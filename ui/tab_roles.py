"""ロール管理タブ: サブLLM（ロール）のCRUDと記憶(memo_md)の閲覧・編集。

Sub LLM（endpoint / model / temperature）は各ロールが自分で保持する。
- 「全ロールへ一括適用」: 上部フォームの値を全ロールへ一斉に書き込む（一括切り替え）
- temperature はロード編集欄でキャラクターごとにも設定できる
（endpoint / model は一括適用で全ロール共通に揃える運用。個別変更は config で可）
"""
from __future__ import annotations

import re
from pathlib import Path

import gradio as gr

from korabo.config import load_config, save_config
from korabo.i18n import t
from korabo.memory import memory_template, read_memory, write_memory
from korabo.schemas import RoleConfig

_DEFAULT_TEMP = 0.8


def _role_choices() -> list[str]:
    return [r.id for r in load_config().roles]


def _endpoint_choices() -> list[str]:
    return list(load_config().endpoints.keys())


def _current_sub_endpoint(cfg) -> str:
    """一括フォームの初期表示用: 先頭ロールの endpoint（無ければ mock/先頭）。"""
    if cfg.roles and cfg.roles[0].endpoint:
        return cfg.roles[0].endpoint
    return "mock" if "mock" in cfg.endpoints else next(iter(cfg.endpoints), "")


def _load_role(role_id: str):
    cfg = load_config()
    role = cfg.get_role(role_id)
    if role is None:
        return "", "", "", True, _DEFAULT_TEMP, "", "", "ロールが見つかりません"
    prompt = ""
    if role.role_prompt_file and Path(role.role_prompt_file).exists():
        prompt = Path(role.role_prompt_file).read_text(encoding="utf-8")
    memory = read_memory(role.memory_file) if role.memory_file else ""
    temp = role.temperature if role.temperature is not None else _DEFAULT_TEMP
    return (
        role.id, role.name, role.faction, role.memory_enabled, temp,
        prompt, memory, f"「{role.id}」を読み込みました",
    )


def _new_role():
    return "", "", "", True, _DEFAULT_TEMP, "", "", "新規ロール: idを入力して保存してください"


def _save_role(role_id: str, name: str, faction: str, memory_enabled: bool,
               temperature: float, prompt: str):
    role_id = (role_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", role_id):
        gr.Warning("idは英数字・ハイフン・アンダースコアのみで入力してください。")
        return gr.update(), "保存に失敗しました"
    cfg = load_config()
    role = cfg.get_role(role_id)
    is_new = role is None
    if is_new:
        role = RoleConfig(
            id=role_id,
            role_prompt_file=f"data/roles/{role_id}.md",
            memory_file=f"data/memories/{role_id}.md",
        )
        # 新規ロールは endpoint/model を既存ロール（＝共通設定）から引き継ぐ
        if cfg.roles:
            role.endpoint = cfg.roles[0].endpoint
            role.model = cfg.roles[0].model
        elif "mock" in cfg.endpoints:
            role.endpoint = "mock"
        cfg.roles.append(role)
    role.name = (name or "").strip()
    role.faction = (faction or "").strip()
    role.memory_enabled = bool(memory_enabled)
    role.temperature = float(temperature)  # temperature はキャラごとに保持

    Path(role.role_prompt_file).parent.mkdir(parents=True, exist_ok=True)
    Path(role.role_prompt_file).write_text(prompt or "", encoding="utf-8")
    if role.memory_file and not Path(role.memory_file).exists():
        write_memory(role.memory_file, memory_template(role.name or role.id, cfg.prompt_lang))

    save_config(cfg)
    return gr.update(choices=_role_choices(), value=role_id), f"「{role_id}」を保存しました"


def _apply_sub_llm(endpoint: str, model: str, temperature: float, apply_temp: bool):
    """全ロールへ Sub LLM を一括適用する。

    endpoint / model は常に全ロールへ揃える。temperature は apply_temp=True のときだけ
    全ロールへ上書きする（False ならキャラごとの個別値を保持）。
    """
    cfg = load_config()
    if not cfg.roles:
        gr.Warning("ロールがありません。先にロールを作成してください。")
        return "適用対象のロールがありません"
    ep = (endpoint or "").strip()
    md = (model or "").strip()
    for r in cfg.roles:
        r.endpoint = ep
        r.model = md
        if apply_temp:
            r.temperature = float(temperature)
    save_config(cfg)
    tnote = f"／temperature={float(temperature):.2f} も一括適用" if apply_temp else "／temperatureは各キャラの値を保持"
    return f"全 {len(cfg.roles)} ロールに Sub LLM「{ep} / {md or '既定モデル'}」を適用しました{tnote}"


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
    template = memory_template(role.name or role.id, cfg.prompt_lang)
    write_memory(role.memory_file, template)
    return template, f"「{role_id}」の記憶をクリアしました"


def _refresh():
    cfg = load_config()
    return (
        gr.update(choices=_role_choices()),
        gr.update(choices=_endpoint_choices(), value=_current_sub_endpoint(cfg) or None),
    )


def build() -> None:
    cfg = load_config()
    # --- 全ロール共通の Sub LLM（一括切り替え） ---
    with gr.Group():
        gr.Markdown(t("### 🎛 Sub LLM（全ロールへ一括適用）"))
        with gr.Row():
            sub_ep = gr.Dropdown(
                label=t("エンドポイント"),
                choices=_endpoint_choices(),
                value=_current_sub_endpoint(cfg) or None,
                scale=2,
            )
            sub_model = gr.Textbox(
                label=t("モデル（空欄ならエンドポイントの既定値）"),
                value=(cfg.roles[0].model if cfg.roles else ""),
                scale=2,
            )
            sub_temp = gr.Slider(
                label="temperature", minimum=0.0, maximum=2.0, step=0.05,
                value=(cfg.roles[0].temperature if cfg.roles and cfg.roles[0].temperature is not None else _DEFAULT_TEMP),
                scale=1,
            )
        sub_apply_temp = gr.Checkbox(
            label=t("temperature も一括適用する（OFFならキャラごとの値を保持）"),
            value=True,
        )
        sub_apply_btn = gr.Button(t("💾 全ロールに適用（Sub LLMを一括設定）"), variant="primary")
        sub_status = gr.Markdown(t("endpoint・model は全ロール共通。temperature は一括／キャラごとの両方で設定できます。"))

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
            role_temp = gr.Slider(
                label=t("temperature（このキャラクター）"),
                minimum=0.0, maximum=2.0, step=0.05, value=_DEFAULT_TEMP,
                info=t("このキャラだけの生成温度。上の一括適用でも上書きできます"),
            )
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

    fields = [role_id, role_name, role_faction, role_mem_enabled, role_temp, prompt_tb, memory_tb, status]
    role_dd.change(_load_role, inputs=[role_dd], outputs=fields)
    new_btn.click(_new_role, outputs=fields)
    refresh_btn.click(_refresh, outputs=[role_dd, sub_ep])
    sub_apply_btn.click(
        _apply_sub_llm,
        inputs=[sub_ep, sub_model, sub_temp, sub_apply_temp],
        outputs=[sub_status],
    )
    save_btn.click(
        _save_role,
        inputs=[role_id, role_name, role_faction, role_mem_enabled, role_temp, prompt_tb],
        outputs=[role_dd, status],
    )
    delete_btn.click(_delete_role, inputs=[role_id], outputs=[role_dd, status])
    mem_save_btn.click(_save_memory, inputs=[role_id, memory_tb], outputs=[status])
    mem_clear_btn.click(_clear_memory, inputs=[role_id], outputs=[memory_tb, status])
