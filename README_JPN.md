## Notice
>このプログラムはAIコーディングにより開発されました。動作の結果のいかなる結果にも作者は責任を負いません。

# korabo_llm — マスターLLM × サブLLM コラボレーションシステム


*English version : [README.md](README.md)*

> **English summary** — korabo_llm is a local-first web app where a **Master LLM** (narrator / director) orchestrates multiple **Sub LLMs** (characters), each with its own role prompt and persistent Markdown memory, to run agent simulations and collaborative story generation. Works with any OpenAI-compatible endpoint (LM Studio, OpenRouter, OpenAI, …). The WebUI (Gradio) supports **Japanese / English** switching, live user intervention, execution modes, factions, narrative styles, presets, and console logging. Quick start: `pip install -r requirements.txt` then `python korabo_llm.py` (opens http://127.0.0.1:7860; runs out-of-the-box with a built-in `mock` endpoint). Note: the UI language does not change the generated story's language — that is driven by your prompts and models.

マスターLLM（語り手・進行役）が複数のサブLLM（ロール＝登場人物）を統括し、
状況シミュレーションや物語生成を行うシステムです。

- **Master LLM**: マスタープロンプトとシチュエーションプロンプトを理解し、適切なタイミングで適切なロールを呼び出し、応答を統合してメインログ（物語）として編纂します
- **Sub LLM（ロール）**: 個別のロールプロンプトで稼働し、外部記憶となる Markdown ファイル（memo_md）を持ち、自分で書き込めます
- **WebUI**: リアルタイム表示・全設定の編集・実行中のユーザー介入がブラウザから可能です

## セットアップ

```bash
pip install -r requirements.txt
python korabo_llm.py
```

http://127.0.0.1:7860 でWebUIが開きます。

初期設定は `mock` エンドポイント（LLM未接続のダミー）になっているため、
インストール直後でもそのまま「▶ 開始」を押せば全体の動作を確認できます。

- **初回起動時、`config/config.jsonc` が無ければ `config/config.example.jsonc` から自動生成**されます。`config.jsonc` は `.gitignore` 済みなので、WebUIで入力したAPIキーがコミットされる心配はありません。
- **APIキーは `config.jsonc` に直接書かず、環境変数（各エンドポイントの `api_key_env`）を使うことを推奨**します。

### Command-line options

```bash
python korabo_llm.py --listen 0.0.0.0 --port 7860   # expose on LAN
python korabo_llm.py --log-level DEBUG               # verbose console logs
python korabo_llm.py --no-color --no-tokens          # plain logs, no per-turn token lines
```
### 起動オプションは
```
python korabo_llm.py --help
```
で確認できますが、以下のようになります、

```
options:
  -h, --help            show this help message and exit
  --listen ADDR         バインドするアドレス。LAN公開は --listen 0.0.0.0（既定: 127.0.0.1）
  --port PORT           待ち受けポート（既定: 7860）
  --share               Gradioの一時公開URL（gradio.live）を発行する
  --log-level {DEBUG,INFO,WARNING,ERROR}
                        コンソールログの詳細度（既定: INFO）
  --no-color            色付き出力を無効化する
  --no-tokens           毎ターンのトークン使用量表示を無効化する
```
```
python korabo_llm.py --log-level DEBUG     # デバッグ用（思考・心の声まで）
python korabo_llm.py                       # 既定 = INFO
python korabo_llm.py --log-level WARNING   # ほぼ無音（問題時のみ）
```


## UIの言語 / UI language

画面右上の「言語 / Language」で **日本語 / English** を切り替えられます（選択するとページが再読み込みされ、UIが選択言語で再構築されます）。
※ UIの言語は**生成される物語の言語を変えません**（出力言語はプロンプトとモデルに依存します）。

## LLMへの接続

「🔌 接続設定」タブでOpenAI互換エンドポイントを登録し、
「🧠 マスター設定」「🎭 ロール管理」タブで使用するエンドポイント・モデルを選択します。

| エンドポイント | base_url | APIキー |
|---|---|---|
| OpenRouter | `https://openrouter.ai/api/v1` | 環境変数 `OPENROUTER_API_KEY` または直接入力 |
| LM Studio | `http://localhost:1234/v1` | 不要（任意文字列） |
| OpenAI | `https://api.openai.com/v1` | 環境変数 `OPENAI_API_KEY` または直接入力 |
| mock | `mock` | 不要（動作確認用ダミー） |

- APIキーは「直接指定」と「環境変数名の参照」の両方に対応しています
- Master と各ロールで別々のエンドポイント・モデルを使えます（例: Masterは OpenRouter の大型モデル、ロールはローカルLLM）
- ロールのエンドポイント/モデルが未指定の場合は `sub_defaults` の既定値を使用します

## 使い方

### 実行タブ

1. シチュエーションプロンプトを入力
2. 実行モードを選択
   - **1ステップずつ** — 1ターンごとに一時停止し、「⏭ 1ステップ」で進める
   - **指定ステップまで実行** — 指定ターン数まで自動実行（Masterの終了判断は無視）
   - **Master判断で停止（上限あり）** — Masterが完結を宣言するかターン上限で停止
   - **Master判断で停止（無限）** — Masterが完結を宣言するまで無制限に実行
   - **無限モード** — ユーザーが停止するまで無制限に実行
3. 「▶ 開始」で実行。メインログ（Masterの編纂結果）と詳細ストリーム（Master思考・Sub応答・記憶更新）がリアルタイムに表示されます
4. 実行中は「⚡ 介入を送信」でイベント注入・シチュエーション変更などの指示をMasterに送れます（次のMasterターンで反映）

### その他のタブ

- **📜 詳細ログ** — 過去セッションの main.md（編纂結果）/ full.md（全やり取り）を閲覧
- **🎭 ロール管理** — ロールの追加・編集・削除、ロールプロンプトと記憶メモ(memo_md)の編集
- **🧠 マスター設定** — マスタープロンプト・Masterの接続先の編集
- **🔌 接続設定** — エンドポイントのCRUDと接続テスト

## アーキテクチャ

```
SituationPrompt ─┐
MasterPrompt ────┤
                 ▼
             MasterLLM ⇄ SubLLM1 ⇄ memo_md1 (RolePrompt1)
                 ⇅       SubLLM2 ⇄ memo_md2 (RolePrompt2)
                 ⇅       SubLLM…
                 ▼
          main.md / full.md / events.jsonl
```

- **LangGraph** で「Masterが行動を決定 →（必要なら）Subが応答 → Masterに戻る」という1ターンのグラフを構成し、セッションコントローラがモードに応じてループ実行します
- Master ⇔ Sub のやり取りは構造化JSON（`MasterDecision` / `SubResponse`）で行い、function-calling非対応のローカルモデルでも動くようプロンプト指示＋堅牢パースで実装しています。パース失敗時は全文を語り/発言として扱い、進行を止めません

### ディレクトリ構成

```
├── korabo_llm.py           # エントリポイント
├── config/config.example.jsonc # 設定のサンプル（同梱・追跡対象）
├── config/config.jsonc     # 実際の設定（初回に example から自動生成／.gitignore 済）
├── korabo/                 # コアロジック
│   ├── schemas.py          #   設定・プロトコルのデータモデル
│   ├── config.py           #   JSONC読み書き
│   ├── llm_client.py       #   OpenAI互換クライアント + JSONパース + Mock
│   ├── master.py / sub.py  #   プロンプト構築・応答パース
│   ├── graph.py            #   LangGraphグラフ
│   ├── session.py          #   セッションコントローラ（モード・介入・停止）
│   ├── memory.py           #   memo_md 読み書き
│   └── logger.py           #   Markdownログ + events.jsonl
├── ui/                     # Gradio WebUI（タブごとのモジュール）
└── data/
    ├── master/master_prompt.md   # マスタープロンプト
    ├── roles/<id>.md             # ロールプロンプト
    └── memories/<id>.md          # ロールの外部記憶 (memo_md)

logs/session_*/                   # セッションログ（プロジェクトルート直下）
presets/<id>/                     # 作品一式プリセット（任意）
```

## ログ

セッションごとに **プロジェクトルート直下** の `logs/session_YYYYMMDD-HHMMSS/` が作成されます。
（旧バージョンの `data/logs/` に残ったログは手動移動しない限りそのまま残ります）

- `main.md` — Masterが編纂した最終出力（物語本文）
- `full.md` — Masterの内部思考・Sub呼び出し・Sub生応答・記憶更新を含む全記録
- `events.jsonl` — 構造化イベント（プログラムからの解析用）

## マスタープロンプトの分割（include）

マスタープロンプトを1枚のmdに全部書く代わりに、子ファイルへ分割できます。
`master_prompt.md` の中に以下いずれかを書くと、子mdを読み込んで末尾に展開します（指定が無ければ従来どおり本文のみ）。

```markdown
@include: outline.md, style.md, note.md
```

または見出し節で:

```markdown
## 参照ファイル
1. `outline.md` — 執筆内容・目的・制約
2. `style.md`   — 文体・口調・避ける表現
3. `note.md`    — 前回までの決定・固有名詞・矛盾防止メモ
```

パスは `master_prompt.md` のあるフォルダ基準で解決されます。

## プリセット（作品一式の一括切替）

「🎁 プリセット」タブで、マスタープロンプト（+include子md）・ロール・記憶・味付けを
まとめて `presets/<id>/` に保存し、ワンクリックで切り替えられます。

- **再ポイント方式**：適用すると各設定が `presets/<id>/` 内を直接参照します。プレイ中の記憶も
  そのプリセット内に蓄積するため、切り替えて戻っても各プリセットの記憶が保たれます。
- **接続先（URL・APIキー）は切り替わりません**（マシン設定として `config.jsonc` に残ります）。
- 「現在の構成を保存」で、いまの `data/` の内容をそのままプリセット化できます。
- **バンドル**: プリセットを単一ファイル `<id>.preset.md`（可読なMarkdown）としてエクスポート/インポートできます（共有・バックアップ用）。稼働形式はディレクトリのまま。接続先（URL・APIキー）はバンドルに含まれません。
