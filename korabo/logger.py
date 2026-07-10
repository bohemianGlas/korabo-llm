"""セッションログ（Markdown + JSONL）。

logs/session_YYYYMMDD-HHMMSS/
  main.md      … Masterが編纂した最終出力（narrationの連なり）
  full.md      … 全やり取りの時系列記録
  events.jsonl … 構造化イベント（UI・過去セッション閲覧用）
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

LOGS_DIR = Path("logs")


class SessionLogger:
    def __init__(self, base_dir: str | Path = LOGS_DIR):
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.session_id = f"session_{ts}"
        self.dir = Path(base_dir) / self.session_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.main_path = self.dir / "main.md"
        self.full_path = self.dir / "full.md"
        self.events_path = self.dir / "events.jsonl"
        header = f"# セッション {ts}\n"
        self.main_path.write_text(header + "\n", encoding="utf-8")
        self.full_path.write_text(header + "\n", encoding="utf-8")

    def _append(self, path: Path, text: str) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(text)

    def event(self, etype: str, turn: int, **payload) -> None:
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "type": etype,
            "turn": turn,
            **payload,
        }
        self._append(self.events_path, json.dumps(record, ensure_ascii=False) + "\n")
        self._append(self.full_path, format_event_md(record) + "\n")
        if etype in ("narration", "sub_main"):
            self._append(self.main_path, payload.get("text", "") + "\n\n")


def format_event_md(e: dict) -> str:
    """イベント1件をfullログ/UI表示用のMarkdown1ブロックに整形する。"""
    t = e.get("type")
    turn = e.get("turn", 0)
    text = e.get("text", "")
    role = e.get("role", "")
    if t == "narration":
        return f"**📖 語り (T{turn})**\n\n{text}\n"
    if t == "master_thought":
        quoted = text.replace("\n", "\n> ")
        return f"> 💭 **Master思考 (T{turn})**: {quoted}\n"
    if t == "sub_call":
        return f"➡️ **Master → {role} (T{turn})**: {text}\n"
    if t == "sub_reply":
        return f"⬅️ **{role} → Master (T{turn})**: {text}\n"
    if t == "sub_inner":
        return f"💭 **{role} の心の声 (T{turn})**: {text}\n"
    if t == "sub_main":
        return f"🎭 **本文へ反映 (T{turn})**\n\n{text}\n"
    if t == "memory_update":
        return f"📝 **{role} の記憶に追記 (T{turn})**: {text}\n"
    if t == "intervention":
        return f"⚡ **ユーザー介入 (T{turn})**: {text}\n"
    if t == "situation":
        return f"🎬 **シチュエーション**\n\n{text}\n"
    if t == "status":
        return f"ℹ️ {text}\n"
    if t == "error":
        return f"❌ **エラー (T{turn})**: {text}\n"
    if t == "finished":
        return f"🏁 **終了 (T{turn})**: {text}\n"
    return f"({t}) {text}\n"


# ---------------------------------------------------------------------------
# 過去セッションの閲覧
# ---------------------------------------------------------------------------

def list_sessions(base_dir: str | Path = LOGS_DIR) -> list[str]:
    base = Path(base_dir)
    if not base.exists():
        return []
    return sorted((d.name for d in base.iterdir() if d.is_dir()), reverse=True)


def read_session_file(session_id: str, filename: str, base_dir: str | Path = LOGS_DIR) -> str:
    p = Path(base_dir) / session_id / filename
    if not p.exists():
        return "(ファイルがありません)"
    return p.read_text(encoding="utf-8")
