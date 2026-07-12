"""設定タブ: 言語などのオプション設定。将来のオプション追加も想定した構成。

ここに新しい設定を追加するときは、`build()` 内に `gr.Group()` の節を足していく。
即時反映でよい設定はその場で保存、UI全体の再構築が要る設定（言語など）は
`appcontrol.schedule_restart()` ＋ `RECONNECT_JS` で再起動して反映する。
"""
from __future__ import annotations

import gradio as gr

from korabo import appcontrol, i18n
from korabo.config import load_config, save_config


def _apply_language(lang: str) -> None:
    """選択言語を config に保存し、新しい言語でUIを再構築するため再起動する。"""
    cfg = load_config()
    cfg.ui_lang = lang if lang in i18n.LANGS else "ja"
    save_config(cfg)
    appcontrol.schedule_restart()


def _apply_prompt_lang(lang: str) -> str:
    """システム指示プロンプトの言語を config に保存する（次回セッション開始から反映・再起動不要）。"""
    cfg = load_config()
    cfg.prompt_lang = "en" if str(lang).lower().startswith("en") else "ja"
    save_config(cfg)
    return i18n.t("保存しました（次に「開始」したセッションから反映されます）")


def build() -> None:
    t = i18n.t
    gr.Markdown(f"## {t('⚙ 設定')}")

    # --- 言語 ---
    with gr.Group():
        lang_dd = gr.Dropdown(
            label=t("言語 / Language"),
            choices=[("English", "en"), ("Japanese", "ja")],
            value=i18n.get_lang(),
        )
        apply_btn = gr.Button(t("APPLY"), variant="primary")
    gr.Markdown(t("※ 言語の変更は、適用時にアプリを再起動して反映されます。"))

    # --- システム指示プロンプトの言語（出力言語とは独立） ---
    with gr.Group():
        cfg0 = load_config()
        prompt_lang_dd = gr.Dropdown(
            label=t("システム指示プロンプトの言語"),
            choices=[("日本語 / Japanese", "ja"), ("English", "en")],
            value=getattr(cfg0, "prompt_lang", "ja"),
            info=t("Master/Subへの共通指示・出力形式の言語。物語の出力言語とは独立（作品プロンプト側で指定）"),
        )
        prompt_lang_btn = gr.Button(t("💾 保存"))
        prompt_lang_status = gr.Markdown("")

    # 将来のオプションはこの下に gr.Group() を足していく（例: テーマ、既定モデル 等）

    apply_btn.click(_apply_language, inputs=[lang_dd]).then(None, js=appcontrol.RECONNECT_JS)
    prompt_lang_btn.click(_apply_prompt_lang, inputs=[prompt_lang_dd], outputs=[prompt_lang_status])
