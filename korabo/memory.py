"""外部記憶（memo_md）の読み書き・構造化・重複抑制。

後方互換の原則（自動縮退）:
- 読み込みは常にファイル全文（旧自由形式もそのまま使える）
- 追記は「行頭タグ ＋ ファイル内に実在する ## 見出し」が揃ったときだけ
  該当セクションへ振り分け、それ以外は従来のタイムスタンプ追記
- 旧形式ファイルを黙って書き換える自動移行は行わない
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

# ロール記憶の推奨セクション（新規作成・クリア時のテンプレに使用）
_MEMORY_SECTIONS = {
    "ja": [
        "確定して知っている事実",
        "他者から聞いた情報",
        "推測・疑念",
        "約束・命令・計画",
        "人間関係の変化",
        "身体・所持品・現在状態",
        "未完了の行動",
    ],
    "en": [
        "Facts known for certain",
        "Heard from others",
        "Guesses & suspicions",
        "Promises, orders, plans",
        "Relationship changes",
        "Body, items, current state",
        "Unfinished actions",
    ],
}

# Master（語り手）の共有状態セクション
_MASTER_STATE_SECTIONS = {
    "ja": [
        "確定して決まった事実",
        "現在の状態",
        "今後の予定（未確定・強制ではない）",
        "未解決の事項・伏線",
        "現在の章・場面の目標",
    ],
    "en": [
        "Established facts",
        "Current state",
        "Upcoming plans (tentative, not mandatory)",
        "Open threads & foreshadowing",
        "Goal for the current chapter/scene",
    ],
}

# 後方互換の別名（既定=日本語。既存 import 用）
MEMORY_SECTIONS = _MEMORY_SECTIONS["ja"]
MASTER_STATE_SECTIONS = _MASTER_STATE_SECTIONS["ja"]

# 行頭タグ → 見出しキーワード（見出しはファイル内に実在するものへ部分一致で振り分け）
# 日英タグを両方登録し、記憶ファイルの見出し言語に依らずルーティングできるようにする。
# 見出しキーワードは「日本語見出しの一部」と「英語見出しの一部」を併記（順に部分一致で試す）。
TAG_TO_HEADING_KEYWORDS = {
    # ロール記憶用
    "事実": ["事実", "Facts"],
    "fact": ["事実", "Facts"],
    "伝聞": ["聞いた", "Heard"],
    "heard": ["聞いた", "Heard"],
    "推測": ["推測", "Guesses"],
    "guess": ["推測", "Guesses"],
    "約束": ["約束", "Promises"],
    "promise": ["約束", "Promises"],
    "関係": ["関係", "Relationship"],
    "relation": ["関係", "Relationship"],
    "状態": ["状態", "state", "Body"],
    "state": ["状態", "state", "Body"],
    "未完了": ["未完了", "Unfinished"],
    "todo": ["未完了", "Unfinished"],
    # Master共有状態用
    "確定": ["確定", "Established"],
    "canon": ["確定", "Established"],
    "予定": ["予定", "plans", "Upcoming"],
    "plan": ["予定", "plans", "Upcoming"],
    "未解決": ["未解決", "Open"],
    "open": ["未解決", "Open"],
    "目標": ["目標", "Goal"],
    "goal": ["目標", "Goal"],
}

# 後方互換の別名（旧: タグ→単一キーワード）
TAG_TO_HEADING_KEYWORD = {k: v[0] for k, v in TAG_TO_HEADING_KEYWORDS.items()}

_TAG_RE = re.compile(r"^[［\[]([^］\]]{1,6})[］\]]\s*")
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _norm_lang(lang: str) -> str:
    return "en" if str(lang).lower().startswith("en") else "ja"


def memory_template(name: str, lang: str = "ja") -> str:
    """ロール用の構造化記憶テンプレート。"""
    lg = _norm_lang(lang)
    body = "\n\n".join(f"## {s}\n" for s in _MEMORY_SECTIONS[lg])
    title = f"{name} の記憶メモ" if lg == "ja" else f"{name}'s memory notes"
    return f"# {title}\n\n{body}"


def master_state_template(lang: str = "ja") -> str:
    """Master（語り手）用の共有状態テンプレート。"""
    lg = _norm_lang(lang)
    body = "\n\n".join(f"## {s}\n" for s in _MASTER_STATE_SECTIONS[lg])
    title = "語り手（Master）の記憶メモ" if lg == "ja" else "Narrator (Master) memory notes"
    return f"# {title}\n\n{body}"


def read_memory(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def extract_memory_section(text: str, keyword: str) -> str:
    """記憶md本文から、見出しに keyword を含む `## ` セクションの中身を返す（無ければ空）。"""
    if not text or not keyword:
        return ""
    matches = list(_HEADING_RE.finditer(text))
    for i, m in enumerate(matches):
        if keyword in m.group(1):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[start:end].strip()
    return ""


def _split_tag(text: str) -> tuple[str, str]:
    """行頭の ［タグ］/[タグ] を (タグ, 残りの本文) に分離する。タグ無しなら ("", 原文)。"""
    m = _TAG_RE.match(text)
    if not m:
        return "", text
    return m.group(1).strip(), text[m.end():].strip()


def _find_section_heading(content: str, tag: str) -> str | None:
    """タグに対応する見出し行（実在するもの）を返す。無ければ None。

    日英どちらの見出し言語でも振り分けられるよう、タグに紐づく複数キーワードを
    順に部分一致で試す（記憶ファイルの見出し言語に依存しない）。
    """
    keywords = TAG_TO_HEADING_KEYWORDS.get(tag, [tag])
    for keyword in keywords:
        for m in _HEADING_RE.finditer(content):
            if keyword in m.group(1):
                return m.group(0)
    return None


def _is_duplicate(content: str, entry_body: str) -> bool:
    """本文の完全一致行（箇条書き・タグ・メタを剥がして比較）が既にあるか。"""
    target = entry_body.strip()
    if not target:
        return True
    for line in content.splitlines():
        s = line.strip().lstrip("-").strip()
        # 既存行から行頭タグと末尾の ［T..］ メタを剥がして比較
        _, s = _split_tag(s)
        s = re.sub(r"\s*[［\[]T?\d+[］\]]\s*$", "", s).strip()
        if s and s == target:
            return True
    return False


def append_memory(path: str | Path, text: str, turn: int | None = None) -> bool:
    """記憶メモへ1件追記する。追記したら True、重複スキップなら False。

    - 完全一致の重複は追記しない（無制限追記の抑制）
    - 行頭タグがあり、対応する `## ` 見出しがファイルに実在すれば、その節末尾へ
      `- 本文 ［T{turn}］` として挿入（構造化ルーティング）
    - それ以外は従来のタイムスタンプ見出しで末尾へ追記（旧形式との互換）
    """
    text = (text or "").strip()
    if not text:
        return False
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = p.read_text(encoding="utf-8") if p.exists() else ""

    tag, body = _split_tag(text)
    if _is_duplicate(existing, body):
        return False

    meta = f" ［T{turn}］" if turn is not None else ""

    heading = _find_section_heading(existing, tag) if tag else None
    if heading is not None:
        # 該当セクションの末尾（次の ## 見出しの直前）へ箇条書きで挿入
        entry = f"- {body}{meta}\n"
        idx = existing.index(heading) + len(heading)
        rest = existing[idx:]
        m = re.search(r"^##\s", rest, re.MULTILINE)
        insert_at = idx + (m.start() if m else len(rest))
        section = existing[idx:insert_at].rstrip("\n")
        new_section = f"{section}\n{entry}" if section.strip() else f"\n\n{entry}"
        updated = existing[:idx] + new_section + "\n" + existing[insert_at:].lstrip("\n")
        p.write_text(updated, encoding="utf-8")
        return True

    # 従来形式（タイムスタンプ見出し）で末尾へ
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    turn_label = f"T{turn} " if turn is not None else ""
    sep = "" if existing.endswith("\n") or not existing else "\n"
    p.write_text(f"{existing}{sep}\n## {turn_label}{ts}\n\n{text}\n", encoding="utf-8")
    return True


def write_memory(path: str | Path, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
