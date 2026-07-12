"""実行時のコンソールログ出力（標準 logging ベース・追加依存なし）。

`session._emit()` から `log_session_event()` を呼び、セッション進行を端末に一行ずつ出す。
`setup_logging()` 未呼び出し時（テスト・インポート時）は NullHandler で無出力。
"""
from __future__ import annotations

import logging
import os
import sys

_LOGGER_NAME = "korabo"

# グローバル設定（setup_logging で更新）
SHOW_TOKENS = True
COLOR = False

# ANSIカラー
_RESET = "\033[0m"
_LEVEL_COLOR = {
    logging.DEBUG: "\033[2m",     # 淡色
    logging.INFO: "",             # 既定色
    logging.WARNING: "\033[33m",  # 黄
    logging.ERROR: "\033[31m",    # 赤
    logging.CRITICAL: "\033[1;31m",
}


def get_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
    return logger


class _Formatter(logging.Formatter):
    def __init__(self, color: bool):
        super().__init__("%(asctime)s %(levelname)-5s %(message)s", datefmt="%H:%M:%S")
        self._color = color

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        if self._color:
            c = _LEVEL_COLOR.get(record.levelno, "")
            if c:
                text = f"{c}{text}{_RESET}"
        return text


def setup_logging(level: str = "INFO", color: bool = True, show_tokens: bool = True) -> None:
    """コンソールログを初期化する（main から1回だけ呼ぶ）。"""
    global SHOW_TOKENS, COLOR
    SHOW_TOKENS = bool(show_tokens)

    use_color = bool(color) and sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
    if use_color and sys.platform == "win32":
        os.system("")  # レガシーコンソールでANSIエスケープ（VT処理）を有効化
    COLOR = use_color

    logger = logging.getLogger(_LOGGER_NAME)
    for h in list(logger.handlers):
        logger.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_Formatter(use_color))
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    logger.propagate = False


# ---------------------------------------------------------------------------
# ヘルパ
# ---------------------------------------------------------------------------

def info(msg: str) -> None:
    get_logger().info(msg)


def warning(msg: str) -> None:
    get_logger().warning(msg)


def _preview(text: str, limit: int = 80) -> str:
    text = " ".join(str(text).split())  # 改行・連続空白をまとめる
    return text if len(text) <= limit else text[:limit] + "…"


# イベント種別 → (ログレベル, 行の組み立て関数)
def log_session_event(turn: int, etype: str, payload: dict) -> None:
    logger = get_logger()
    text = payload.get("text", "")
    role = payload.get("role", "")
    t = f"T{turn}"

    if etype == "situation":
        logger.info(f"🎬 シチュエーション: {_preview(text)}")
    elif etype == "status":
        logger.info(f"ℹ  {_preview(text, 120)}")
    elif etype == "narration":
        logger.info(f"📖 {t}: {_preview(text)}")
    elif etype == "sub_call":
        logger.info(f"➡  {t} Master→{role}: {_preview(text)}")
    elif etype == "sub_reply":
        logger.info(f"⬅  {t} {role}: {_preview(text)}")
    elif etype == "memory_update":
        logger.info(f"📝 {t} {role} 記憶更新: {_preview(text, 60)}")
    elif etype == "intervention":
        logger.info(f"⚡ {t} ユーザー介入: {_preview(text)}")
    elif etype == "finished":
        logger.info(f"🏁 {t} {_preview(text)}")
    elif etype == "master_thought":
        logger.debug(f"💭 {t} Master思考: {_preview(text)}")
    elif etype == "sub_inner":
        logger.debug(f"💭 {t} {role}の心の声: {_preview(text)}")
    elif etype == "scene_packet":
        logger.debug(f"🗺 {t} 場面パケット→{role}: {_preview(text, 160)}")
    elif etype == "memory_skip":
        logger.debug(f"📝 {t} {role} 記憶追記を重複スキップ: {_preview(text, 60)}")
    elif etype == "error":
        logger.error(f"❌ {t} {_preview(text, 200)}")
    # sub_main は sub_reply と重複するため出さない


def log_token(turn: int, model: str, usage: dict, total: int) -> None:
    if not SHOW_TOKENS:
        return
    get_logger().info(
        f"🔢 T{turn} {model}: in={usage.get('prompt', 0):,} "
        f"out={usage.get('completion', 0):,} (累計 {total:,})"
    )
