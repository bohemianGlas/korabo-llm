"""実行タブ: セッションの開始・制御・介入・リアルタイムログ表示。"""
from __future__ import annotations

import time

import gradio as gr

from korabo import i18n
from korabo.config import load_config, save_config
from korabo.schemas import Dial
from korabo.session import MODE_LABELS, SessionRunner, render_status_banner

t = i18n.t
_runner: SessionRunner | None = None

# 味付けダイヤルのスロット数（ラベル空欄のスロットは無効扱い）
SLOTS = 6
DEFAULT_DIALS = [("叙情的", 4), ("娯楽性", 9), ("突飛さ", 1), ("シリアス度", 5)]

# 叙述スタイル（内部キー → 表示ラベル日本語。表示は t() で翻訳）
NARRATIVE_LABELS = {
    "third": "三人称小説",
    "first": "一人称小説（視点ロールを選択）",
    "script": "台本・戯曲風",
    "custom": "カスタム（自由記述）",
}


def _idle():
    return (
        render_status_banner("idle", meta=t("セッション未開始")),
        t("（まだ出力がありません）"),
        t("（まだイベントがありません）"),
        t("（トークン使用量はまだありません）"),
    )


def _initial_dials() -> list[tuple[str, int]]:
    saved = [(d.label, d.value) for d in load_config().run.dials]
    dials = saved or DEFAULT_DIALS[:]
    return (dials + [("", 5)] * SLOTS)[:SLOTS]


def _snapshot() -> tuple[str, str, str, str]:
    r = _runner
    if r is None:
        return _idle()
    return r.status_html(), r.main_log_md(), r.detail_log_md(), r.token_report_md()


def _collect_dials(dials_flat: tuple) -> list[dict]:
    """フラットな [ラベル×SLOTS, 値×SLOTS] を、ラベル非空のダイヤル辞書リストにまとめる。"""
    labels = dials_flat[:SLOTS]
    values = dials_flat[SLOTS : SLOTS * 2]
    dials = []
    for lbl, val in zip(labels, values):
        lbl = (lbl or "").strip()
        if lbl:
            dials.append({"label": lbl, "value": int(val)})
    return dials


def _start(
    situation: str,
    style: str,
    mode_label: str,
    max_turns: float,
    sub_in_main: bool,
    show_name: bool,
    show_action: bool,
    show_inner: bool,
    narrative_label: str,
    pov_role: str,
    narrative_custom: str,
    *dials_flat,
):
    """セッションを開始し、終了（または停止）までスナップショットをストリーミングする。"""
    global _runner
    if _runner is not None and _runner.is_active:
        gr.Warning(t("実行中のセッションがあります。先に停止してください。"))
        yield _snapshot()
        return
    if not (situation or "").strip():
        gr.Warning(t("シチュエーションプロンプトを入力してください。"))
        yield _snapshot()
        return
    mode = mode_label if mode_label in MODE_LABELS else "master_stop_limited"
    narrative = narrative_label if narrative_label in NARRATIVE_LABELS else "third"
    dials = _collect_dials(dials_flat)
    try:
        cfg = load_config()
        # 文体・方向性・味付け・叙述スタイル・ログ設定を次回起動時に復元できるよう設定に保存
        cfg.run.default_style = (style or "").strip()
        cfg.run.dials = [Dial(label=d["label"], value=d["value"]) for d in dials]
        cfg.run.sub_in_main_log = bool(sub_in_main)
        cfg.run.sub_main_show_name = bool(show_name)
        cfg.run.sub_main_show_action = bool(show_action)
        cfg.run.sub_main_show_inner = bool(show_inner)
        cfg.run.narrative_style = narrative
        cfg.run.pov_role = (pov_role or "").strip()
        cfg.run.narrative_custom = (narrative_custom or "").strip()
        save_config(cfg)
        _runner = SessionRunner(
            cfg, situation, mode, int(max_turns or 20),
            style=style, dials=dials,
            sub_in_main_log=bool(sub_in_main),
            sub_main_show_name=bool(show_name),
            sub_main_show_action=bool(show_action),
            sub_main_show_inner=bool(show_inner),
            narrative_style=narrative,
            pov_role=pov_role,
            narrative_custom=narrative_custom,
        )
        _runner.start()
    except Exception as e:
        gr.Warning(f"{t('開始に失敗しました')}: {e}")
        yield _snapshot()
        return
    yield from _drive()


