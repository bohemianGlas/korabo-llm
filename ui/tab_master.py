"""マスター設定タブ: マスタープロンプト・重要プロンプト・接続設定・記憶メモ。"""
from __future__ import annotations

from pathlib import Path

import gradio as gr

from korabo.config import load_config, save_config
from korabo.i18n import t
from korabo.memory import master_state_template, read_memory, write_memory
from korabo.prompts import IMPORTANT_PROMPT_TEMPLATE, ensure_important_prompt


def _read_prompt(cfg) -> str:
    p = cfg.master.prompt_file
    return Path(p).read_text(encoding="utf-8") if p and Path(p).exists() else ""


def _read_important(cfg) -> str:
    p = cfg.master.important_prompt_file
    if not p:
        return IMPORTANT_PROMPT_TEMPLATE
    ensure_important_prompt(p)  # 無ければテンプレートを書き込む
    return Path(p).read_text(encoding="utf-8")


def _load():
    cfg = load_config()
    m = cfg.master
    memory = read_memory(m.memory_file) if m.memory_file else ""
    return (
        m.directive,
        _read_prompt(cfg),
        _read_important(cfg),
        gr.update(choices=list(cfg.endpoints.keys()), value=m.endpoint),
        m.model,
        m.temperature,
        m.memory_enabled,
        memory,
        "設定を読み込みました",
    )


def _save(directive: str, prompt: str, important: str, endpoint: str, model: str,
          temperature: float, memory_enabled: bool):
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
    if m.important_prompt_file:
        ip = Path(m.important_prompt_file)
        ip.parent.mkdir(parents=True, exist_ok=True)
        ip.write_text(important or "", encoding="utf-8")
    save_config(cfg)
    return "マスター設定を保存しました"


def _reset_important():
    """重要プロンプトをテンプレートへ戻す（＝未使用状態にする）。"""
    cfg = load_config()
    if cfg.master.important_prompt_file:
        write_memory(cfg.master.important_prompt_file, IMPORTANT_PROMPT_TEMPLATE)
    return IMPORTANT_PROMPT_TEMPLATE, "重要プロンプトをテンプレートに戻しました（未使用状態）"


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
    template = master_state_template(cfg.prompt_lang)
    write_memory(cfg.master.memory_file, template)
    return template, "Masterの記憶をクリアしました"


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
            important_tb = gr.Textbox(
                label=t("重要プロンプト（作品の設計図・Markdown）"),
                lines=14,
                value=_read_important(cfg),
                info=t("テンプレートを埋めると毎ターンMasterの判断基準になります。テンプレートのまま（未記入）なら一切注入されません"),
            )
            important_reset_btn = gr.Button(t("↩ 重要プロンプトをテンプレートに戻す"))
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
        inputs=[directive_tb, prompt_tb, important_tb, ep_dd, model_tb, temp_sl, mem_enabled_cb],
        outputs=[status],
    )
    reload_btn.click(
        _load,
        outputs=[directive_tb, prompt_tb, important_tb, ep_dd, model_tb, temp_sl,
                 mem_enabled_cb, memory_tb, status],
    )
    important_reset_btn.click(_reset_important, outputs=[important_tb, status])
    mem_save_btn.click(_save_memory, inputs=[memory_tb], outputs=[status])
    mem_clear_btn.click(_clear_memory, outputs=[memory_tb, status])
