"""korabo_llm エントリポイント。

    python korabo_llm.py

で http://127.0.0.1:7860 にWebUIが起動します。
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings

# Gradio 6.19 が Starlette 1.3 で非推奨化した定数名を内部参照しているため、
# リクエストのたびに StarletteDeprecationWarning が出る（無害）。当該カテゴリのみ抑制する。
try:
    from starlette.exceptions import StarletteDeprecationWarning

    warnings.filterwarnings("ignore", category=StarletteDeprecationWarning)
except Exception:
    # クラスの場所が変わった場合のフォールバック（メッセージ一致で抑制）
    warnings.filterwarnings("ignore", message=r".*HTTP_422_UNPROCESSABLE_ENTITY.*")

# どこから起動しても相対パス（config/, data/）が解決できるようにする
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.main_app import build_app


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="korabo_llm WebUI サーバー")
    parser.add_argument(
        "--listen",
        default="127.0.0.1",
        metavar="ADDR",
        help="バインドするアドレス。LAN公開は --listen 0.0.0.0（既定: 127.0.0.1）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="待ち受けポート（既定: 7860）",
    )
    parser.add_argument(
        "--share",
        action="store_true",
        help="Gradioの一時公開URL（gradio.live）を発行する",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="コンソールログの詳細度（既定: INFO）",
    )
    parser.add_argument("--no-color", action="store_true", help="色付き出力を無効化する")
    parser.add_argument("--no-tokens", action="store_true", help="毎ターンのトークン使用量表示を無効化する")
    return parser.parse_args(argv)


def _log_startup(args) -> None:
    """起動サマリ（サーバURL・設定概要）をコンソールに出す。"""
    from korabo import applog

    applog.info(f"korabo_llm 起動 ｜ WebUI: http://{args.listen}:{args.port}"
                + ("  ｜ share=ON" if args.share else ""))
    try:
        from korabo.config import load_config
        from korabo.presets import active_preset_id

        cfg = load_config()

        def _ep(name: str) -> str:
            ep = cfg.endpoints.get(name)
            return "mock" if (ep and ep.base_url.strip().lower() == "mock") else "実LLM"

        m = cfg.master
        applog.info(f"Master : {m.endpoint} / {m.model or '(既定)'} [{_ep(m.endpoint)}]")
        if cfg.roles:
            r0 = cfg.roles[0]
            same = all((r.endpoint, r.model) == (r0.endpoint, r0.model) for r in cfg.roles)
            suffix = "" if same else " (ロールごとに異なる)"
            applog.info(f"Sub    : {r0.endpoint} / {r0.model or '(既定)'} [{_ep(r0.endpoint)}]{suffix}")
        preset = active_preset_id(cfg) or "custom (data/)"
        applog.info(f"ロール数: {len(cfg.roles)} ｜ プリセット: {preset}")
    except Exception as e:
        applog.warning(f"設定サマリの読込に失敗しました: {e}")


def main() -> None:
    args = parse_args()
    from korabo.applog import setup_logging

    setup_logging(level=args.log_level, color=not args.no_color, show_tokens=not args.no_tokens)
    _log_startup(args)
    app = build_app()
    app.queue().launch(
        server_name=args.listen,
        server_port=args.port,
        share=args.share,
    )


if __name__ == "__main__":
    main()
