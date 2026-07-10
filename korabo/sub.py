"""SubLLM（ロール）のプロンプト構築と応答パース。"""
from __future__ import annotations

from .llm_client import extract_json
from .master import filter_history_for_role, render_history
from .schemas import RoleConfig, SubResponse

# サブLLMに渡す直近履歴の件数
SUB_HISTORY_WINDOW = 20

SUB_PROTOCOL = """
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
"""


def build_sub_messages(
    role: RoleConfig,
    role_prompt: str,
    memory_text: str,
    situation: str,
    message_from_master: str,
    history: list[dict],
    all_roles: list[RoleConfig] | None = None,
) -> list[dict]:
    parts = [role_prompt]
    faction = str(getattr(role, "faction", "")).strip()
    if faction:
        parts.append(
            f"# あなたの陣営\n\nあなたは陣営「{faction}」に属します。"
            "その立場・利害・仲間との関係を踏まえて振る舞ってください。"
        )
    parts.append(
        f"# あなたの記憶メモ（これまでに自分で書き残したもの）\n\n{memory_text or '（まだ何もありません）'}"
    )
    parts.append(SUB_PROTOCOL)
    system = "\n\n".join(parts)
    visible = filter_history_for_role(history, role, all_roles or [role])
    user = "\n\n".join(
        [
            f"# 全体のシチュエーション\n\n{situation}",
            f"# 直近の経過\n\n{render_history(visible, SUB_HISTORY_WINDOW)}",
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
        return SubResponse(reply=text.strip())
