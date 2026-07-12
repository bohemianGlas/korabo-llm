"""MasterLLM のプロンプト構築と応答パース。"""
from __future__ import annotations

from .base_prompts import master_base
from .llm_client import extract_json, strip_code_fences
from .schemas import MasterDecision, RoleConfig

# 直近何件の履歴をコンテキストに含めるか
HISTORY_WINDOW = 40


def _mlang(lang: str) -> str:
    return "en" if str(lang).lower().startswith("en") else "ja"


_MASTER_PROTOCOL_JA = """
# 出力形式（厳守）

あなたは毎ターン、必ず次のMasterDecision JSON形式のみで出力してください。
JSON以外の文章・前置き・後書きを一切含めないでください。

```json
{
  "thought": "あなたの内部思考。物語本文には現れません",
  "narration": "メインログに記録する語り・地の文（不要なら空文字）",
  "action": "call_sub | continue | finish",
  "target_role": "actionがcall_subのとき、呼び出すロールのid",
  "message_to_role": "actionがcall_subのとき、そのロールが直接知覚できる状況・問いかけ",
  "memory_append": "次ターン以降も覚えておきたいこと（不要なら空文字）",
  "scene": {"location": "現在の場所", "time": "時刻・日付", "present_roles": ["その場にいるロールid"], "constraints": "その場の制約（任意）"}
}
```

- `call_sub`: 指定したロール（登場人物）に状況を伝え、発言・行動させる
- `continue`: ロールを呼ばず、語り（narration）のみで次ターンへ進む
- `finish`: 物語・シミュレーションを完結させる（narrationに結びを書く）
- `scene` は任意。call_subのとき分かる範囲で埋める（不明な項目や scene 自体の省略も可）。
  present_roles に載っていないロールには、このターンの出来事は伝わらない
- 文字列の値の中で改行したい場合は \\n と書くこと（生の改行を入れない）
"""

_MASTER_PROTOCOL_EN = """
# Output format (strict)

Each turn, output ONLY the following MasterDecision JSON.
Do not include any prose, preamble or postscript outside the JSON.

```json
{
  "thought": "your internal reasoning; never appears in the story text",
  "narration": "prose recorded to the main log (empty string if none)",
  "action": "call_sub | continue | finish",
  "target_role": "when action is call_sub, the id of the role to call",
  "message_to_role": "when action is call_sub, the situation/prompt that role can DIRECTLY perceive",
  "memory_append": "anything to remember for later turns (empty string if none)",
  "scene": {"location": "current place", "time": "time/date", "present_roles": ["ids of roles present"], "constraints": "constraints in this scene (optional)"}
}
```

- `call_sub`: tell the given role (character) the situation and let them speak/act
- `continue`: do not call a role; advance with narration only
- `finish`: conclude the story/simulation (write the closing in narration)
- `scene` is optional. On call_sub, fill in what you know (unknown items, or scene itself, may be omitted).
  A role not listed in present_roles is not told about this turn's events
- To put a line break inside a string value, write \\n (never a raw newline)
"""

_MASTER_PROTOCOL = {"ja": _MASTER_PROTOCOL_JA, "en": _MASTER_PROTOCOL_EN}


def master_protocol(lang: str = "ja") -> str:
    return _MASTER_PROTOCOL[_mlang(lang)]


# 後方互換の別名（既定=日本語）
MASTER_PROTOCOL = _MASTER_PROTOCOL_JA


def _cross_faction_blocked(viewer_faction: str, other_faction: str) -> bool:
    """双方に（異なる）陣営が設定されている場合のみ True（=見えない）。

    どちらかが陣営なしなら常に見える → 「設定なし＝影響なし」を担保する。
    """
    vf = str(viewer_faction or "").strip()
    of = str(other_faction or "").strip()
    return bool(vf and of and vf != of)


def _absent_from_scene(event: dict, viewer_id: str) -> bool:
    """イベントに present（在席ロールid）が付与されており、viewer が不在なら True。

    present の無い旧イベントは常に False（＝従来の判定のみ・後方互換）。
    """
    present = event.get("present")
    if not present or not isinstance(present, (list, tuple)):
        return False
    return viewer_id not in present


