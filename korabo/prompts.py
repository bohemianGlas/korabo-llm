"""Masterプロンプトの読み込みと include 展開（AGENTS.md方式）。

master_prompt.md を親ファイルとして扱い、include 指定があれば子ファイル
（outline.md / style.md / note.md 等）を読み込んで末尾に展開する。
指定が無ければ本文をそのまま返す（従来動作）。

include の記法（両対応）:
  1. 明示行:   `@include: outline.md, style.md, note.md`   （複数行可）
  2. 見出し節: 見出しに「参照ファイル / インクルード / include」を含む節の中の
               `` `xxx.md` `` （バッククォート）を対象
パスは master_prompt.md のあるディレクトリ基準で解決する。
"""
from __future__ import annotations

import re
from pathlib import Path

# 見出しに含まれると「参照ファイル節」とみなすキーワード
_INCLUDE_HEADING = re.compile(r"^#{1,6}\s*.*(参照ファイル|インクルード|include)", re.IGNORECASE)
_HEADING = re.compile(r"^#{1,6}\s")
_INCLUDE_LINE = re.compile(r"^\s*@include\s*[:：]\s*(.+)$", re.IGNORECASE)
_BACKTICK_MD = re.compile(r"`([^`]+?\.md)`")


def find_includes(text: str) -> list[str]:
    """本文から include 対象のファイル名リストを順序保持・重複排除で抽出する。"""
    found: list[str] = []

    def _add(name: str) -> None:
        name = name.strip().strip("`").strip()
        if name and name not in found:
            found.append(name)

    in_section = False
    for line in text.splitlines():
        # 1) 明示行 @include: a.md, b.md
        m = _INCLUDE_LINE.match(line)
        if m:
            for part in m.group(1).split(","):
                _add(part)
            continue
        # 2) 見出し節の検出（節に入る／出る）
        if _INCLUDE_HEADING.match(line):
            in_section = True
            continue
        if _HEADING.match(line):
            in_section = False
        if in_section:
            for name in _BACKTICK_MD.findall(line):
                _add(name)
    return found


def load_master_prompt(prompt_file: str | Path) -> str:
    """master_prompt.md を読み、include 指定があれば子ファイルを末尾に展開して返す。"""
    p = Path(prompt_file)
    if not p.exists():
        return ""
    body = p.read_text(encoding="utf-8")
    includes = find_includes(body)
    if not includes:
        return body

    base = p.parent
    parts = [body]
    for name in includes:
        child = (base / name)
        if child.exists():
            parts.append(f"\n\n# 参照: {name}\n\n{child.read_text(encoding='utf-8')}")
        else:
            parts.append(f"\n\n<!-- 参照ファイルが見つかりません: {name} -->")
    return "".join(parts)