def _drive():
    """runnerがactiveの間スナップショットをストリーミングし、最後に一度yieldする。"""
    yield _snapshot()
    runner = _runner
    while runner is not None and runner.is_active:
        time.sleep(0.4)
        yield _snapshot()
    yield _snapshot()


def _continue(mode_label: str, max_turns: float):
    """終了/停止したセッションの続きを、この設定で生成する。"""
    if _runner is None:
        gr.Warning(t("セッションがありません。まず『開始』してください。"))
        yield _snapshot()
        return
    if _runner.is_active:
        gr.Warning(t("実行中です。『続きを生成』は終了・停止後に使えます。"))
        yield _snapshot()
        return
    mode = mode_label if mode_label in MODE_LABELS else "master_stop_limited"
    try:
        _runner.continue_run(mode, int(max_turns or 20))
    except Exception as e:
        gr.Warning(f"{t('続き生成に失敗しました')}: {e}")
        yield _snapshot()
        return
    yield from _drive()


def _change_settings(mode_label: str, max_turns: float):
    """実行中にモード・ターン数をライブ変更する。"""
    if _runner is None or not _runner.is_active:
        gr.Warning(t("実行中のセッションがありません（終了後は『続きを生成』を使用してください）。"))
        return _snapshot()
    mode = mode_label if mode_label in MODE_LABELS else "master_stop_limited"
    _runner.update_run_settings(mode, int(max_turns or 20))
    gr.Info(t("実行設定を変更しました。次のターンから反映されます。"))
    return _snapshot()


def _step():
    if _runner is None or not _runner.is_active:
        gr.Warning(t("実行中のセッションがありません。"))
    else:
        _runner.step()
    return _snapshot()


def _pause():
    if _runner is not None:
        _runner.pause()
    return _snapshot()


def _resume():
    if _runner is not None:
        _runner.resume()
    return _snapshot()


def _stop():
    if _runner is not None:
        _runner.stop()
    return _snapshot()


def _intervene(text: str):
    if _runner is None or not _runner.is_active:
        gr.Warning(t("実行中のセッションがありません。"))
        return gr.update(), *_snapshot()
    if not (text or "").strip():
        return gr.update(), *_snapshot()
    _runner.add_intervention(text)
    gr.Info(t("介入を送信しました。次のMasterターンで反映されます。"))
    return "", *_snapshot()


def _tick():
    return _snapshot()


