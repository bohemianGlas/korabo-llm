"""SubLLM（ロール）のプロンプト構築と応答パース。"""
from __future__ import annotations

from .base_prompts import sub_base
from .llm_client import extract_json, strip_code_fences
from .master import filter_history_for_role, render_history
from .scene import ScenePacket, render_scene_packet
from .schemas import RoleConfig, SubResponse

# サブLLMに渡す直近履歴の件数
SUB_HISTORY_WINDOW = 20


def _slang(lang: str) -> str:
    return "en" if str(lang).lower().startswith("en") else "ja"


_SUB_PROTOCOL_JA = """
# 出力形式（厳守）

あなたは必ず次のSubResponse JSON形式のみで出力してください。
JSON以外の文章・前置き・後書きを一切含めないでください。

```json
{
  "speech": "あなたが声に出して言うセリフ（無ければ空文字）",
  "action": "あなたの行動・仕草・表情など、外から見える言動の描写（無ければ空文字）",
  "inner_voice": "あなたの心の声・心情。声には出さない内面（無ければ空文字）",
  "memory_append": "あなたの記憶メモに残したい内容（不要なら空文字）"
}
```

- speech は「」を付けずに中身だけ書いてください（表示側で付けます）。
- inner_voice はあなたと語り手だけが知る内面で、他の登場人物には伝わりません。
- 与えられた指示文をそのまま繰り返さず、あなた自身の言葉で反応してください。
- 文字列の値の中で改行したい場合は \\n と書いてください（生の改行を入れない）。
"""

_SUB_PROTOCOL_EN = """
# Output format (strict)

Output ONLY the following SubResponse JSON.
Do not include any prose, preamble or postscript outside the JSON.

```json
{
  "speech": "what you say aloud (empty string if none)",
  "action": "your outward action, gesture, expression (empty string if none)",
  "inner_voice": "your unspoken feelings/thoughts, not said aloud (empty string if none)",
  "memory_append": "what to keep in your memory note (empty string if none)"
}
```

- Write speech as the content only, without quotation marks (the display adds them).
- inner_voice is known only to you and the narrator; it does not reach other characters.
- Do not repeat the prompt verbatim; react in your own words.
- To put a line break inside a string value, write \\n (never a raw newline).
"""

_SUB_PROTOCOL = {"ja": _SUB_PROTOCOL_JA, "en": _SUB_PROTOCOL_EN}


def sub_protocol(lang: str = "ja") -> str:
    return _SUB_PROTOCOL[_slang(lang)]


# 後方互換の別名（既定=日本語）
SUB_PROTOCOL = _SUB_PROTOCOL_JA


def build_sub_messages(
    role: RoleConfig,
    role_prompt: str,
    memory_text: str,
    situation: str,
    message_from_master: str,
    history: list[dict],
    all_roles: list[RoleConfig] | None = None,
    scene_packet: ScenePacket | None = None,
    lang: str = "ja",
) -> list[dict]:
    en = _slang(lang) == "en"
    parts = [sub_base(lang), role_prompt]
    faction = str(getattr(role, "faction", "")).strip()
    if faction:
        if en:
            parts.append(
                f"# Your faction\n\nYou belong to faction \"{faction}\". "
                "Act with its stance, interests and ties to your allies in mind."
            )
        else:
            parts.append(
                f"# あなたの陣営\n\nあなたは陣営「{faction}」に属します。"
                "その立場・利害・仲間との関係を踏まえて振る舞ってください。"
            )
    if en:
        parts.append(
            f"# Your memory note (what you have written for yourself)\n\n{memory_text or '(nothing yet)'}"
        )
    else:
        parts.append(
            f"# あなたの記憶メモ（これまでに自分で書き残したもの）\n\n{memory_text or '（まだ何もありません）'}"
        )
    parts.append(sub_protocol(lang))
    system = "\n\n".join(parts)

    if scene_packet is not None:
        # 場面パケット経由（可視情報は build_scene_packet でフィルタ済み）
        head = "# Overall situation" if en else "# 全体のシチュエーション"
        tail = "Output the SubResponse JSON." if en else "SubResponse JSON を出力してください。"
        user = "\n\n".join(
            [
                f"{head}\n\n{situation}",
                render_scene_packet(scene_packet, all_roles or [role], lang),
                tail,
            ]
        )
    else:
        # 従来経路（後方互換）: ここでフィルタして直近経過＋指示を渡す
        visible = filter_history_for_role(history, role, all_roles or [role])
        if en:
            user = "\n\n".join(
                [
                    f"# Overall situation\n\n{situation}",
                    f"# Recent progress\n\n{render_history(visible, SUB_HISTORY_WINDOW, lang)}",
                    f"# From the narrator (Master) to you\n\n{message_from_master}",
                    "Output the SubResponse JSON.",
                ]
            )
        else:
            user = "\n\n".join(
                [
                    f"# 全体のシチュエーション\n\n{situation}",
                    f"# 直近の経過\n\n{render_history(visible, SUB_HISTORY_WINDOW, lang)}",
                    f"# 語り手（Master）からあなたへ\n\n{message_from_master}",
                    "SubResponse JSON を出力してください。",
                ]
            )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def parse_sub_response(text: str) -> SubResponse:
    """JSONパースに失敗した場合は全文をreplyとして扱う（進行を止めない）。"""
    try:
        data = extract_json(text)
        return SubResponse.model_validate(data)
    except Exception:
        # フェンス記号（```json 等）が本文へ流出しないよう剥がしてから使う
        return SubResponse(reply=strip_code_fences(text))