def filter_history_for_role(
    history: list[dict], viewer: RoleConfig, roles: list[RoleConfig]
) -> list[dict]:
    """あるロール（viewer）が見てよい履歴だけに絞り込む（情報可視性の単一の門）。

    - 心の声(sub_inner)は本人にのみ可視（陣営設定の有無に関わらず、他人には見せない）。
    - イベントに present（Masterが申告した在席者）が付与されている場合、
      不在だったロールにはそのターンの出来事を見せない（presence可視性）。
      present の無いイベントは従来判定のみ＝旧履歴の挙動は不変。
    - 陣営が1つも設定されていなければ、それ以外は従来通り全履歴を返す（ノベル用途など）。
    - narration（地の文）は公開情報として可視（presence除外を除く）。
    - ユーザー介入（監督→Masterのメタ指示）はSubには見せない。
    - 他ロールの発言 / Masterから他ロールへの指示は、対立陣営のものを除外する。
      （対立陣営の情報はMasterが message_to_role で明示的に渡したときのみ届く）
    """
    vid = getattr(viewer, "id", "")
    has_faction = any(str(getattr(r, "faction", "")).strip() for r in roles)
    faction_of = {r.id: str(getattr(r, "faction", "")).strip() for r in roles}
    vf = str(getattr(viewer, "faction", "")).strip()

    out: list[dict] = []
    for e in history:
        kind = e.get("kind")
        if kind == "intervention":
            continue  # 監督→Masterのメタ指示はSubに渡さない
        if kind == "sub_inner":
            if e.get("role") == vid:  # 心の声は本人にのみ可視
                out.append(e)
            continue
        if _absent_from_scene(e, vid):
            continue  # 不在だった場面の出来事は見えない
        if kind == "narration":
            out.append(e)
        elif kind in ("master_to_sub", "sub_to_master"):
            if has_faction:
                other = faction_of.get(e.get("role", ""), "")
                if not _cross_faction_blocked(vf, other):
                    out.append(e)
            else:
                out.append(e)
        else:
            out.append(e)
    return out


def render_history(history: list[dict], window: int = HISTORY_WINDOW, lang: str = "ja") -> str:
    en = _mlang(lang) == "en"
    if not history:
        return "(nothing has happened yet)" if en else "（まだ何も起きていません）"
    lines = []
    for e in history[-window:]:
        kind = e.get("kind")
        text = e.get("text", "")
        role = e.get("role")
        if kind == "narration":
            lines.append(f"[Narration] {text}" if en else f"【語り】{text}")
        elif kind == "master_to_sub":
            lines.append(f"[Master→{role}] {text}" if en else f"【Master→{role}】{text}")
        elif kind == "sub_to_master":
            lines.append(f"[{role}] {text}" if en else f"【{role}】{text}")
        elif kind == "sub_inner":
            lines.append(f"[{role}'s inner voice] {text}" if en else f"【{role}の心の声】{text}")
        elif kind == "intervention":
            lines.append(f"[User intervention] {text}" if en else f"【ユーザー介入】{text}")
    return "\n".join(lines)


def build_directive_section(directive: str, lang: str = "ja") -> str:
    """最優先指令（絶対厳守）をsystemの最上位に前置するブロックを返す。空なら空文字。"""
    d = (directive or "").strip()
    if not d:
        return ""
    if _mlang(lang) == "en":
        return (
            "# Top-priority directive (absolute; overrides everything below)\n\n"
            f"{d}\n\n"
            "The above is the highest rule of this session. Whenever it conflicts with any later "
            "prompt, style, pacing decision or character behavior, always obey the above first.\n\n"
            "---\n\n"
        )
    return (
        "# 最優先指令（絶対厳守・以下のすべての指示に優先する）\n\n"
        f"{d}\n\n"
        "上記はこのセッションの最上位ルールです。以降のプロンプト・文体・進行判断・"
        "ロールの言動と矛盾する場合は、必ず上記を最優先で守ってください。\n\n"
        "---\n\n"
    )


