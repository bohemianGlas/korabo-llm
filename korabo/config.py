"""config.jsonc の読み書き。読込はJSONC（コメント許容）、保存はJSON形式。"""
from __future__ import annotations

import json
from pathlib import Path

import json5

from .schemas import AppConfig

CONFIG_PATH = Path("config/config.jsonc")
EXAMPLE_PATH = Path("config/config.example.jsonc")


def load_config(path: Path | str = CONFIG_PATH) -> AppConfig:
    p = Path(path)
    # 初回起動時、config.jsonc が無ければ同梱の example から自動生成する
    if not p.exists() and p == CONFIG_PATH and EXAMPLE_PATH.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    if not p.exists():
        return AppConfig()
    data = json5.loads(p.read_text(encoding="utf-8"))
    return AppConfig.model_validate(data)


def save_config(cfg: AppConfig, path: Path | str = CONFIG_PATH) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(cfg.model_dump(), ensure_ascii=False, indent=2)
    p.write_text(text + "\n", encoding="utf-8")