def build() -> None:
    with gr.Row():
        with gr.Column(scale=2):
            situation = gr.Textbox(
                label=t("シチュエーションプロンプト"),
                placeholder="例: 嵐の夜、灯台のふもとの古書店にアリスが駆け込んでくる。店主のボブは…",
                lines=6,
            )
            style = gr.Textbox(
                label=t("文体・方向性（作品全体のトーン）"),
                placeholder="例: 叙情的で静かな私小説風。短めの文で情景を丁寧に。／ラノベ風にテンポよく軽妙に。",
                lines=2,
                value=load_config().run.default_style,
            )
            _cfg0 = load_config()
            _narr0 = _cfg0.run.narrative_style if _cfg0.run.narrative_style in NARRATIVE_LABELS else "third"
            _role_choices = [(f"{r.name or r.id} ({r.id})", r.id) for r in _cfg0.roles]
            with gr.Row():
                narrative_dd = gr.Dropdown(
                    label=t("叙述スタイル（Masterの編纂形式）"),
                    choices=[(t(v), k) for k, v in NARRATIVE_LABELS.items()],
                    value=_narr0,
                    scale=2,
                )
                pov_dd = gr.Dropdown(
                    label=t("視点ロール（一人称）"),
                    choices=_role_choices,
                    value=_cfg0.run.pov_role or None,
                    visible=(_narr0 == "first"),
                    scale=1,
                )
            narrative_custom_tb = gr.Textbox(
                label=t("カスタム叙述指示"),
                placeholder="例: 二人称「あなた」で読者に語りかけるゲームブック調で書く",
                lines=2,
                value=_cfg0.run.narrative_custom,
                visible=(_narr0 == "custom"),
            )
            gr.Markdown(t("#### 🎚 作品の味付け（ラベルは自由に編集可 / 値 1〜10・高いほど強い）"))
            dial_labels = []
            dial_values = []
            _init = _initial_dials()
            for i in range(SLOTS):
                with gr.Row():
                    lbl = gr.Textbox(
                        value=_init[i][0],
                        placeholder=f"軸{i + 1}の名前（例: 叙情的）",
                        show_label=False,
                        scale=2,
                        container=False,
                    )
                    val = gr.Slider(
                        minimum=1,
                        maximum=10,
                        step=1,
                        value=_init[i][1],
                        show_label=False,
                        scale=3,
                        container=False,
                    )
                dial_labels.append(lbl)
                dial_values.append(val)
            with gr.Row():
                mode = gr.Dropdown(
                    label=t("実行モード"),
                    choices=[(t(v), k) for k, v in MODE_LABELS.items()],
                    value="master_stop_limited",
                )
                max_turns = gr.Number(
                    label=t("ターン上限"),
                    value=20,
                    precision=0,
                    minimum=1,
                    info=t("続き生成・実行中変更では「現在から追加Nターン」として扱われます"),
                )
            sub_in_main = gr.Checkbox(
                label=t("サブの生のセリフ・心情もメインログに反映（OFFならMaster編纂のみ）"),
                value=_cfg0.run.sub_in_main_log,
                info=t("セリフだけを載せたい場合は、これをONにして下の3つ（名前・仕草・心の声）をすべてOFF"),
            )
            with gr.Row():
                show_name_cb = gr.Checkbox(
                    label=t("└ ロール名見出し（**名前**）を付ける"),
                    value=_cfg0.run.sub_main_show_name,
                )
                show_action_cb = gr.Checkbox(
                    label=t("└ 仕草・行動(action)を含める"),
                    value=_cfg0.run.sub_main_show_action,
                )
                show_inner_cb = gr.Checkbox(
                    label=t("└ （心の声）を含める"),
                    value=_cfg0.run.sub_main_show_inner,
                )
            with gr.Row():
                start_btn = gr.Button(t("▶ 開始"), variant="primary")
                step_btn = gr.Button(t("⏭ 1ステップ"))
                pause_btn = gr.Button(t("⏸ 一時停止"))
                resume_btn = gr.Button(t("⏵ 再開"))
                stop_btn = gr.Button(t("⏹ 停止"), variant="stop")
            with gr.Row():
                continue_btn = gr.Button(t("⏩ 続きを生成（この設定で）"), variant="primary")
                change_btn = gr.Button(t("🔧 実行設定を変更（実行中）"))
            intervention = gr.Textbox(
                label=t("ユーザー介入（実行中に送信可能）"),
                placeholder="例: 突然、店の照明がすべて消える",
                lines=2,
            )
            intervene_btn = gr.Button(t("⚡ 介入を送信"))
        with gr.Column(scale=3):
            status_md = gr.HTML(render_status_banner("idle", meta=t("セッション未開始")))
            gr.Markdown(t("### 📖 メインログ（Masterの編纂結果）"))
            main_md = gr.Markdown(t("（まだ出力がありません）"), height=350)
            with gr.Accordion(t("🔍 詳細ストリーム（Master思考・Sub応答・記憶更新）"), open=True):
                detail_md = gr.Markdown(t("（まだイベントがありません）"), height=350)
            with gr.Accordion(t("📊 トークン使用量（モデルごと・合計）"), open=True):
                token_md = gr.Markdown(t("（トークン使用量はまだありません）"))

    outputs = [status_md, main_md, detail_md, token_md]
    start_btn.click(
        _start,
        inputs=[
            situation, style, mode, max_turns,
            sub_in_main, show_name_cb, show_action_cb, show_inner_cb,
            narrative_dd, pov_dd, narrative_custom_tb,
            *dial_labels, *dial_values,
        ],
        outputs=outputs,
        show_progress="hidden",
    )
    step_btn.click(_step, outputs=outputs)
    pause_btn.click(_pause, outputs=outputs)
    resume_btn.click(_resume, outputs=outputs)
    stop_btn.click(_stop, outputs=outputs)
    continue_btn.click(_continue, inputs=[mode, max_turns], outputs=outputs, show_progress="hidden")
    change_btn.click(_change_settings, inputs=[mode, max_turns], outputs=outputs)
    intervene_btn.click(_intervene, inputs=[intervention], outputs=[intervention, *outputs])
    intervention.submit(_intervene, inputs=[intervention], outputs=[intervention, *outputs])

    def _narrative_changed(kind: str):
        kind = kind if kind in NARRATIVE_LABELS else "third"
        return (
            gr.update(visible=(kind == "first")),
            gr.update(visible=(kind == "custom")),
        )

    narrative_dd.change(_narrative_changed, inputs=[narrative_dd], outputs=[pov_dd, narrative_custom_tb])

    timer = gr.Timer(0.7)
    timer.tick(_tick, outputs=outputs)
