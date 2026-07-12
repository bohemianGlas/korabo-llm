"""プロンプト組み立てテスト: 二重注入防止・合成順序・後方互換。"""
from __future__ import annotations

from conftest import make_role

from korabo.base_prompts import MASTER_BASE_PROMPT, SUB_BASE_PROMPT
from korabo.master import build_master_messages, parse_master_decision
from korabo.scene import build_scene_packet
from korabo.schemas import MasterDecision
from korabo.sub import build_sub_messages

ROLES = [make_role("a", name="アキラ")]


def _master_system(**kw):
    msgs = build_master_messages("この作品固有の指示。", "状況", ROLES, [], 1, None, [], **kw)
    return msgs[0]["content"]


def _sub_messages(packet=None):
    return build_sub_messages(
        ROLES[0], "あなたはアキラ。", "# 記憶", "状況", "Masterからの指示", [], ROLES,
        scene_packet=packet,
    )


class TestNoDoubleInjection:
    def test_master_format_injected_once(self):
        assert _master_system().count("# 出力形式（厳守）") == 1

    def test_sub_format_injected_once(self):
        assert _sub_messages()[0]["content"].count("# 出力形式（厳守）") == 1

    def test_base_prompts_contain_no_json_fence(self):
        """基本プロンプトはJSON形式指示を持たない（PROTOCOLと重複しない）。"""
        assert "```json" not in MASTER_BASE_PROMPT
        assert "```json" not in SUB_BASE_PROMPT


class TestCompositionOrder:
    def test_directive_topmost(self):
        s = _master_system(directive="- 絶対ルールX")
        assert s.index("最優先指令") < s.index("語り手（Master）の基本原則")
        assert s.index("語り手（Master）の基本原則") < s.index("この作品固有の指示。")

    def test_base_before_work_prompt(self):
        s = _master_system()
        assert s.index("語り手（Master）の基本原則") < s.index("この作品固有の指示。")

    def test_sub_base_before_role_prompt(self):
        s = _sub_messages()[0]["content"]
        assert s.index("登場人物（あなた）の基本原則") < s.index("あなたはアキラ。")

    def test_base_prompts_not_swapped(self):
        """MasterとSubの共通指示が取り違えられていない。"""
        assert "登場人物（あなた）の基本原則" not in _master_system()
        assert "語り手（Master）の基本原則" not in _sub_messages()[0]["content"]


class TestMockMarkers:
    def test_master_marker_kept(self):
        """MockClientの判定マーカー（MasterDecision）が維持される。"""
        assert "MasterDecision" in _master_system()

    def test_sub_marker_kept(self):
        joined = "\n".join(m["content"] for m in _sub_messages())
        assert "SubResponse" in joined


class TestBackwardCompat:
    def test_sub_without_packet_uses_legacy_layout(self):
        user = _sub_messages(packet=None)[1]["content"]
        assert "# 直近の経過" in user
        assert "# 語り手（Master）からあなたへ" in user

    def test_sub_with_packet_uses_scene_layout(self):
        d = MasterDecision(action="call_sub", target_role="a", message_to_role="物音がした")
        p = build_scene_packet(1, d, ROLES[0], ROLES, [])
        user = _sub_messages(packet=p)[1]["content"]
        assert "# 現在の場面" in user
        assert "物音がした" in user
        assert "# 語り手（Master）からあなたへ" not in user

    def test_old_decision_json_without_scene_parses(self):
        d = parse_master_decision('{"narration": "x", "action": "continue"}')
        assert d.scene is None and d.narration == "x"

    def test_broken_scene_does_not_break_decision(self):
        """scene が不正な形状でも Decision 全体のパースを壊さない。"""
        d = parse_master_decision('{"narration": "x", "action": "continue", "scene": "倉庫"}')
        assert d.narration == "x" and d.scene is None

    def test_scene_present_roles_string_coerced(self):
        d = parse_master_decision(
            '{"action": "call_sub", "target_role": "a", "scene": {"location": "倉庫", "present_roles": "a, b"}}'
        )
        assert d.scene is not None
        assert d.scene.present_roles == ["a", "b"]

    def test_style_and_directive_not_conflicting(self):
        """自動文体指示と作品固有指示が両方systemに保持される。"""
        s = _master_system(style="叙情的に", directive="- ルール")
        assert "叙情的に" in s and "この作品固有の指示。" in s and "ルール" in s