def build_length_goal_section(target: int, current: int, lang: str = "ja") -> str:
    """main.mdの目標文字数と現在量をMasterへ伝えるセクションを返す。0以下なら空文字。"""
    try:
        target = int(target or 0)
    except (TypeError, ValueError):
        return ""
    if target <= 0:
        return ""
    current = max(0, int(current or 0))
    remaining = max(0, target - current)
    if _mlang(lang) == "en":
        return (
            "\n\n# Target length (characters in main.md; keep in mind every turn)\n\n"
            f"The target length for this work is about {target:,} characters "
            f"(current text is about {current:,}; about {remaining:,} remaining).\n"
            "Allocate the length of narration, number of scenes and pace of development toward this target.\n"
            "As the remainder shrinks, converge the story, and once the target is reached wrap up with "
            "finish rather than padding (do not greatly overshoot the target)."
        )
    return (
        "\n\n# 目標分量（main.md の文字数・毎ターン意識すること）\n\n"
        f"この作品の目標分量は約 {target:,} 文字です"
        f"（現在の本文は 約 {current:,} 文字 ／ 残り 約 {remaining:,} 文字）。\n"
        "1ターンあたりの narration の長さ・場面の数・展開の速度をこの目標に合わせて配分してください。\n"
        "残りが少なくなってきたら物語を収束させ、目標に達したら不自然に引き延ばさず finish で締めくくってください"
        "（目標を大幅に超過しないこと）。"
    )


def build_important_section(text: str, lang: str = "ja") -> str:
    """重要プロンプト（作品の設計図）をsystemメッセージ用セクションに整形する。

    text はテンプレ未変更なら空（prompts.load_important_prompt 側で判定）。
    空なら注入しない＝MasterLLMはテンプレの内容に左右されない。
    """
    body = (text or "").strip()
    if not body:
        return ""
    if _mlang(lang) == "en":
        return (
            "\n\n# Key prompt (story blueprint; consult every turn)\n\n"
            f"{body}\n\n"
            "## How to use this key prompt\n\n"
            "- Items 1-8 (core of the work, cast, destination, question, must-include, "
            "developments to avoid, afterfeel, rigidity) are the top per-turn criteria for the whole work\n"
            "- Items 9-13 (disclosure, scale, tempo, viewpoint, reality) are consulted per genre and scene "
            "(e.g. mysteries emphasize the disclosure policy; historical works emphasize the reality standard)\n"
            "- Even if developments drift from the plan, preserve the core, character consistency, the central "
            "question, the avoid-list and the intended afterfeel. Treat plot as a plan for realizing these\n"
            "- Blank items may be ignored"
        )
    return (
        "\n\n# 重要プロンプト（作品の設計図・毎ターン参照）\n\n"
        f"{body}\n\n"
        "## この重要プロンプトの扱い\n\n"
        "- 1〜8（作品の核・人物・到達点・問い・必須要素・避けたい展開・読後感・拘束度）は"
        "作品全体を通した毎ターンの判断基準として優先する\n"
        "- 9〜13（情報開示・規模・テンポ・視点・リアリティ）は作品のジャンルや場面に応じて参照する"
        "（例: ミステリーでは情報開示の方針、歴史物ではリアリティの基準を重視）\n"
        "- 展開が当初の予定から変化しても、「作品の核」「人物の一貫性」「中心的な問い」"
        "「避けたい展開」「期待する読後感」は維持する。"
        "プロットは、これらを実現するための予定として扱う\n"
        "- 未記入の項目は無視してよい"
    )


