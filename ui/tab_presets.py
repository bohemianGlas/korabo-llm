"""プリセットタブ: マスター/ロール/記憶の「作品一式」を一括で保存・切替する。"""
from __future__ import annotations

import gradio as gr

from korabo import appcontrol
from korabo.i18n import t
from korabo.presets import (
    active_preset_id,
    apply_preset,
    export_preset_bundle,
    import_preset_bundle,
    list_presets,
    save_current_as_preset,
)

# 適用はUI全体（各タブの内容）の再構築＝サーバ再起動が必要。復帰をポーリングして再接続。
_RELOAD_JS = appcontrol.RECONNECT_JS


def _choices() -> list[tuple[str, str]]:
    # gr.Dropdown は (label, value) のタプルを choices に取れる
    return [(name, pid) for pid, name in list_presets()]


def _status_text() -> str:
    active = active_preset_id()
    where = f"プリセット **{active}**" if active else "**custom（data/ 直下の構成）**"
    return f"現在アクティブ: {where}"


def _apply(preset_id: str):
    if not preset_id:
        gr.Warning("適用するプリセットを選択してください。")
        return _status_text()
    try:
        msg = apply_preset(preset_id)
        gr.Info(msg + "（アプリを再起動して反映します）")
        appcontrol.schedule_restart()
    except Exception as e:
        gr.Warning(f"適用に失敗しました: {e}")
    return _status_text()


def _save(preset_id: str, display_name: str):
    try:
        msg = save_current_as_preset(preset_id, display_name)
        gr.Info(msg)
    except Exception as e:
        gr.Warning(f"保存に失敗しました: {e}")
        return gr.update(), _status_text()
    return gr.update(choices=_choices(), value=(preset_id or "").strip()), _status_text()


def _refresh():
    return gr.update(choices=_choices()), _status_text()


def _export(preset_id: str):
    if not preset_id:
        gr.Warning("エクスポートするプリセットを選択してください。")
        return None
    try:
        path = export_preset_bundle(preset_id)
        gr.Info(f"バンドルを書き出しました: {path.name}")
        return str(path)
    except Exception as e:
        gr.Warning(f"エクスポートに失敗しました: {e}")
        return None


def _import(bundle_path: str, preset_id: str):
    if not bundle_path:
        gr.Warning("インポートするバンドルファイルを選択してください。")
        return gr.update(), _status_text()
    try:
        pid, msg = import_preset_bundle(bundle_path, preset_id or "")
        gr.Info(msg + "（適用するには一覧から選んで『適用』してください）")
    except Exception as e:
        gr.Warning(f"インポートに失敗しました: {e}")
        return gr.update(), _status_text()
    return gr.update(choices=_choices(), value=pid), _status_text()


def build() -> None:
    gr.Markdown(
        "作品一式（マスタープロンプト＋include子ファイル・ロール・記憶・味付け）を"
        "プリセットとして保存し、まとめて切り替えます。"
        "**接続先（URL・APIキー）は切り替わりません**（マシン設定として保持）。"
    )
    status = gr.Markdown(_status_text())
    with gr.Row():
        with gr.Column():
            gr.Markdown(t("### ▶ プリセットを適用"))
            preset_dd = gr.Dropdown(label=t("プリセット"), choices=_choices())
            with gr.Row():
                apply_btn = gr.Button(t("▶ 適用（再読み込み）"), variant="primary")
                refresh_btn = gr.Button(t("🔄 一覧更新"))
        with gr.Column():
            gr.Markdown(t("### 💾 現在の構成をプリセットとして保存"))
            new_id = gr.Textbox(label=t("プリセットid（英数字・-・_）"), placeholder="例: mint_mansion")
            new_name = gr.Textbox(label=t("表示名"), placeholder="例: 薄荷館ミステリ")
            save_btn = gr.Button(t("💾 現在の構成を保存"))

    gr.Markdown("---\n### 📦 バンドル（単一ファイル）でのエクスポート/インポート")
    gr.Markdown(
        "作品一式を1つの `.preset.md`（可読なMarkdown）として書き出し・取り込みできます（共有・バックアップ用）。"
        "**接続先（URL・APIキー）は含まれません。**"
    )
    with gr.Row():
        with gr.Column():
            gr.Markdown(t("#### 📤 エクスポート"))
            export_btn = gr.Button(t("📤 選択中のプリセットをバンドル化"))
            export_file = gr.File(label=t("ダウンロード（生成された .preset.md）"))
        with gr.Column():
            gr.Markdown(t("#### 📥 インポート"))
            import_file = gr.File(label=t("バンドル(.preset.md)をアップロード"), type="filepath")
            import_id = gr.Textbox(label=t("取り込み先id（空欄ならファイル名から）"), placeholder="例: mint_mansion")
            import_btn = gr.Button(t("📥 インポート"))

    # js を入力付きイベントに直付けするとJSの戻り値が入力を上書きするため、.then で分離する
    apply_btn.click(_apply, inputs=[preset_dd], outputs=[status]).then(None, js=_RELOAD_JS)
    refresh_btn.click(_refresh, outputs=[preset_dd, status])
    save_btn.click(_save, inputs=[new_id, new_name], outputs=[preset_dd, status])
    export_btn.click(_export, inputs=[preset_dd], outputs=[export_file])
    import_btn.click(_import, inputs=[import_file, import_id], outputs=[preset_dd, status])
