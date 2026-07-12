"""接続設定タブ: OpenAI互換エンドポイント（OpenRouter/ローカル/OpenAI等）のCRUDと接続テスト。"""
from __future__ import annotations

import re

import gradio as gr
from openai import OpenAI

from korabo.config import load_config, save_config
from korabo.i18n import t
from korabo.schemas import EndpointConfig


def _choices() -> list[str]:
    return list(load_config().endpoints.keys())


def _load(name: str):
    cfg = load_config()
    ep = cfg.endpoints.get(name)
    if ep is None:
        return "", "", "", "", "", "エンドポイントが見つかりません"
    return name, ep.base_url, ep.api_key, ep.api_key_env, ep.default_model, f"「{name}」を読み込みました"


def _new():
    return "", "https://", "", "", "", "新規エンドポイント: 名前を入力して保存してください"


def _save(name: str, base_url: str, api_key: str, api_key_env: str, default_model: str):
    name = (name or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        gr.Warning("名前は英数字・ハイフン・アンダースコアのみで入力してください。")
        return gr.update(), "保存に失敗しました"
    cfg = load_config()
    cfg.endpoints[name] = EndpointConfig(
        base_url=(base_url or "").strip(),
        api_key=(api_key or "").strip(),
        api_key_env=(api_key_env or "").strip(),
        default_model=(default_model or "").strip(),
    )
    save_config(cfg)
    return gr.update(choices=_choices(), value=name), f"「{name}」を保存しました"


def _delete(name: str):
    cfg = load_config()
    if name not in cfg.endpoints:
        gr.Warning("削除対象のエンドポイントが見つかりません。")
        return gr.update(), "削除に失敗しました"
    users = [r.id for r in cfg.roles if r.endpoint == name]
    if cfg.master.endpoint == name:
        users.append("master")
    if users:
        gr.Warning(f"このエンドポイントは {', '.join(users)} が使用中のため削除できません。")
        return gr.update(), "削除に失敗しました"
    del cfg.endpoints[name]
    save_config(cfg)
    return gr.update(choices=_choices(), value=None), f"「{name}」を削除しました"


def _test(name: str):
    cfg = load_config()
    ep = cfg.endpoints.get(name)
    if ep is None:
        return "❌ エンドポイントが見つかりません"
    if ep.base_url.strip().lower() == "mock":
        return "✅ mockエンドポイントは常に利用可能です"
    try:
        client = OpenAI(base_url=ep.base_url, api_key=ep.resolve_api_key() or "no-key", timeout=15.0)
        models = client.models.list()
        ids = [m.id for m in models.data[:10]]
        more = " …" if len(models.data) > 10 else ""
        return f"✅ 接続成功。利用可能モデル（先頭10件）: {', '.join(ids)}{more}"
    except Exception as e:
        return f"❌ 接続失敗: {e}"


def build() -> None:
    with gr.Row():
        with gr.Column(scale=1):
            ep_dd = gr.Dropdown(label=t("エンドポイント一覧"), choices=_choices())
            with gr.Row():
                new_btn = gr.Button(t("➕ 新規"))
                delete_btn = gr.Button(t("🗑 削除"), variant="stop")
        with gr.Column(scale=2):
            name_tb = gr.Textbox(label=t("名前（英数字・-・_）"))
            url_tb = gr.Textbox(label="base_url（\"mock\" でダミー動作）")
            key_tb = gr.Textbox(label=t("APIキー（直接指定）"), type="password")
            env_tb = gr.Textbox(label=t("APIキー環境変数名（直接指定が空のとき使用）"))
            model_tb = gr.Textbox(label=t("既定モデル"))
            with gr.Row():
                save_btn = gr.Button(t("💾 保存"), variant="primary")
                test_btn = gr.Button(t("🔍 接続テスト"))
            status = gr.Markdown("")

    fields = [name_tb, url_tb, key_tb, env_tb, model_tb, status]
    ep_dd.change(_load, inputs=[ep_dd], outputs=fields)
    new_btn.click(_new, outputs=fields)
    save_btn.click(_save, inputs=[name_tb, url_tb, key_tb, env_tb, model_tb], outputs=[ep_dd, status])
    delete_btn.click(_delete, inputs=[name_tb], outputs=[ep_dd, status])
    test_btn.click(_test, inputs=[name_tb], outputs=[status])