def build_master_memory_section(memory_text: str, lang: str = "ja") -> str:
    """語り手（Master）自身の外部記憶メモをsystemメッセージ用セクションに整形する。

    記憶機能が有効なときだけ呼ぶ。空でも見出しは出し、memory_append の使い方を案内する。
    """
    if _mlang(lang) == "en":
        body = (memory_text or "").strip() or "(nothing yet)"
        return (
            "\n\n# Your (narrator's) memory note\n\n"
            f"{body}\n\n"
            "Write anything to remember for later turns — settings, foreshadowing, decisions, "
            "timeline — into memory_append (this note is given at the top every turn)."
        )
    body = (memory_text or "").strip() or "（まだ何もありません）"
    return (
        "\n\n# あなた（語り手）の記憶メモ\n\n"
        f"{body}\n\n"
        "作品の設定・伏線・決定事項・時系列など、次ターン以降も覚えておきたいことは "
        "memory_append に書いてください（この記憶は毎ターン先頭に渡されます）。"
    )


def build_style_section(style: str, lang: str = "ja") -> str:
    """文体・方向性プロンプトをsystemメッセージ用のセクションに整形する。"""
    style = (style or "").strip()
    if not style:
        return ""
    if _mlang(lang) == "en":
        return (
            "\n\n# Overall style & direction (obey every turn)\n\n"
            f"{style}\n\n"
            "Reflect this style and tone consistently in the narration, and lend the same tone to "
            "the message_to_role you send to roles (while still respecting each role's own persona and voice)."
        )
    return (
        "\n\n# 作品全体の文体・方向性（毎ターン厳守）\n\n"
        f"{style}\n\n"
        "この文体・トーンを narration（地の文）に一貫して反映し、"
        "ロールへ渡す message_to_role の雰囲気にも同じトーンを添えてください。"
        "（ただしロールの人物像・口調そのものは尊重すること）"
    )


def build_factions_section(roles: list[RoleConfig], lang: str = "ja") -> str:
    """陣営が設定されたロールがある場合のみ、Master向けの陣営考慮セクションを返す。

    陣営が1つも設定されていなければ空文字を返し、Masterの思考に一切影響を与えない
    （ノベル執筆など陣営概念が不要な用途を想定）。
    """
    labeled = [r for r in roles if str(getattr(r, "faction", "")).strip()]
    if not labeled:
        return ""
    if _mlang(lang) == "en":
        lines = "\n".join(
            f"- {r.id} ({r.name or r.id}): faction {r.faction.strip()}" for r in labeled
        )
        return (
            "\n\n# Factions (consider only roles that have one)\n\n"
            f"{lines}\n\n"
            "Reason with each role's faction-based stance, interests and information asymmetry. "
            "When deciding what to tell whom (message_to_role), take care not to carelessly pass "
            "information held by one faction to a role of the opposing faction, and reflect the "
            "conflict, cooperation and maneuvering between factions in the story/simulation. "
            "Do not apply faction considerations to roles that have no faction set."
        )
    lines = "\n".join(
        f"- {r.id}（{r.name or r.id}）: 陣営 {r.faction.strip()}" for r in labeled
    )
    return (
        "\n\n# 陣営（設定のあるロールのみ考慮すること）\n\n"
        f"{lines}\n\n"
        "各ロールの陣営に伴う立場・利害・情報の非対称性を踏まえて思考してください。"
        "どのロールに何を伝えるか（message_to_role）を決める際は、"
        "ある陣営だけが持つ情報を対立する陣営のロールへ不用意に渡さないよう注意し、"
        "陣営間の対立・協力・駆け引きを物語／シミュレーションに反映してください。"
        "陣営が設定されていないロールには、この陣営の考慮を適用しないでください。"
    )


