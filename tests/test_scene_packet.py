"""場面パケットテスト: 直接知覚のみ・不可視情報の除外・場面情報の反映。"""
from __future__ import annotations

from conftest import make_role

from korabo.memory import memory_template
from korabo.scene import build_scene_packet, render_scene_packet
from korabo.schemas import MasterDecision, SceneInfo

ROLES = [
    make_role("a", faction="A", name="アキラ"),
    make_role("b", faction="B", name="ベル"),
]

HISTORY = [
    {"kind": "narration", "text": "倉庫街に霧が立ち込める。"},
    {"kind": "master_to_sub", "role": "b", "text": "B陣営だけの秘密"},
    {"kind": "sub_inner", "role": "b", "text": "bの心の声"},
    {"kind": "sub_to_master", "role": "a", "text": "aの発言"},
]

DECISION = MasterDecision(
    action="call_sub",
    target_role="a",
    message_to_role="隣室から床板を踏む音が一度聞こえた。",
    scene=SceneInfo(location="倉庫の二階", time="深夜", present_roles=["a"], constraints="物音を立てられない"),
)


def _packet(memory_text=""):
    return build_scene_packet(5, DECISION, ROLES[0], ROLES, HISTORY, memory_text=memory_text)


class TestScenePacket:
    def test_direct_perceptions_is_message(self):
        assert _packet().direct_perceptions == "隣室から床板を踏む音が一度聞こえた。"

    def test_scene_fields_reflected(self):
        p = _packet()
        assert p.scene_id == 5
        assert p.location == "倉庫の二階"
        assert p.time == "深夜"
        assert p.present_roles == ["a"]
        assert p.known_constraints == "物音を立てられない"

    def test_invisible_info_excluded(self):
        """Master側全情報のうち、他陣営の秘密と他人の心の声は載らない。"""
        events = _packet().recent_visible_events
        assert "B陣営だけの秘密" not in events
        assert "bの心の声" not in events
        assert "倉庫街に霧が立ち込める。" in events
        assert "aの発言" in events

    def test_excluded_kinds_counted(self):
        ex = _packet().excluded_kinds
        assert ex.get("master_to_sub") == 1
        assert ex.get("sub_inner") == 1

    def test_physical_state_from_memory_section(self):
        mem = memory_template("アキラ").replace(
            "## 身体・所持品・現在状態\n", "## 身体・所持品・現在状態\n\n- 左腕を負傷している\n- 懐中電灯を所持\n"
        )
        p = _packet(memory_text=mem)
        assert "左腕を負傷している" in p.physical_state
        assert "懐中電灯" in p.physical_state

    def test_scene_optional(self):
        """scene無しのDecisionでもパケットは組める（後方互換）。"""
        d = MasterDecision(action="call_sub", target_role="a", message_to_role="どうする？")
        p = build_scene_packet(1, d, ROLES[0], ROLES, [])
        assert p.location == "" and p.present_roles == []
        assert p.direct_perceptions == "どうする？"


class TestRender:
    def test_render_contains_fields(self):
        text = render_scene_packet(_packet(), ROLES)
        assert "倉庫の二階" in text
        assert "深夜" in text
        assert "アキラ" in text  # present_roles は表示名で描画
        assert "物音を立てられない" in text
        assert "隣室から床板を踏む音" in text

    def test_render_unknown_when_empty(self):
        d = MasterDecision(action="call_sub", target_role="a", message_to_role="x")
        p = build_scene_packet(1, d, ROLES[0], ROLES, [])
        text = render_scene_packet(p, ROLES)
        assert "不明" in text
