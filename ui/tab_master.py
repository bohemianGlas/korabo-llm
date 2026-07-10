"""マスター設定タブ: マスタープロンプトとMasterLLMの接続設定。"""
from __future__ import annotations

from pathlib import Path

import gradio as gr

from korabo.config import load_config, save_config
from korabo.i18n import t


def _load():
    cfg = load_config()
    m = cfg.master
    prompt = ""
    if m.prompt_file and Path(m.prompt_file).exists():
        prompt = Path(m.prompt_file).read_text(encoding="utf-8")
    return (
        prompt,
        gr.update(choices=list(cfg.endpoints.keys()), value=m.endpoint),
        m.model,
        m.temperature,
        "設定を読み込みました",
    )


def _save(prompt: str, endpoint: str, model: str, temperature: float):
    cfg = load_config()
    m = cfg.master
    if endpoint:
        m.endpoint = endpoint
    m.model = (model or "").strip()
    m.temperature = float(temperature)
    p = Path(m.prompt_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(prompt or "", encoding="utf-8")
    save_config(cfg)
    return "マスター設定を保存しました"


def build() -> None:
    cfg = load_config()
    with gr.Row():
        with gr.Column(scale=2):
            prompt_tb = gr.Textbox(
                label=t("マスタープロンプト（Markdown）"),
                lines=20,
                value=(
                    Path(cfg.master.prompt_file).read_text(encoding="utf-8")
                    if Path(cfg.master.prompt_file).exists()
                    else ""
                ),
            )
        with gr.Column(scale=1):
            ep_dd = gr.Dropdown(
                label=t("エンドポイント"),
                choices=list(cfg.endpoints.keys()),
                value=cfg.master.endpoint,
            )
            model_tb = gr.Textbox(label=t("モデル（空欄ならエンドポイントの既定値）"), value=cfg.master.model)
            temp_sl = gr.Slider(label="temperature", minimum=0.0, maximum=2.0, step=0.05, value=cfg.master.temperature)
            with gr.Row():
                save_btn = gr.Button(t("💾 保存"), variant="primary")
                reload_btn = gr.Button(t("🔄 再読込"))
            status = gr.Markdown("")

    save_btn.click(_save, inputs=[prompt_tb, ep_dd, model_tb, temp_sl], outputs=[status])
    reload_btn.click(_load, outputs=[prompt_tb, ep_dd, model_tb, temp_sl, status])