def build_narrative_section(style: str, pov_label: str = "", custom_text: str = "", lang: str = "ja") -> str:
    """叙述スタイル（人称・形式）の指示をsystemメッセージ用セクションに整形する。"""
    style = (style or "").strip()
    if not style:
        return ""
    if _mlang(lang) == "en":
        header = "\n\n# Narrative style (how to write narration; obey every turn)\n\n"
        if style == "third":
            body = (
                "Write narration as third-person novel prose. Keep character lines as quoted "
                "dialogue, and weave feelings into gesture and scene description."
            )
        elif style == "first":
            pov = pov_label or "the viewpoint character"
            body = (
                f"Write narration in the first person from \"{pov}\".\n"
                f"- Do not put in the prose events {pov} did not directly witness or experience "
                "(express them as hearsay or guess if needed)\n"
                f"- Do not write the inner thoughts of anyone other than {pov} (describe only outward behavior)\n"
                f"- Freely use {pov}'s own inner voice and emotions as first-person interior description"
            )
        elif style == "script":
            body = (
                "Write narration as a script/play: character name at the start of a line, quoted "
                "dialogue, and stage directions in parentheses."
            )
        elif style == "custom":
            if not (custom_text or "").strip():
                return ""
            body = custom_text.strip()
        else:
            return ""
        return header + body
    header = "\n\n# 叙述スタイル（narrationの書き方・毎ターン厳守）\n\n"
    if style == "third":
        body = (
            "narration は三人称の小説の地の文として書いてください。"
            "登場人物のセリフは「」の会話文で残し、心情は仕草・情景の描写に織り込んでください。"
        )
    elif style == "first":
        pov = pov_label or "視点人物"
        body = (
            f"narration は「{pov}」の一人称視点で書いてください。\n"
            f"- {pov} が直接見聞き・体験していない出来事は地の文に書かない"
            "（必要なら伝聞・推測として表現する）\n"
            f"- {pov} 以外の登場人物の心の声・内面は書かない（外から見える言動のみ描写する）\n"
            f"- {pov} 自身の心の声・感情は一人称の内面描写として自由に活かす"
        )
    elif style == "script":
        body = (
            "narration は台本・戯曲の形式で書いてください。"
            "行頭に人物名、セリフは「」、動作や情景などのト書きは（）で記述します。"
        )
    elif style == "custom":
        if not (custom_text or "").strip():
            return ""
        body = custom_text.strip()
    else:
        return ""
    return header + body


def build_dialogue_policy_section(sub_lines_shown: bool, lang: str = "ja") -> str:
    """セリフ・言動をどう扱うかの方針（生ブロック表示の有無で切り替え）。

    生ブロックがONのときは、Masterがセリフ/行動を繰り返すと二重表示になるため、
    Masterは「つなぎの地の文」だけを書くよう明示する。
    """
    if _mlang(lang) == "en":
        if sub_lines_shown:
            return (
                "\n\n# Handling of dialogue & action (top priority)\n\n"
                "Character lines, actions and gestures will be shown in the text verbatim right after this. "
                "Therefore, in narration do not re-quote or re-describe the preceding character's lines or "
                "actions. Write only the connective prose — scene, passage of time, atmosphere, the viewpoint "
                "character's feelings. Above all, do not write the same content twice. "
                "To draw out a line, put it in message_to_role via call_sub, not in narration."
            )
        return (
            "\n\n# Handling of dialogue & action\n\n"
            "Write important character lines as quoted dialogue within the narration, weaving gesture and "
            "feeling into the description so the exchange reads as novel prose."
        )
    if sub_lines_shown:
        return (
            "\n\n# セリフ・言動の扱い（最優先・厳守）\n\n"
            "登場人物のセリフや行動・仕草は、この後そのまま本文に表示されます。"
            "したがって narration では、直前の登場人物のセリフや行動を繰り返し引用・再描写しないでください。"
            "あなたが書くのは、情景・時間の流れ・空気・視点人物の心情など"
            "「地の文（つなぎ）」だけです。同じ内容を二重に書かないことを最優先してください。"
            "セリフを call_sub で引き出したいときは message_to_role に書き、narration には書かないこと。"
        )
    return (
        "\n\n# セリフ・言動の扱い\n\n"
        "登場人物の重要なセリフは narration の中に「」の会話文として書き、"
        "仕草や心情も描写に織り込んで、対話が読者に伝わる小説本文にしてください。"
    )


