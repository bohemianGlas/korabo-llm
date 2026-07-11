"""詳細ログタブ: 過去セッションの main.md / full.md を閲覧・ダウンロード。"""
from __future__ import annotations

import gradio as gr

from korabo.i18n import t
from korabo.logger import LOGS_DIR, list_sessions, read_session_file


def _dl_updates(session_id: str):
    """ダウンロードボタン2つの value/interactive を更新する gr.update を返す。"""
    if session_id:
        main_p = LOGS_DIR / session_id / "main.md"
        full_p = LOGS_DIR / session_id / "full.md"
        return (
            gr.update(value=str(main_p) if main_p.exists() else None, interactive=main_p.exists()),
            gr.update(value=str(full_p) if full_p.exists() else None, interactive=full_p.exists()),
        )
    return gr.update(value=None, interactive=False), gr.update(value=None, interactive=False)


def _refresh():
    sessions = list_sessions()
    selected = sessions[0] if sessions else None
    dl_main, dl_full = _dl_updates(selected)
    return gr.update(choices=sessions, value=selected), dl_main, dl_full


def _load(session_id: str):
    dl_main, dl_full = _dl_updates(session_id)
    if not session_id:
        return t("(セッション未選択)"), t("(セッション未選択)"), dl_main, dl_full
    return (
        read_session_file(session_id, "main.md"),
        read_session_file(session_id, "full.md"),
        dl_main,
        dl_full,
    )


def build() -> None:
    with gr.Row():
        session_dd = gr.Dropdown(label=t("セッション"), choices=list_sessions(), scale=3)
        with gr.Column(scale=1):
            refresh_btn = gr.Button(t("🔄 一覧更新"))
            dl_main_btn = gr.DownloadButton(t("⬇ main.md をダウンロード"), value=None, interactive=False)
            dl_full_btn = gr.DownloadButton(t("⬇ full.md をダウンロード"), value=None, interactive=False)
    with gr.Tab(t("📖 メインログ (main.md)")):
        main_md = gr.Markdown(t("(セッション未選択)"))
    with gr.Tab(t("🔍 フルログ (full.md)")):
        full_md = gr.Markdown(t("(セッション未選択)"))

    refresh_btn.click(_refresh, outputs=[session_dd, dl_main_btn, dl_full_btn])
    session_dd.change(_load, inputs=[session_dd], outputs=[main_md, full_md, dl_main_btn, dl_full_btn])
