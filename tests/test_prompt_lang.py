"""システム指示プロンプトの言語切替（prompt_lang: ja/en）のテスト。

方針:
- ja（既定）はバイト不変（既存テストが担保）。ここでは en 分岐と後方互換を検証。
- 出力言語は本プロンプトでは決めない（作品側指示）。ここで見るのは「指示文の言語」。
"""
from __future__ import annotations

import json

from korabo import base_prompts, master, sub
from korabo.master import build_master_messages
from korabo.memory import (
    append_memory,
    extract_memory_section,
    master_state_template,
    memory_template,
)
from korabo.sub import build_sub_messages
from tests.conftest import make_role


# ---- アクセサ / 後方互換 ----

def test_base_accessors_switch_language():
    assert "語り手（Master）の基本原則" in base_prompts.master_base("ja")
    assert "Narrator (Master) Core Principles" in base_prompts.master_base("en")
    assert "登場人物（あなた）の基本原則" in base_prompts.sub_base("ja")
    assert "Character (you) Core Principles" in base_prompts.sub_base("en")
    # 後方互換の別名は日本語
    assert base_prompts.MASTER_BASE_PROMPT == base_prompts.master_base("ja")
    assert sub.SUB_PROTOCOL == sub.sub_protocol("ja")
    assert master.MASTER_PROTOCOL == master.master_protocol("ja")


def test_protocol_keeps_schema_markers_both_langs():
    # Mock判定・パースのため MasterDecision / SubResponse マーカーは両言語で保持
    assert "MasterDecision" in master.master_protocol("en")
    assert "SubResponse" in sub.sub_protocol("en")
    # JSONキーは英語のまま（両言語）
    for lang in ("ja", "en"):
        assert '"memory_append"' in master.master_protocol(lang)
        assert '"inner_voice"' in sub.sub_protocol(lang)


# ---- Master プロンプト組立 ----

def test_master_messages_en_is_english_and_ordered():
    msgs = build_master_messages(
        "You narrate a mystery.", "An opening scene.",
        [make_role("elena", faction="")], [], 1, 10, [],
        style="terse prose", narrative_style="third",
        directive="- never kill characters",
        lang="en",
    )
    sys_txt = msgs[0]["content"]
    user_txt = msgs[1]["content"]
    # 英語の見出し・基本原則・PROTOCOL
    assert "Narrator (Master) Core Principles" in sys_txt
    assert "Output format (strict)" in sys_txt
    assert "# Situation" in user_txt and "# Available roles" in user_txt
    # directive 最上位 → base → 作品固有 の順
    assert sys_txt.index("Top-priority directive") < sys_txt.index("Narrator (Master) Core Principles")
    assert sys_txt.index("Narrator (Master) Core Principles") < sys_txt.index("You narrate a mystery.")
    # 日本語の固定見出しが混ざらない
    assert "出力形式（厳守）" not in sys_txt
    assert "語り手（Master）の基本原則" not in sys_txt


def test_master_json_format_not_double_injected_en():
    msgs = build_master_messages("m", "s", [], [], 1, None, [], lang="en")
    assert msgs[0]["content"].count("Output format (strict)") == 1


def test_master_ja_unchanged_default():
    # 既定（lang省略）とlang="ja"が同一、かつ日本語であること
    a = build_master_messages("m", "s", [], [], 1, None, [])[0]["content"]
    b = build_master_messages("m", "s", [], [], 1, None, [], lang="ja")[0]["content"]
    assert a == b
    assert "出力形式（厳守）" in a


# ---- Sub プロンプト組立（場面パケット経由・従来経路の両方）----

def test_sub_messages_en_scene_and_legacy():
    role = make_role("elena")
    # 従来経路（scene_packet=None）
    legacy = build_sub_messages(role, "You are Elena.", "", "sit", "msg", [], [role], lang="en")
    assert "Character (you) Core Principles" in legacy[0]["content"]
    assert "Output format (strict)" in legacy[0]["content"]
    assert "# Overall situation" in legacy[1]["content"]
    assert "# Recent progress" in legacy[1]["content"]
    # 日本語が混ざらない
    assert "全体のシチュエーション" not in legacy[1]["content"]


def test_sub_scene_packet_en_labels():
    from korabo.scene import build_scene_packet
    from korabo.schemas import MasterDecision, SceneInfo
    role = make_role("elena")
    dec = MasterDecision(action="call_sub", target_role="elena",
                         message_to_role="A knock at the door.",
                         scene=SceneInfo(location="the inn", time="night", present_roles=["elena"]))
    packet = build_scene_packet(1, dec, role, [role], [], lang="en")
    msgs = build_sub_messages(role, "You are Elena.", "", "sit", dec.message_to_role,
                              [], [role], scene_packet=packet, lang="en")
    u = msgs[1]["content"]
    assert "Current scene" in u and "Place: the inn" in u and "Time: night" in u
    assert "What just happened" in u and "A knock at the door." in u


# ---- 記憶テンプレート・タグルーティング（日英）----

def test_memory_template_en():
    tpl = memory_template("Elena", "en")
    assert "Elena's memory notes" in tpl
    assert "## Facts known for certain" in tpl and "## Body, items, current state" in tpl
    st = master_state_template("en")
    assert "## Established facts" in st and "## Open threads & foreshadowing" in st


def test_tag_routing_english_file_english_tag(tmp_cwd):
    p = "elena_en.md"
    from korabo.memory import write_memory
    write_memory(p, memory_template("Elena", "en"))
    # 英語タグ [heard] → "Heard from others" 見出しへ
    assert append_memory(p, "[heard] Saeki has the key.", turn=5)
    body = extract_memory_section(open(p, encoding="utf-8").read(), "Heard")
    assert "Saeki has the key." in body and "［T5］" in body


def test_tag_routing_japanese_tag_into_english_file(tmp_cwd):
    # 記憶ファイルが英語見出しでも、日本語タグ ［事実］ が Facts 見出しへ振り分く（キーワード併記）
    p = "elena_en2.md"
    from korabo.memory import write_memory
    write_memory(p, memory_template("Elena", "en"))
    assert append_memory(p, "［事実］I am the heir.", turn=2)
    body = extract_memory_section(open(p, encoding="utf-8").read(), "Facts")
    assert "I am the heir." in body


def test_tag_routing_japanese_file_unchanged(tmp_cwd):
    # 日本語ファイル＋日本語タグ（従来動作）
    p = "alice_ja.md"
    from korabo.memory import write_memory
    write_memory(p, memory_template("アリス", "ja"))
    assert append_memory(p, "［伝聞］倉庫の鍵はボブが持っている。", turn=3)
    body = extract_memory_section(open(p, encoding="utf-8").read(), "聞いた")
    assert "倉庫の鍵はボブが持っている。" in body
