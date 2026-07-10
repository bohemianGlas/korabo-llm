"""サブLLMの外部記憶（memo_md）の読み書き。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


def read_memory(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def append_memory(path: str | Path, text: str) -> None:
    text = text.strip()
    if not text:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing = p.read_text(encoding="utf-8") if p.exists() else ""
    sep = "" if existing.endswith("\n") or not existing else "\n"
    p.write_text(f"{existing}{sep}\n## {ts}\n\n{text}\n", encoding="utf-8")


def write_memory(path: str | Path, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
