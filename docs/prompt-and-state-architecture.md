# プロンプトと状態管理のアーキテクチャ

korabo_llm における Master/Sub の責務分離・情報可視性・外部記憶の設計文書。
（`claude_code_korabo_llm_prompt_state_improvement.md` に基づく改修の成果）

## 1. MasterとSubの責務境界

> Masterは状況と結果を管理する。Subは自分自身の意思と試みを管理する。

| | 管理するもの | 確定してはいけないもの |
|---|---|---|
| **Master** | 世界・環境・時刻・場所・場面転換・第三者/群衆・物理的結果・行動の成否・進行・Sub呼び出し・終了判断 | 人物本人の重要な意思決定／発言／内心／秘密の自発的開示／プロット都合の人格変更／知らない情報の付与 |
| **Sub** | 自分の発言・試みる行動・判断・感情・内心・秘密の扱い・記憶への追記候補 | 行動の成功結果／他人の反応・内心／世界全体の変化／場面にない人物・道具／自分が知らない秘密／将来のプロット |

この境界は [korabo/base_prompts.py](../korabo/base_prompts.py) の
`MASTER_BASE_PROMPT` / `SUB_BASE_PROMPT` として**全作品共通で毎回注入**される。
作品固有プロンプト（presets/ や data/ のmd）にはこの汎用原則を書かない。

## 2. 情報の種類と優先順位

コンテキスト上で次の4種を区別する:
**Canon（確定設定）／Current State（現在状態）／Planned Plot（予定・未確定）／Hypothesis（推測）**。

矛盾時の優先順位:
確定設定 > 本文で既に起きた事実 > 現在状態 > 人物の記憶 > プロット予定 > 未確定案。
予定はMasterの記憶メモ（［予定］タグ）に置かれ「強制ではない。既成事実と衝突したら予定側を修正」と明示される。

## 3. 可視性規則（渡す前に除外する）

可視性判定は [korabo/master.py](../korabo/master.py) `filter_history_for_role` に一元化されている
（唯一の門。UI側では判定しない）:

1. **inner_voice**: 本人と Master 以外には決して渡らない（陣営設定の有無に関わらず）
2. **faction**: 双方に異なる陣営が設定された発言・指示は互いに不可視。
   片方でも陣営なしなら可視（「設定なし＝影響なし」）
3. **presence（在席）**: Masterが `scene.present_roles` を申告したターンの出来事
   （narration / 指示 / 発言）は、不在だったロールに不可視。
   present情報の無い旧イベントは従来判定のみ＝**後方互換**
4. **ユーザー介入**: 監督→Masterのメタ指示。Subには常に不可視
5. **他Subの専用記憶**: そもそもコンテキストに含めない（本人の記憶ファイルのみ注入）

秘密情報は「モデルへ渡してから禁止する」のではなく、**渡す前に除外**する。

## 4. 場面パケット（Scene Packet）

Sub呼び出し時の動的コンテキストは [korabo/scene.py](../korabo/scene.py) の
`build_scene_packet()` で**一箇所に集約して**組み立てる:

| フィールド | 出所 |
|---|---|
| scene_id | ターン番号 |
| location / time / present_roles / known_constraints | `MasterDecision.scene`（Masterが申告・任意） |
| recent_visible_events | `filter_history_for_role` 済み履歴（不可視情報は除外済み。発言=heard_speech を含む） |
| direct_perceptions | `message_to_role`（Masterは「本人が直接知覚できること」だけを書くよう共通指示される） |
| physical_state | 本人の記憶md「身体・所持品・現在状態」節の抽出 |
| excluded_kinds | 除外された情報種別のカウント（デバッグ用） |

`MasterDecision.scene` は**任意**フィールドで、不正な形状は None に落とす
（scene の不備で Decision 全体のパースを壊さない）。scene が無くてもパケットは組める。

## 5. role memory（外部記憶）

- 形式: 自由Markdown（従来通り全文をSubのsystemへ注入）
- 推奨構造（[korabo/memory.py](../korabo/memory.py) `memory_template`）:
  `確定して知っている事実／他者から聞いた情報／推測・疑念／約束・命令・計画／人間関係の変化／身体・所持品・現在状態／未完了の行動`
- **タグルーティング**: `memory_append` の行頭タグ（［事実］［伝聞］［推測］［約束］［関係］［状態］［未完了］）を、
  **ファイルに実在する `## ` 見出しへの部分一致**で該当節へ `- 内容 ［T{turn}］` として振り分ける。
  意味推定の正規表現は使わない（明示タグ＋見出しマッチのみ）
