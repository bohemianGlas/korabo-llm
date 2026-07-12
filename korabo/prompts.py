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


IMPORTANT_PROMPT_TEMPLATE = """\
# 重要プロンプト

## 1. 作品の核

ジャンル：
舞台：
主人公が直面する問題：
中心的な対立：
描きたい変化：

本文：


## 2. 主人公と中心人物

主人公：
中心人物：
中心となる人物関係：
物語の軸から外してはいけない人物：
脇役に留めたい人物：

本文：


## 3. 主人公の初期状態と到達点

開始時点：
到達点：
変わってほしくない部分：


## 4. 中心的な問い

中心的な問い：


## 5. 必ず含めたい要素

-
-
-


## 6. 避けたい展開

-
-
-


## 7. 期待する読後感

期待する感情：
避けたい読後感：

本文：


## 8. プロットの拘束度

拘束度：
厳密／中程度／自由

固定する要素：

Master LLMへ任せる要素：


## 9. 情報開示の方針

序盤で明かしてよい情報：

中盤で明かしてよい情報：

終盤まで隠す情報：

最後まで曖昧にする情報：

読者と主人公の情報差：


## 10. 物語の規模

主な舞台：
作中期間：
主要人物数：
移動範囲：
事件や対立の規模：


## 11. テンポと場面配分

序盤のテンポ：

中盤のテンポ：

終盤のテンポ：

会話・心理描写・行動・説明の比率：


## 12. 視点上の重点

中心となる視点：

読者が知る範囲：

他人物の内心の扱い：

誤解や認識のずれの扱い：


## 13. リアリティの基準

厳密に扱う要素：

簡略化してよい要素：

人物心理の現実性：

架空設定のルール：
"""


def _norm(text: str) -> str:
    """テンプレ一致判定用の正規化。

    改行コード・行末空白・空行の有無を無視して比較する（エディタやOSによる
    改行変換で「変更あり」と誤判定しないため）。ユーザーの記入は必ず
    非空白文字を伴うので、この正規化で判定の正しさは損なわれない。
    """
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines()]
    return "\n".join(line for line in lines if line)


def ensure_important_prompt(path: str | Path) -> None:
    """重要プロンプトのファイルが無ければテンプレートを書き込む。"""
    p = Path(path)
    if not path or p.exists():
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(IMPORTANT_PROMPT_TEMPLATE, encoding="utf-8")


def load_important_prompt(path: str | Path) -> str:
    """重要プロンプトを読み込む。

    ファイルが無い・空・**テンプレートから変更されていない**場合は空文字を返す
    （＝MasterLLMへは一切注入されず、内容に左右されない）。
    """
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        return ""
    body = p.read_text(encoding="utf-8")
    if not body.strip():
        return ""
    if _norm(body) == _norm(IMPORTANT_PROMPT_TEMPLATE):
        return ""  # テンプレのまま＝未記入とみなす
    return body


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
