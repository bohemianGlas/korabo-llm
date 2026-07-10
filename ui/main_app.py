"""Gradioアプリの組み立て。"""
from __future__ import annotations

import gradio as gr

from korabo import i18n
from korabo.config import load_config

from . import (
    tab_endpoints,
    tab_logs,
    tab_master,
    tab_presets,
    tab_roles,
    tab_run,
    tab_settings,
)

# 「⚙ 設定」タブをタブ列の右端へ寄せる（メインのタブ列のみ・入れ子タブには影響しない）。
# Gradio 6 では Blocks(css=) が非推奨のため <style> を gr.HTML で注入する。
_CSS = (
    "<style>"
    ".main-tabs > div > div[role='tablist'] > button[role='tab']:last-child"
    " { margin-left: auto; }"
    "</style>"
)


def build_app() -> gr.Blocks:
    # 現在の言語を適用してからUIを組み立てる（言語切替は 設定タブ→APPLY→再起動で反映）
    i18n.set_lang(load_config().ui_lang)
    t = i18n.t

    with gr.Blocks(title="korabo_llm") as demo:
        gr.HTML(_CSS)
        gr.Markdown(f"# {t('🤝 korabo_llm — マスターLLM × サブLLM コラボレーション')}")
        with gr.Tabs(elem_classes=["main-tabs"]):
            with gr.Tab(t("▶ 実行")):
                tab_run.build()
            with gr.Tab(t("📜 詳細ログ")):
                tab_logs.build()
            with gr.Tab(t("🎭 ロール管理")):
                tab_roles.build()
            with gr.Tab(t("🧠 マスター設定")):
                tab_master.build()
            with gr.Tab(t("🔌 接続設定")):
                tab_endpoints.build()
            with gr.Tab(t("🎁 プリセット")):
                tab_presets.build()
            with gr.Tab(t("⚙ 設定")):  # ← 右端に寄せる（_CSS）
                tab_settings.build()

        # ページ/タブを閉じる・リロードする際にブラウザ標準の離脱確認ダイアログを出す
        demo.load(
            fn=None,
            js="""
            () => {
                window.addEventListener('beforeunload', (e) => {
                    e.preventDefault();
                    e.returnValue = '';
                });
            }
            """,
        )
    return demo
