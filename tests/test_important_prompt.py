"""重要プロンプト（作品の設計図）のテスト。

仕様: テンプレートから変更されていない場合、MasterLLMへ一切注入されない
（＝テンプレの内容に左右されない）。変更されている場合のみ、扱い方の
ラッパー指示付きで作品固有プロンプトの直後に注入される。
"""
from __future__ import annotations

from pathlib import Path

from korabo.master import build_important_section, build_master_messages
from korabo.prompts import (
    IMPORTANT_PROMPT_TEMPLATE,
    ensure_important_prompt,
    load_important_prompt,
)


def test_template_unchanged_returns_empty(tmp_cwd):
    p = Path("data/master/important_prompt.md")
    ensure_important_prompt(p)
    assert p.exists()
    assert load_important_prompt(p) == ""  # テンプレのまま＝未使用


def test_template_with_whitespace_diff_still_unused(tmp_cwd):
    # 行末空白・改行コード・前後空行の違いは「変更」とみなさない
    p = Path("ip.md")
    body = IMPORTANT_PROMPT_TEMPLATE.replace("\n", "\r\n") + "\r\n\r\n"
    p.write_text(body, encoding="utf-8")
    assert load_important_prompt(p) == ""


def test_modified_template_is_loaded(tmp_cwd):
    p = Path("ip.md")
    body = IMPORTANT_PROMPT_TEMPLATE.replace("ジャンル：", "ジャンル：本格ミステリ")
    p.write_text(body, encoding="utf-8")
    loaded = load_important_prompt(p)
    assert "本格ミステリ" in loaded


def test_missing_or_empty_file_returns_empty(tmp_cwd):
    assert load_important_prompt("no_such.md") == ""
    assert load_important_prompt("") == ""
    p = Path("empty.md")
    p.write_text("", encoding="utf-8")
    assert load_important_prompt(p) == ""


def test_ensure_does_not_overwrite_existing(tmp_cwd):
    p = Path("ip.md")
    p.write_text("ユーザーの記入内容", encoding="utf-8")
    ensure_important_prompt(p)
    assert p.read_text(encoding="utf-8") == "ユーザーの記入内容"


def test_section_empty_when_blank():
    assert build_important_section("") == ""
    assert build_important_section("   \n  ") == ""


def test_section_contains_handling_rules():
    s = build_important_section("# 重要プロンプト\n\n## 1. 作品の核\n\nジャンル：SF")
    assert "重要プロンプト（作品の設計図" in s
    assert "ジャンル：SF" in s
    # 「渡す際の扱い」: 1〜8常時参照／9〜13は場面に応じて／プロットより核を優先
    assert "1〜8" in s and "9〜13" in s
    assert "作品の核" in s and "避けたい展開" in s and "期待する読後感" in s
    assert "予定として扱う" in s


def test_injection_into_master_messages():
    msgs = build_master_messages(
        "あなたは語り手。", "状況", [], [], 1, None, [],
        important_prompt="# 重要プロンプト\n\n中心的な問い：赦しは可能か",
    )
    sys_txt = msgs[0]["content"]
    assert "赦しは可能か" in sys_txt
    # 作品固有プロンプトの後に置かれる
    assert sys_txt.index("あなたは語り手。") < sys_txt.index("赦しは可能か")


def test_no_injection_when_empty():
    msgs = build_master_messages("語り手", "状況", [], [], 1, None, [], important_prompt="")
    assert "重要プロンプト" not in msgs[0]["content"]
