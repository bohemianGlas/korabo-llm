"""ロール管理タブ: サブLLM（ロール）のCRUDと記憶(memo_md)の閲覧・編集。"""
from __future__ import annotations

import re
from pathlib import Path

import gradio as gr

from korabo.config import load_config, save_config
from korabo.i18n import t
from korabo.memory import read_memory, write_memory
from korabo.schemas import RoleConfig

_DEFAULT_EP = "（既定を使用）"


def _role_choices() -> list[str]:
    return [r.id for r in load_config().roles]


def _endpoint_choices() -> list[str]:
    return [_DEFAULT_EP] + list(load_config().endpoints.keys())


def _load_role(role_id: str):
    cfg = load_config()
    role = cfg.get_role(role_id)
    if role is None:
        return "", "", "", _DEFAULT_EP, "", True, "", "", "ロールが見つかりません"
    prompt = ""
    if role.role_prompt_file and Path(role.role_prompt_file).exists():
        prompt = Path(role.role_prompt_file).read_text(encoding="utf-8")
    memory = read_memory(role.memory_file) if role.memory_file else ""
    ep = role.endpoint or _DEFAULT_EP
    return (
        role.id, role.name, role.faction, ep, role.model,
        role.memory_enabled, prompt, memory, f"「{role.id}」を読み込みました",
    )


def _new_role():
    return "", "", "", _DEFAULT_EP, "", True, "", "", "新規ロール: idを入力して保存してください"


def _save_role(
    role_id: str, name: str, faction: str, endpoint: str, model: str,
    memory_enabled: bool, prompt: str,
):
    role_id = (role_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", role_id):
        gr.Warning("idは英数字・ハイフン・アンダースコアのみで入力してください。")
        return gr.update(), "保存に失敗しました"
    cfg = load_config()
    role = cfg.get_role(role_id)
    if role is None:
        role = RoleConfig(
            id=role_id,
            role_prompt_file=f"data/roles/{role_id}.md",
            memory_file=f"data/memories/{role_id}.md",
        )
        cfg.roles.append(role)
    role.name = (name or "").strip()
    role.faction = (faction or "").strip()
    role.endpoint = "" if endpoint in ("", _DEFAULT_EP, None) else endpoint
    role.model = (model or "").strip()
    role.memory_enabled = bool(memory_enabled)

    Path(role.role_prompt_file).parent.mkdir(parents=True, exist_ok=True)
    Path(role.role_prompt_file).write_text(prompt or "", encoding="utf-8")
    if role.memory_file and not Path(role.memory_file).exists():
        write_memory(role.memory_file, f"# {role.name or role.id} の記憶メモ\n")

    save_config(cfg)
    return gr.update(choices=_role_choices(), value=role_id), f"「{role_id}」を保存しました"


def _delete_role(role_id: str):
    cfg = load_config()
    role = cfg.get_role(role_id)
    if role is None:
        gr.Warning("削除対象のロールが見つかりません。")
        return gr.update(), "削除に失敗しました"
    cfg.roles = [r for r in cfg.roles if r.id != role_id]
    save_config(cfg)
    return (
        gr.update(choices=_role_choices(), value=None),
        f"「{role_id}」を設定から削除しました（プロンプト・記憶ファイルは残っています）",
    )


def _save_memory(role_id: str, memory_text: str):
    cfg = load_config()
    role = cfg.get_role(role_id)
    if role is None or not role.memory_file:
        gr.Warning("ロールが選択されていないか、記憶ファイルが未設定です。")
        return "保存に失敗しました"
    write_memory(role.memory_file, memory_text or "")
    return f"「{role_id}」の記憶を保存しました"


def _clear_memory(role_id: str):
    cfg = load_config()
    role = cfg.get_role(role_id)
    if role is None or not role.memory_file:
        gr.Warning("ロールが選択されていないか、記憶ファイルが未設定です。")
        return gr.update(), "クリアに失敗しました"
    header = f"# {role.name or role.id} の記憶メモ\n"
    write_memory(role.memory_file, header)
    return header, f"「{role_id}」の記憶をクリアしました"


def _refresh():
    return gr.update(choices=_role_choices()), gr.update(choices=_endpoint_choices())


def build() -> None:
    with gr.Row():
        with gr.Column(scale=1):
            role_dd = gr.Dropdown(label=t("ロール一覧"), choices=_role_choices())
            with gr.Row():
                new_btn = gr.Button(t("➕ 新規"))
                refresh_btn = gr.Button(t("🔄 一覧更新"))
                delete_btn = gr.Button(t("🗑 削除"), variant="stop")
            role_id = gr.Textbox(label=t("id（英数字・-・_）"))
            role_name = gr.Textbox(label=t("名前（表示名）"))
            role_faction = gr.Textbox(
                label=t("陣営（空欄=設定なし・影響なし）"),
                placeholder="例: A / B / C ／ 反乱軍 など",
            )
            role_ep = gr.Dropdown(label=t("エンドポイント"), choices=_endpoint_choices(), value=_DEFAULT_EP)
            role_model = gr.Textbox(label=t("モデル（空欄なら既定値）"))
            role_mem_enabled = gr.Checkbox(
                label=t("記憶機能を有効にする"),
                value=True,
                info=t("OFFにするとこのロールは記憶を読み書きしません"),
            )
            save_btn = gr.Button(t("💾 ロールを保存"), variant="primary")
            status = gr.Markdown("")
        with gr.Column(scale=2):
            prompt_tb = gr.Textbox(label=t("ロールプロンプト（Markdown）"), lines=14)
            memory_tb = gr.Textbox(label=t("記憶メモ (memo_md)"), lines=10)
            with gr.Row():
                mem_save_btn = gr.Button(t("💾 記憶を保存"))
                mem_clear_btn = gr.Button(t("🧹 記憶をクリア"))

    fields = [
        role_id, role_name, role_faction, role_ep, role_model,
        role_mem_enabled, prompt_tb, memory_tb, status,
    ]
    role_dd.change(_load_role, inputs=[role_dd], outputs=fields)
    new_btn.click(_new_role, outputs=fields)
    refresh_btn.click(_refresh, outputs=[role_dd, role_ep])
    save_btn.click(
        _save_role,
        inputs=[role_id, role_name, role_faction, role_ep, role_model, role_mem_enabled, prompt_tb],
        outputs=[role_dd, status],
    )
    delete_btn.click(_delete_role, inputs=[role_id], outputs=[role_dd, status])
    mem_save_btn.click(_save_memory, inputs=[role_id, memory_tb], outputs=[status])
    mem_clear_btn.click(_clear_memory, inputs=[role_id], outputs=[memory_tb, status])
