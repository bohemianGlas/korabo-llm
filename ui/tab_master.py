"""マスター設定タブ: マスタープロンプト・接続設定・記憶メモ。"""
from __future__ import annotations

from pathlib import Path

import gradio as gr

from korabo.config import load_config, save_config
from korabo.i18n import t
from korabo.memory import read_memory, write_memory


def _read_prompt(cfg) -> str:
    p = cfg.master.prompt_file
    return Path(p).read_text(encoding="utf-8") if p and Path(p).exists() else ""


def _load():
    cfg = load_config()
    m = cfg.master
    memory = read_memory(m.memory_file) if m.memory_file else ""
    return (
        m.directive,
        _read_prompt(cfg),
        gr.update(choices=list(cfg.endpoints.keys()), value=m.endpoint),
        m.model,
        m.temperature,
        m.memory_enabled,
        memory,
        "設定を読み込みました",
    )


def _save(directive: str, prompt: str, endpoint: str, model: str, temperature: float, memory_enabled: bool):
    cfg = load_config()
    m = cfg.master
    m.directive = directive or ""
    if endpoint:
        m.endpoint = endpoint
    m.model = (model or "").strip()
    m.temperature = float(temperature)
    m.memory_enabled = bool(memory_enabled)
    p = Path(m.prompt_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(prompt or "", encoding="utf-8")
    save_config(cfg)
    return "マスター設定を保存しました"


def _save_memory(memory_text: str):
    cfg = load_config()
    if not cfg.master.memory_file:
        gr.Warning("Masterの記憶ファイルが未設定です。")
        return "保存に失敗しました"
    write_memory(cfg.master.memory_file, memory_text or "")
    return "Masterの記憶を保存しました"


def _clear_memory():
    cfg = load_config()
    if not cfg.master.memory_file:
        gr.Warning("Masterの記憶ファイルが未設定です。")
        return gr.update(), "クリアに失敗しました"
    header = "# 語り手（Master）の記憶メモ\n"
    write_memory(cfg.master.memory_file, header)
    return header, "Masterの記憶をクリアしました"


def build() -> None:
    cfg = load_config()
    with gr.Row():
        with gr.Column(scale=2):
            directive_tb = gr.Textbox(
                label=t("⭐ 最優先指令（絶対厳守・Markdown）"),
                lines=5,
                value=cfg.master.directive,
                placeholder=t("例: - 登場人物を死なせない\n- 一次資料に無い固有名詞を捏造しない"),
                info=t("systemの最上位に前置され、他のすべての指示より優先されます（空欄で無効）"),
            )
            prompt_tb = gr.Textbox(
                label=t("マスタープロンプト（Markdown）"),
                lines=14,
                value=_read_prompt(cfg),
            )
            mem_enabled_cb = gr.Checkbox(
                label=t("Masterの記憶機能を有効にする"),
                value=cfg.master.memory_enabled,
                info=t("有効にするとMasterが記憶メモを読み書きします（設定・伏線・決定事項の保持）"),
            )
            memory_tb = gr.Textbox(
                label=t("Masterの記憶メモ (memo_md)"),
                lines=8,
                value=read_memory(cfg.master.memory_file) if cfg.master.memory_file else "",
            )
            with gr.Row():
                mem_save_btn = gr.Button(t("💾 記憶を保存"))
                mem_clear_btn = gr.Button(t("🧹 記憶をクリア"))
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

    save_btn.click(
        _save,
        inputs=[directive_tb, prompt_tb, ep_dd, model_tb, temp_sl, mem_enabled_cb],
        outputs=[status],
    )
    reload_btn.click(
        _load,
        outputs=[directive_tb, prompt_tb, ep_dd, model_tb, temp_sl, mem_enabled_cb, memory_tb, status],
    )
    mem_save_btn.click(_save_memory, inputs=[memory_tb], outputs=[status])
    mem_clear_btn.click(_clear_memory, outputs=[memory_tb, status])
