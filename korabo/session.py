"""セッションコントローラ。

実行モード・一時停止/再開/停止・ユーザー介入を制御しつつ、
LangGraphのターングラフをバックグラウンドスレッドで回す。
"""
from __future__ import annotations

import html
import threading
import time
from pathlib import Path

from . import applog, i18n
from .graph import build_turn_graph
from .llm_client import create_client
from .logger import SessionLogger, format_event_md
from .master import build_master_messages, parse_master_decision
from .memory import append_memory, read_memory
from .prompts import load_important_prompt, load_master_prompt
from .scene import build_scene_packet, packet_debug_summary
from .schemas import AppConfig, MasterDecision, RoleConfig
from .sub import SUB_HISTORY_WINDOW, build_sub_messages, parse_sub_response

MODE_LABELS = {
    "step": "1ステップずつ",
    "run_n": "指定ステップまで実行",
    "master_stop_limited": "Master判断で停止（上限あり）",
    "master_stop_infinite": "Master判断で停止（無限）",
    "infinite": "無限モード",
}
LABEL_TO_MODE = {v: k for k, v in MODE_LABELS.items()}

# Masterのfinish判断を尊重するモード
_RESPECTS_FINISH = {"step", "master_stop_limited", "master_stop_infinite"}
# ターン数上限を適用するモード
_USES_LIMIT = {"run_n", "master_stop_limited"}

# 状態の見た目（ラベル・絵文字・色）
_STATE_STYLE = {
    "idle": ("準備中", "⏳", "#6b7280"),
    "running": ("実行中", "▶", "#16a34a"),
    "paused": ("一時停止中", "⏸", "#d97706"),
    "finished": ("完了", "🏁", "#2563eb"),
    "stopped": ("停止済み", "⏹", "#475569"),
    "error": ("エラーで一時停止", "❌", "#dc2626"),
}


def render_status_banner(kind: str, meta: str = "", detail: str = "") -> str:
    """状態を大きく色分けしたHTMLバナーを生成する（UI共通・アイドル表示にも使う）。"""
    label, emoji, color = _STATE_STYLE.get(kind, _STATE_STYLE["idle"])
    label = i18n.t(label)
    banner = (
        f'<div style="padding:16px 20px;border-radius:12px;background:{color};'
        f'color:#fff;font-size:1.7rem;font-weight:800;text-align:center;'
        f'letter-spacing:0.05em;box-shadow:0 2px 8px rgba(0,0,0,0.18);">'
        f"{emoji}&nbsp;{label}</div>"
    )
    parts = [banner]
    if meta:
        parts.append(
            f'<div style="margin-top:8px;font-size:0.95rem;color:#9ca3af;'
            f'text-align:center;">{meta}</div>'
        )
    if detail:
        parts.append(
            f'<div style="margin-top:6px;font-size:0.9rem;color:#dc2626;'
            f'text-align:center;">{detail}</div>'
        )
    return "".join(parts)