def build_dials_section(dials: list[dict] | None, lang: str = "ja") -> str:
    """作品の味付けダイヤルをsystemメッセージ用のセクションに整形する。"""
    items = [d for d in (dials or []) if str(d.get("label", "")).strip()]
    if not items:
        return ""
    lines = "\n".join(f"- {str(d['label']).strip()}: {int(d['value'])}/10" for d in items)
    if _mlang(lang) == "en":
        return (
            "\n\n# Flavor dials (each axis 1-10; higher = stronger)\n\n"
            f"{lines}\n\n"
            "Reflect this balance in how you write the narration and in the tone of the "
            "message_to_role you send to roles."
        )
    return (
        "\n\n# 作品の味付け（各軸 1〜10、数値が高いほどその要素を強く）\n\n"
        f"{lines}\n\n"
        "これらのバランスを narration の書きぶりと、"
        "ロールへ渡す message_to_role のトーンに反映してください。"
    )


def build_master_messages(
    master_prompt: str,
    situation: str,
    roles: list[RoleConfig],
    history: list[dict],
    turn: int,
    max_turns: int | None,
    interventions: list[str],
    style: str = "",
    dials: list[dict] | None = None,
    narrative_style: str = "",
    pov_label: str = "",
    narrative_custom: str = "",
    sub_lines_shown: bool = False,
    master_memory_enabled: bool = False,
    master_memory: str = "",
    directive: str = "",
    target_main_chars: int = 0,
    current_main_chars: int = 0,
    important_prompt: str = "",
    lang: str = "ja",
) -> list[dict]:
    en = _mlang(lang) == "en"

    def _role_line(r: RoleConfig) -> str:
        base = f"- {r.id}: {r.name or r.id}"
        fac = str(getattr(r, "faction", "")).strip()
        if not fac:
            return base
        return f"{base} (faction: {fac})" if en else f"{base}（陣営: {fac}）"

    role_lines = "\n".join(_role_line(r) for r in roles)
    if en:
        limit = f"{max_turns}" if max_turns else "none (unlimited)"
        no_roles = "(no roles available; you may only choose continue or finish)"
        parts = [
            f"# Situation\n\n{situation}",
            f"# Available roles\n{role_lines if role_lines else no_roles}",
            f"# Progress so far\n\n{render_history(history, lang=lang)}",
        ]
        if interventions:
            joined = "\n".join(f"[User intervention] {t}" for t in interventions)
            parts.append(f"# New user intervention (reflect with top priority)\n\n{joined}")
        parts.append(f"# Progress info\n\nCurrent turn: {turn}\nTurn limit: {limit}")
        parts.append("Output the MasterDecision JSON.")
    else:
        limit = f"{max_turns}" if max_turns else "なし（無制限）"
        parts = [
            f"# シチュエーション\n\n{situation}",
            f"# 利用可能なロール\n{role_lines if role_lines else '（ロールがいません。continue か finish のみ選べます）'}",
            f"# これまでの経過\n\n{render_history(history, lang=lang)}",
        ]
        if interventions:
            joined = "\n".join(f"【ユーザー介入】{t}" for t in interventions)
            parts.append(f"# 新しいユーザー介入（最優先で反映すること）\n\n{joined}")
        parts.append(f"# 進行情報\n\n現在のターン: {turn}\nターン上限: {limit}")
        parts.append("MasterDecision JSON を出力してください。")
    system = (
        build_directive_section(directive, lang)
        + master_base(lang)
        + "\n\n---\n\n"
        + master_prompt
        + build_important_section(important_prompt, lang)
        + (build_master_memory_section(master_memory, lang) if master_memory_enabled else "")
        + build_length_goal_section(target_main_chars, current_main_chars, lang)
        + build_style_section(style, lang)
        + build_narrative_section(narrative_style, pov_label, narrative_custom, lang)
        + build_dialogue_policy_section(sub_lines_shown, lang)
        + build_dials_section(dials, lang)
        + build_factions_section(roles, lang)
        + "\n\n"
        + master_protocol(lang)
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def parse_master_decision(text: str) -> MasterDecision:
    """JSONパースに失敗した場合は全文をnarrationとして扱う（進行を止めない）。"""
    try:
        data = extract_json(text)
        return MasterDecision.model_validate(data)
    except Exception:
        # フェンス記号（```json 等）が本文へ流出しないよう剥がしてから使う
        return MasterDecision(narration=strip_code_fences(text), action="continue")
