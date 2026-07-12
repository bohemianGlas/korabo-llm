"""WebUIの軽量i18n（日英切替）。

方式: 日本語文字列をキーにして英語訳を引く。未登録なら日本語のまま返す
（＝安全なフォールバック。翻訳漏れでもクラッシュせず段階的に整備できる）。
言語切替はページ再読込で全UIを再構築する（build_app が現在言語で組み立てる）。
"""
from __future__ import annotations

LANGS = {"ja": "日本語", "en": "English"}

_LANG = "ja"


def set_lang(lang: str) -> None:
    global _LANG
    _LANG = lang if lang in LANGS else "ja"


def get_lang() -> str:
    return _LANG


# 日本語 → 英語。ここに無い文字列は日本語のまま表示される。
_EN: dict[str, str] = {
    # アプリ全体 / タブ
    "🤝 korabo_llm — マスターLLM × サブLLM コラボレーション":
        "🤝 korabo_llm — Master LLM × Sub LLM Collaboration",
    "言語 / Language": "言語 / Language",
    "▶ 実行": "▶ Run",
    "📜 詳細ログ": "📜 Logs",
    "🎭 ロール管理": "🎭 Roles",
    "🧠 マスター設定": "🧠 Master",
    "🔌 接続設定": "🔌 Endpoints",
    "🎁 プリセット": "🎁 Presets",
    "⚙ 設定": "⚙ Setting",

    # 設定タブ
    "APPLY": "APPLY",
    "※ 言語の変更は、適用時にアプリを再起動して反映されます。":
        "Note: applying a language change restarts the app to take effect.",
    "システム指示プロンプトの言語": "System-instruction prompt language",
    "Master/Subへの共通指示・出力形式の言語。物語の出力言語とは独立（作品プロンプト側で指定）":
        "Language of the common Master/Sub instructions and output format. Independent of the story's output language (set that in the work prompts)",
    "保存しました（次に「開始」したセッションから反映されます）":
        "Saved (takes effect from the next session you start)",

    # 実行タブ
    "シチュエーションプロンプト": "Situation prompt",
    "文体・方向性（作品全体のトーン）": "Style & direction (overall tone)",
    "叙述スタイル（Masterの編纂形式）": "Narrative style (how Master composes)",
    "視点ロール（一人称）": "POV role (first person)",
    "カスタム叙述指示": "Custom narrative instruction",
    "実行モード": "Run mode",
    "ターン上限": "Turn limit",
    "目指すmain.md文字数（0で無効）": "Target main.md length in chars (0 = off)",
    "Masterがこの分量を目安に配分・収束します（ターン上限とは別）":
        "Master paces and wraps up toward this length (separate from turn limit)",
    "続き生成・実行中変更では「現在から追加Nターン」として扱われます":
        "For continue / live-change, this is 'N more turns from now'",
    "サブの生のセリフ・心情もメインログに反映（OFFならMaster編纂のみ）":
        "Also put raw sub dialogue/feelings into the main log (off = Master's prose only)",
    "└ ロール名見出し（**名前**）を付ける": "└ Add role-name heading (**name**)",
    "└ 仕草・行動(action)を含める": "└ Include gesture/action",
    "└ （心の声）を含める": "└ Include (inner voice)",
    "心の声の接頭辞": "Inner-voice prefix",
    "空欄で接頭辞なし": "empty = no prefix",
    "サブ（キャラ）の記憶機能を有効にする（全ロール共通）":
        "Enable sub (character) memory (all roles)",
    "OFFにすると全ロールが記憶を読み書きしません（個別ONでも全体OFFが優先）":
        "Off = no role reads/writes memory (global off overrides per-role on)",
    "セリフだけを載せたい場合は、これをONにして下の3つ（名前・仕草・心の声）をすべてOFF":
        "For dialogue only: turn this ON and turn OFF all three below (name, action, inner voice)",
    "▶ 開始": "▶ Start",
    "⏭ 1ステップ": "⏭ Step",
    "⏸ 一時停止": "⏸ Pause",
    "⏵ 再開": "⏵ Resume",
    "⏹ 停止": "⏹ Stop",
    "⏩ 続きを生成（この設定で）": "⏩ Continue (with these settings)",
    "🔧 実行設定を変更（実行中）": "🔧 Change run settings (while running)",
    "ユーザー介入（実行中に送信可能）": "User intervention (can send while running)",
    "⚡ 介入を送信": "⚡ Send intervention",
    "### 📖 メインログ（Masterの編纂結果）": "### 📖 Main log (Master's composition)",
    "（まだ出力がありません）": "(no output yet)",
    "🔍 詳細ストリーム（Master思考・Sub応答・記憶更新）":
        "🔍 Detail stream (Master thoughts, sub replies, memory updates)",
    "（まだイベントがありません）": "(no events yet)",
    "📊 トークン使用量（モデルごと・合計）": "📊 Token usage (per model / total)",
    "（トークン使用量はまだありません）": "(no token usage yet)",
    "#### 🎚 作品の味付け（ラベルは自由に編集可 / 値 1〜10・高いほど強い）":
        "#### 🎚 Flavor dials (labels editable / value 1-10, higher = stronger)",

    # 実行モード（表示ラベル）
    "1ステップずつ": "One step at a time",
    "指定ステップまで実行": "Run until N turns",
    "Master判断で停止（上限あり）": "Master decides to stop (with limit)",
    "Master判断で停止（無限）": "Master decides to stop (unlimited)",
    "無限モード": "Infinite mode",

    # 叙述スタイル（表示ラベル）
    "三人称小説": "Third-person novel",
    "一人称小説（視点ロールを選択）": "First-person novel (pick POV role)",
    "台本・戯曲風": "Screenplay / script",
    "カスタム（自由記述）": "Custom (free text)",

    # 状態バナー
    "準備中": "Idle",
    "実行中": "Running",
    "一時停止中": "Paused",
    "完了": "Finished",
    "停止済み": "Stopped",
    "エラーで一時停止": "Paused on error",
    "セッション未開始": "No session yet",

    # 状態バナーのメタ
    "モード": "Mode",
    "ターン": "Turn",

    # 詳細ログタブ
    "セッション": "Session",
    "🔄 一覧更新": "🔄 Refresh list",
    "⬇ main.md をダウンロード": "⬇ Download main.md",
    "⬇ full.md をダウンロード": "⬇ Download full.md",
    "📖 メインログ (main.md)": "📖 Main log (main.md)",
    "🔍 フルログ (full.md)": "🔍 Full log (full.md)",
    "(セッション未選択)": "(no session selected)",

    # ロール管理タブ
    "### 🎛 Sub LLM（全ロールへ一括適用）": "### 🎛 Sub LLM (apply to all roles at once)",
    "💾 全ロールに適用（Sub LLMを一括設定）": "💾 Apply to all roles (set Sub LLM at once)",
    "temperature も一括適用する（OFFならキャラごとの値を保持）":
        "Also apply temperature to all (off = keep each character's value)",
    "endpoint・model は全ロール共通。temperature は一括／キャラごとの両方で設定できます。":
        "endpoint & model are shared by all roles; temperature can be set both at once and per character.",
    "temperature（このキャラクター）": "temperature (this character)",
    "このキャラだけの生成温度。上の一括適用でも上書きできます":
        "Sampling temperature for this character only; can also be overwritten by the bulk apply above",
    "ロール一覧": "Roles",
    "➕ 新規": "➕ New",
    "🗑 削除": "🗑 Delete",
    "id（英数字・-・_）": "id (alphanumeric, -, _)",
    "名前（表示名）": "Name (display)",
    "陣営（空欄=設定なし・影響なし）": "Faction (blank = none / no effect)",
    "エンドポイント": "Endpoint",
    "モデル（空欄なら既定値）": "Model (blank = default)",
    "💾 ロールを保存": "💾 Save role",
    "ロールプロンプト（Markdown）": "Role prompt (Markdown)",
    "記憶メモ (memo_md)": "Memory note (memo_md)",
    "💾 記憶を保存": "💾 Save memory",
    "🧹 記憶をクリア": "🧹 Clear memory",
    "記憶機能を有効にする": "Enable memory",
    "OFFにするとこのロールは記憶を読み書きしません":
        "Off = this role does not read/write memory",

    # マスター設定タブ
    "マスタープロンプト（Markdown）": "Master prompt (Markdown)",
    "モデル（空欄ならエンドポイントの既定値）": "Model (blank = endpoint default)",
    "💾 保存": "💾 Save",
    "🔄 再読込": "🔄 Reload",
    "⭐ 最優先指令（絶対厳守・Markdown）": "⭐ Top-priority directive (must obey, Markdown)",
    "例: - 登場人物を死なせない\n- 一次資料に無い固有名詞を捏造しない":
        "e.g. - Never kill off characters\n- Do not invent proper nouns absent from sources",
    "systemの最上位に前置され、他のすべての指示より優先されます（空欄で無効）":
        "Prepended at the very top of the system prompt, overriding all other instructions (blank = off)",
    "重要プロンプト（作品の設計図・Markdown）": "Key prompt (story blueprint, Markdown)",
    "テンプレートを埋めると毎ターンMasterの判断基準になります。テンプレートのまま（未記入）なら一切注入されません":
        "Fill in the template to make it the Master's per-turn criteria. If left as the unmodified template, it is never injected",
    "↩ 重要プロンプトをテンプレートに戻す": "↩ Reset key prompt to template",
    "Masterの記憶機能を有効にする": "Enable Master memory",
    "有効にするとMasterが記憶メモを読み書きします（設定・伏線・決定事項の保持）":
        "On = Master reads/writes a memory note (settings, foreshadowing, decisions)",
    "Masterの記憶メモ (memo_md)": "Master memory note (memo_md)",

    # 接続設定タブ
    "エンドポイント一覧": "Endpoints",
    "名前（英数字・-・_）": "Name (alphanumeric, -, _)",
    "APIキー（直接指定）": "API key (direct)",
    "APIキー環境変数名（直接指定が空のとき使用）":
        "API key env var name (used when direct key is empty)",
    "既定モデル": "Default model",
    "🔍 接続テスト": "🔍 Test connection",

    # プリセットタブ
    "### ▶ プリセットを適用": "### ▶ Apply a preset",
    "プリセット": "Preset",
    "▶ 適用（再読み込み）": "▶ Apply (reload)",
    "### 💾 現在の構成をプリセットとして保存": "### 💾 Save current setup as a preset",
    "プリセットid（英数字・-・_）": "Preset id (alphanumeric, -, _)",
    "表示名": "Display name",
    "💾 現在の構成を保存": "💾 Save current setup",
    "#### 📤 エクスポート": "#### 📤 Export",
    "📤 選択中のプリセットをバンドル化": "📤 Bundle the selected preset",
    "ダウンロード（生成された .preset.md）": "Download (generated .preset.md)",
    "#### 📥 インポート": "#### 📥 Import",
    "バンドル(.preset.md)をアップロード": "Upload a bundle (.preset.md)",
    "取り込み先id（空欄ならファイル名から）": "Target id (blank = from filename)",
    "📥 インポート": "📥 Import",
}


def t(text: str, **fmt) -> str:
    """日本語文字列 text を現在言語で返す。未登録は日本語のまま。"""
    s = text if _LANG == "ja" else _EN.get(text, text)
    return s.format(**fmt) if fmt else s