class SessionRunner:
    def __init__(
        self,
        cfg: AppConfig,
        situation: str,
        mode: str,
        max_turns: int,
        target_main_chars: int = 0,
        style: str = "",
        dials: list[dict] | None = None,
        sub_memory_enabled: bool = True,
        sub_in_main_log: bool = True,
        sub_main_show_name: bool = True,
        sub_main_show_action: bool = True,
        sub_main_show_inner: bool = True,
        sub_main_inner_prefix: str = "（心の声）",
        narrative_style: str = "third",
        pov_role: str = "",
        narrative_custom: str = "",
    ):
        self.cfg = cfg
        self.situation = situation.strip()
        self.style = (style or "").strip()
        self.dials = [d for d in (dials or []) if str(d.get("label", "")).strip()]
        self.sub_memory_enabled = bool(sub_memory_enabled)
        self.sub_in_main_log = bool(sub_in_main_log)
        self.sub_main_show_name = bool(sub_main_show_name)
        self.sub_main_show_action = bool(sub_main_show_action)
        self.sub_main_show_inner = bool(sub_main_show_inner)
        self.sub_main_inner_prefix = sub_main_inner_prefix  # stripしない（空白も尊重）
        self.narrative_style = (narrative_style or "third").strip()
        self.narrative_custom = (narrative_custom or "").strip()
        pov = cfg.get_role((pov_role or "").strip())
        self.pov_label = (pov.name or pov.id) if pov else ""
        self.mode = mode
        self.max_turns = int(max_turns) if mode in _USES_LIMIT else None
        self.target_main_chars = max(0, int(target_main_chars or 0))

        self.turn = 0
        self.history: list[dict] = []
        # Masterが申告した「現ターンの在席ロールid」（presence可視性用。無ければNone）
        self._current_present: list[str] | None = None
        self.finished = False
        self.paused = False
        self.stopped = False
        self._step_request = False
        self._interventions: list[str] = []
        self._lock = threading.Lock()
        self._last_decision: MasterDecision | None = None
        self._error: str | None = None

        self._main_md: list[str] = []
        self._detail_md: list[str] = []
        # モデル名 -> {prompt, completion, total, calls}
        self.token_usage: dict[str, dict] = {}

        self.logger = SessionLogger()

        m = cfg.master
        self.master_memory_enabled = bool(getattr(m, "memory_enabled", True))
        self.master_memory_file = getattr(m, "memory_file", "") or ""
        self.master_directive = getattr(m, "directive", "") or ""
        self.master_important_file = getattr(m, "important_prompt_file", "") or ""
        self.prompt_lang = getattr(cfg, "prompt_lang", "ja") or "ja"
        self.master_prompt = load_master_prompt(m.prompt_file) or "あなたは物語の語り手です。"
        endpoint = cfg.endpoints.get(m.endpoint)
        if endpoint is None:
            raise ValueError(f"Masterのエンドポイント '{m.endpoint}' が未定義です")
        self._master_client = create_client(endpoint, m.model, m.temperature)
        self._sub_clients: dict[str, object] = {}

        self._graph = build_turn_graph(self)
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # UI向けインターフェース
    # ------------------------------------------------------------------

    @property
    def is_active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def main_log_md(self) -> str:
        return "\n\n".join(self._main_md) or "（まだ出力がありません）"

    def _main_char_count(self) -> int:
        """これまでにmain.mdへ書かれた本文のおおよその文字数。"""
        return sum(len(b) for b in self._main_md)

    def detail_log_md(self, last: int = 120) -> str:
        blocks = self._detail_md[-last:]
        return "\n\n".join(blocks) or "（まだイベントがありません）"

    def token_report_md(self) -> str:
        """モデルごと＋合計のトークン使用量をMarkdownテーブルで返す。"""
        with self._lock:
            usage = {k: dict(v) for k, v in self.token_usage.items()}
        if not usage:
            return "（トークン使用量はまだありません）"
        lines = [
            "| モデル | 入力 | 出力 | 合計 | 呼出 |",
            "|:--|--:|--:|--:|--:|",
        ]
        tp = tc = tt = tcalls = 0
        for model, u in usage.items():
            lines.append(
                f"| `{model}` | {u['prompt']:,} | {u['completion']:,} | {u['total']:,} | {u['calls']} |"
            )
            tp += u["prompt"]
            tc += u["completion"]
            tt += u["total"]
            tcalls += u["calls"]
        lines.append(f"| **合計** | **{tp:,}** | **{tc:,}** | **{tt:,}** | **{tcalls}** |")
        return "\n".join(lines)

    def state_kind(self) -> str:
        if self.stopped:
            return "stopped"
        if self.finished:
            return "finished"
        if self._error:
            return "error"
        if self.paused:
            return "paused"
        if self.is_active:
            return "running"
        return "idle"

    def status_html(self) -> str:
        limit = f" / {self.max_turns}" if self.max_turns else ""
        meta = (
            f"{i18n.t('セッション')}: {self.logger.session_id}"
            f"　｜　{i18n.t('モード')}: {i18n.t(MODE_LABELS.get(self.mode, self.mode))}"
            f"　｜　{i18n.t('ターン')}: {self.turn}{limit}"
        )
        detail = ""
        if self._error and self.state_kind() == "error":
            detail = html.escape(self._error)
        return render_status_banner(self.state_kind(), meta, detail)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self._error = None
        self.paused = False

    def step(self) -> None:
        """一時停止中に1ターンだけ進める。"""
        self._error = None
        self._step_request = True

    def stop(self) -> None:
        self.stopped = True
        self.paused = False

    _CONTINUE_NOTE = "（続き生成）ここまでの流れを踏まえ、物語を自然に続けてください。"

    def _apply_run_settings(self, mode: str, max_turns: int) -> None:
        """実行モードとターン上限を適用する。限定モードでは現在ターンから追加Nターン。"""
        self.mode = mode
        if mode in _USES_LIMIT:
            self.max_turns = self.turn + max(1, int(max_turns or 1))
        else:
            self.max_turns = None

    def update_run_settings(self, mode: str, max_turns: int) -> None:
        """実行中にモード・ターン数をライブ変更する。"""
        self._apply_run_settings(mode, max_turns)
        limit = f"あと約{self.max_turns - self.turn}ターン" if self.max_turns else "上限なし"
        self._emit("status", text=f"⚙ 設定変更: モード「{MODE_LABELS.get(mode, mode)}」／{limit}")

    def continue_run(self, mode: str, max_turns: int, note: str | None = _CONTINUE_NOTE) -> None:
        """終了/停止したセッションから、新しいモード・ターン数で続きを生成する。"""
        if self.is_active:
            return
        self._error = None
        self.stopped = False
        self.finished = False
        self.paused = False
        self._apply_run_settings(mode, max_turns)
        if note:
            self.add_intervention(note)
        limit = f"+{self.max_turns - self.turn}ターン" if self.max_turns else "上限なし"
        self._emit("status", text=f"▶ 続きを生成します（モード「{MODE_LABELS.get(mode, mode)}」／{limit}）")
        self._thread = threading.Thread(target=self._run, kwargs={"emit_header": False}, daemon=True)
        self._thread.start()

    def add_intervention(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        with self._lock:
            self._interventions.append(text)
        self._emit("intervention", text=text)

    # ------------------------------------------------------------------
    # 実行ループ
    # ------------------------------------------------------------------

    def _run(self, emit_header: bool = True) -> None:
        if emit_header:
            self._emit("situation", text=self.situation)
            if self.style:
                self._emit("status", text=f"文体・方向性: {self.style}")
            if self.dials:
                dials_str = " / ".join(f"{d['label']}:{int(d['value'])}" for d in self.dials)
                self._emit("status", text=f"味付け: {dials_str}")
            narrative_labels = {"third": "三人称小説", "first": "一人称小説", "script": "台本・戯曲風", "custom": "カスタム"}
            n_label = narrative_labels.get(self.narrative_style, self.narrative_style)
            pov = f"（視点: {self.pov_label}）" if self.narrative_style == "first" and self.pov_label else ""
            self._emit("status", text=f"叙述スタイル: {n_label}{pov}")
            self._emit("status", text=f"モード「{MODE_LABELS.get(self.mode, self.mode)}」で開始します。")
        while not self.stopped and not self.finished:
            if self.paused:
                if self._step_request:
                    self._step_request = False
                else:
                    time.sleep(0.15)
                    continue
            self.turn += 1
            try:
                self._graph.invoke({})
            except Exception as e:
                self._error = str(e)
                raw = str(e).replace("\n", " ")
                if len(raw) > 200:
                    raw = raw[:200] + "…"
                self._emit(
                    "error",
                    text=(
                        "応答の取得に失敗しました（リトライしても回復せず）。"
                        "推論エンジンがモデルの出力形式を拒否した可能性があります。"
                        "別のモデル/エンドポイントに変更するか、「再開」で再試行してください。\n\n"
                        f"詳細: {raw}"
                    ),
                )
                self.turn -= 1  # 再開時にターン番号が飛ばないよう、失敗ターンを巻き戻す
                self.paused = True
                continue
            if self.max_turns and self.turn >= self.max_turns and not self.finished:
                self.finished = True
                self._emit("finished", text=f"ターン上限（{self.max_turns}）に到達しました。")
            if self.mode == "step" and not self.finished:
                self.paused = True
        if self.stopped:
            self._emit("status", text="ユーザー操作により停止しました。")

    # ------------------------------------------------------------------
    # グラフのノード本体（graph.py から呼ばれる）
    # ------------------------------------------------------------------

    def run_master(self) -> MasterDecision:
        with self._lock:
            interventions = self._interventions[:]
            self._interventions.clear()

        master_memory = (
            read_memory(self.master_memory_file)
            if self.master_memory_enabled and self.master_memory_file
            else ""
        )
        messages = build_master_messages(
            self.master_prompt,
            self.situation,
            self.cfg.roles,
            self.history,
            self.turn,
            self.max_turns,
            interventions,
            self.style,
            self.dials,
            self.narrative_style,
            self.pov_label,
            self.narrative_custom,
            self.sub_in_main_log,
            master_memory_enabled=self.master_memory_enabled,
            master_memory=master_memory,
            directive=self.master_directive,
            target_main_chars=self.target_main_chars,
            current_main_chars=self._main_char_count(),
            # テンプレ未変更なら空が返り、注入されない（内容に左右されない）
            important_prompt=load_important_prompt(self.master_important_file),
            lang=self.prompt_lang,
        )
        for t in interventions:
            self.history.append({"kind": "intervention", "text": t})

        raw = self._master_client.chat(messages, on_retry=self._on_retry("Master"))
        self._track_usage(self._master_client)
        decision = parse_master_decision(raw)

        # Masterが場面の在席者を申告したターンは、履歴イベントにpresenceを付与する
        self._current_present = (
            list(decision.scene.present_roles)
            if decision.scene and decision.scene.present_roles
            else None
        )

        if decision.action == "finish" and self.mode not in _RESPECTS_FINISH:
            decision.action = "continue"

        if decision.action == "call_sub":
            role = self.cfg.get_role(decision.target_role)
            if role is None:
                self._emit(
                    "error",
                    text=f"Masterが不明なロール '{decision.target_role}' を指定したため、語りのみで続行します。",
                )
                decision.action = "continue"

        if decision.thought:
            self._emit("master_thought", text=decision.thought)
        if decision.narration:
            self._append_main(decision.narration, "narration")
            self._hist("narration", text=decision.narration)
        if decision.action == "call_sub":
            self._emit("sub_call", role=decision.target_role, text=decision.message_to_role)
            self._hist("master_to_sub", role=decision.target_role, text=decision.message_to_role)
        if decision.action == "finish":
            self.finished = True
            self._emit("finished", text="Masterが物語の完結を宣言しました。")

        # 語り手（Master）の記憶追記（記憶機能が有効なときのみ）
        if self.master_memory_enabled and decision.memory_append and self.master_memory_file:
            if append_memory(self.master_memory_file, decision.memory_append, turn=self.turn):
                self._emit("memory_update", role="Master", text=decision.memory_append)
            else:
                self._emit("memory_skip", role="Master", text=decision.memory_append)

        self._last_decision = decision
        return decision

    def run_sub(self, decision: MasterDecision) -> None:
        role = self.cfg.get_role(decision.target_role)
        if role is None:
            return
        client = self._get_sub_client(role)
        role_prompt = _read_text(role.role_prompt_file) or f"あなたは「{role.name or role.id}」です。"
        # サブの記憶機能: 全体ON かつ 個別ON かつ ファイル有り のときのみ読み書きする
        mem_on = (
            self.sub_memory_enabled
            and bool(getattr(role, "memory_enabled", True))
            and bool(role.memory_file)
        )
        memory_text = read_memory(role.memory_file) if mem_on else ""

        # 場面パケット: Subへ渡す可視情報をここで一括組立・フィルタ（渡す前に除外）
        packet = build_scene_packet(
            self.turn,
            decision,
            role,
            self.cfg.roles,
            self.history,
            memory_text=memory_text,
            window=SUB_HISTORY_WINDOW,
            lang=self.prompt_lang,
        )
        self._emit("scene_packet", role=role.id, text=packet_debug_summary(packet))

        messages = build_sub_messages(
            role,
            role_prompt,
            memory_text,
            self.situation,
            decision.message_to_role,
            self.history,
            self.cfg.roles,
            scene_packet=packet,
            lang=self.prompt_lang,
        )
        raw = client.chat(messages, on_retry=self._on_retry(role.name or role.id))
        self._track_usage(client)
        resp = parse_sub_response(raw)

        name = role.name or role.id
        outward = resp.outward_text()
        self._emit("sub_reply", role=role.id, text=outward)
        self._hist("sub_to_master", role=role.id, text=outward)

        # 心の声：Master・本人には見えるが他キャラには見えない（filter_history_for_roleで隔離）
        if resp.inner_voice.strip():
            self._emit("sub_inner", role=role.id, text=resp.inner_voice.strip())
            self._hist("sub_inner", role=role.id, text=resp.inner_voice.strip())

        # トグルON時、サブの生のセリフ・言動・心の声をメインログにも反映（指令は含めない）
        if self.sub_in_main_log:
            block = resp.main_log_block(
                name,
                show_name=self.sub_main_show_name,
                show_action=self.sub_main_show_action,
                show_inner=self.sub_main_show_inner,
                inner_prefix=self.sub_main_inner_prefix,
            )
            if block.strip():
                self._add_to_main(block)

        if mem_on and resp.memory_append:
            if append_memory(role.memory_file, resp.memory_append, turn=self.turn):
                self._emit("memory_update", role=role.id, text=resp.memory_append)
            else:
                self._emit("memory_skip", role=role.id, text=resp.memory_append)

    # ------------------------------------------------------------------
    # 内部ヘルパ
    # ------------------------------------------------------------------

    def _hist(self, kind: str, **payload) -> None:
        """履歴イベントを追加する。Masterが在席者を申告していればpresenceを付与。"""
        e = {"kind": kind, **payload}
        if self._current_present:
            e["present"] = list(self._current_present)
        self.history.append(e)

    def _fallback_endpoint(self) -> str:
        """ロールに endpoint 未設定のときの保険。mock があれば mock、無ければ先頭。"""
        if "mock" in self.cfg.endpoints:
            return "mock"
        return next(iter(self.cfg.endpoints), "")

    def _get_sub_client(self, role: RoleConfig):
        if role.id in self._sub_clients:
            return self._sub_clients[role.id]
        ep_name = role.endpoint or self._fallback_endpoint()
        endpoint = self.cfg.endpoints.get(ep_name)
        if endpoint is None:
            raise ValueError(f"ロール '{role.id}' のエンドポイント '{ep_name}' が未定義です")
        temp = role.temperature if role.temperature is not None else 0.8
        client = create_client(endpoint, role.model, temp)
        self._sub_clients[role.id] = client
        return client

    def _append_main(self, text: str, etype: str) -> None:
        """メインログ(main.md/UI)へ1ブロック追記する。直前と完全一致なら重複としてスキップ。"""
        t = (text or "").strip()
        if not t:
            return
        if self._main_md and self._main_md[-1].strip() == t:
            return  # 直前の段落と完全一致 → 二重表示を防ぐ
        self._main_md.append(text)
        self._emit(etype, text=text)

    def _add_to_main(self, text: str) -> None:
        """narration以外の内容（サブの生セリフ等）をメインログへ反映する。"""
        self._append_main(text, "sub_main")

    def _on_retry(self, who: str):
        """chat() のリトライ直前に詳細ログへ通知するコールバックを返す。"""
        def _cb(attempt: int, err: Exception) -> None:
            msg = str(err).replace("\n", " ")
            if len(msg) > 160:
                msg = msg[:160] + "…"
            self._emit("status", text=f"⚠ {who} の応答エラー。リトライ中…（{attempt}回目） {msg}")
        return _cb

    def _track_usage(self, client) -> None:
        usage = getattr(client, "last_usage", None)
        if not usage:
            return
        model = getattr(client, "model", "") or "(unknown)"
        with self._lock:
            agg = self.token_usage.setdefault(
                model, {"prompt": 0, "completion": 0, "total": 0, "calls": 0}
            )
            agg["prompt"] += usage.get("prompt", 0)
            agg["completion"] += usage.get("completion", 0)
            agg["total"] += usage.get("total", 0)
            agg["calls"] += 1
            grand_total = sum(v["total"] for v in self.token_usage.values())
        applog.log_token(self.turn, model, usage, grand_total)

    def _emit(self, etype: str, **payload) -> None:
        self.logger.event(etype, self.turn, **payload)
        record = {"type": etype, "turn": self.turn, **payload}
        self._detail_md.append(format_event_md(record))
        applog.log_session_event(self.turn, etype, payload)


def _read_text(path: str) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")
