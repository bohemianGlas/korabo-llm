"""詳細ログタブ: 過去セッションの main.md / full.md を閲覧。"""
from __future__ import annotations

import gradio as gr

from korabo.i18n import t
from korabo.logger import list_sessions, read_session_file


def _refresh():
    sessions = list_sessions()
    return gr.update(choices=sessions, value=sessions[0] if sessions else None)


def _load(session_id: str):
    if not session_id:
        return t("(セッション未選択)"), t("(セッション未選択)")
    return (
        read_session_file(session_id, "main.md"),
        read_session_file(session_id, "full.md"),
    )


def build() -> None:
    with gr.Row():
        session_dd = gr.Dropdown(label=t("セッション"), choices=list_sessions(), scale=3)
        refresh_btn = gr.Button(t("🔄 一覧更新"), scale=1)
    with gr.Tab(t("📖 メインログ (main.md)")):
        main_md = gr.Markdown(t("(セッション未選択)"))
    with gr.Tab(t("🔍 フルログ (full.md)")):
        full_md = gr.Markdown(t("(セッション未選択)"))

    refresh_btn.click(_refresh, outputs=[session_dd])
    session_dd.change(_load, inputs=[session_dd], outputs=[main_md, full_md])