- **重複抑制**: 本文の完全一致（タグ・［T..］メタを剥がして比較）は追記せずスキップし、
  `memory_skip` イベントとして記録する
- **後方互換**: タグ無し・見出し無しファイルへは従来のタイムスタンプ追記。
  旧ファイルの自動移行はしない（読み込みは常に全文）

## 6. Master共有状態

Masterの記憶メモ（memo_md）を共有状態として構造化する
（`master_state_template`）: `確定して決まった事実／現在の状態／今後の予定（未確定・強制ではない）／未解決の事項・伏線／現在の章・場面の目標`。
Masterはタグ ［確定］［状態］［予定］［未解決］［目標］ で追記する（ロール記憶と同じ機構）。
共有状態はMasterのみに注入され、**Subへはすべて渡さない**（Subへは場面パケット経由の可視情報のみ）。

## 7. コンテキスト構築順序

**Master system** = 最優先指令（あれば）→ `MASTER_BASE_PROMPT` → 作品固有Masterプロンプト（include展開後）
→ Master記憶（有効時）→ 目標分量 → 文体 → 叙述スタイル → セリフ方針 → ダイヤル → 陣営 → `MASTER_PROTOCOL`（JSON形式・1回のみ）

**Sub system** = `SUB_BASE_PROMPT` → 作品固有ロールプロンプト → 陣営 → 本人の記憶全文 → `SUB_PROTOCOL`（1回のみ）
**Sub user** = シチュエーション → 場面パケット（可視情報のみ）→ 出力要求

JSON形式指示は PROTOCOL 定数のみが持ち、基本プロンプト・作品プロンプトには重複させない。

### 7.1 指示プロンプトの言語（prompt_lang）と出力言語の分離

- `AppConfig.prompt_lang`（"ja"|"en"・既定 ja）が**システム指示文の言語**を選ぶ。切替対象は
  `base_prompts`（Master/Sub基本原則）・PROTOCOL・master.py の各 section builder・
  `render_history`・場面パケット描画（scene.py）・記憶テンプレ/見出し（memory.py）。すべて末尾 `lang`
  引数（既定 ja）で束ね、**ja はバイト不変＝完全な後方互換**。UIは ⚙設定タブで選択（次セッションから反映・再起動不要）。
- **出力言語（narration/セリフの言語）は prompt_lang では決まらない。** 作品側の明示指示
  （ロール「必ず日本語で応答する」／Master「すべて日本語で書く」＝ data/templates 由来）と
  作品本文・記憶・シチュエーションの言語で決まる。原則 **指示言語＝出力言語＝作品言語** が最も頑健
  （混在は小型ローカルモデルで言語のにじみを招きやすい）。
- **記憶タグ→見出しルーティングは日英両対応**（`TAG_TO_HEADING_KEYWORDS` が ［事実］/[fact] 等を
  日本語・英語どちらの見出しにも部分一致で振り分け）。prompt_lang を切替えても、既存の
  日本語記憶ファイルへのルーティングは壊れない。
- `prompt_lang`/`ui_lang` は**マシンローカル設定**（AppConfig）でプリセットに含めない。

## 8. 後方互換

- 旧 MasterDecision（scene無し）／旧 SubResponse: そのまま動作
- 旧記憶md・旧プリセット（新キー無しマニフェスト）: 無変換で読める。欠落キーはデフォルト補完
- presence の無い旧履歴: 可視性判定は従来と同一
- `build_sub_messages(scene_packet=None)`: 従来レイアウトで動作

## 9. テスト方針

`tests/`（pytest・外部API不要）:
可視性（faction/inner_voice/介入/presence）・場面パケット（除外・反映）・記憶（互換/ルーティング/dedup）・
プロンプト組み立て（二重注入防止・合成順序）・統合（台本スタブによる呼び出し→試み→記憶→隔離のE2E）・
指示言語切替（`test_prompt_lang.py`: en分岐の英語化・ja不変・日英タグルーティング）。
実行: `python -m pytest tests/ -q`

## 10. 将来拡張（未実装・設計方針のみ）

- **高類似記憶の統合**: 完全一致以外の重複はLLM判定が必要。`memory.append_memory` の
  dedup判定を差し替え可能にし、任意の「整理パス」（LLMに節単位の要約・統合をさせる明示操作）として追加する想定
- **状態の自動要約**: 記憶mdが閾値を超えたら `summarize_state_if_needed(path, llm)` を挟む。
  破壊的変更になるため必ずバックアップを取り、ユーザー操作でのみ実行する
- **矛盾候補検出**: ［確定］と新規追記の衝突をLLMに照合させ、警告イベントとして表示する
（いずれも脆弱な正規表現による意味判定は行わない）
