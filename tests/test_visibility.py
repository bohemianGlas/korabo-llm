"""可視性テスト: faction隔離・inner_voice・介入・presence（不在場面）。"""
from __future__ import annotations

from conftest import make_role

from korabo.master import filter_history_for_role


def _texts(events):
    return [e.get("text", "") for e in events]


ROLES = [
    make_role("a", faction="A"),
    make_role("b", faction="B"),
    make_role("c"),  # 陣営なし
]

HISTORY = [
    {"kind": "narration", "text": "夜が更けた。"},
    {"kind": "master_to_sub", "role": "a", "text": "A陣営の秘密指令"},
    {"kind": "sub_to_master", "role": "a", "text": "Aの秘密報告"},
    {"kind": "sub_inner", "role": "a", "text": "aの心の声"},
    {"kind": "intervention", "text": "監督のメタ指示"},
    {"kind": "sub_to_master", "role": "c", "text": "cの公開発言"},
]


class TestFactionIsolation:
    def test_cross_faction_blocked(self):
        """faction Aの秘密会話は faction B のSubへ渡らない。"""
        visible = _texts(filter_history_for_role(HISTORY, ROLES[1], ROLES))
        assert "A陣営の秘密指令" not in visible
        assert "Aの秘密報告" not in visible

    def test_own_faction_visible(self):
        visible = _texts(filter_history_for_role(HISTORY, ROLES[0], ROLES))
        assert "A陣営の秘密指令" in visible
        assert "Aの秘密報告" in visible

    def test_no_faction_speech_visible_to_all(self):
        """陣営なしの公開発言は誰からも見える。"""
        for viewer in ROLES:
            visible = _texts(filter_history_for_role(HISTORY, viewer, ROLES))
            assert "cの公開発言" in visible

    def test_narration_public(self):
        for viewer in ROLES:
            assert "夜が更けた。" in _texts(filter_history_for_role(HISTORY, viewer, ROLES))


class TestInnerVoice:
    def test_inner_voice_only_self(self):
        """inner_voice は本人以外のSubへ渡らない（Masterは無フィルタで見える）。"""
        assert "aの心の声" in _texts(filter_history_for_role(HISTORY, ROLES[0], ROLES))
        assert "aの心の声" not in _texts(filter_history_for_role(HISTORY, ROLES[1], ROLES))
        assert "aの心の声" not in _texts(filter_history_for_role(HISTORY, ROLES[2], ROLES))

    def test_inner_voice_hidden_even_without_factions(self):
        roles = [make_role("x"), make_role("y")]
        hist = [{"kind": "sub_inner", "role": "x", "text": "xの内心"}]
        assert "xの内心" in _texts(filter_history_for_role(hist, roles[0], roles))
        assert "xの内心" not in _texts(filter_history_for_role(hist, roles[1], roles))


class TestIntervention:
    def test_intervention_never_reaches_subs(self):
        for viewer in ROLES:
            assert "監督のメタ指示" not in _texts(filter_history_for_role(HISTORY, viewer, ROLES))


class TestPresence:
    """presence（在席者）可視性: presentが付いたイベントは不在者に見えない。"""

    ROLES2 = [make_role("a"), make_role("b")]
    HIST = [
        {"kind": "sub_to_master", "role": "a", "text": "密室での発言", "present": ["a"]},
        {"kind": "narration", "text": "密室の描写", "present": ["a"]},
        {"kind": "sub_to_master", "role": "a", "text": "presence無しの旧発言"},
    ]

    def test_absent_role_excluded(self):
        visible = _texts(filter_history_for_role(self.HIST, self.ROLES2[1], self.ROLES2))
        assert "密室での発言" not in visible
        assert "密室の描写" not in visible

    def test_present_role_sees(self):
        visible = _texts(filter_history_for_role(self.HIST, self.ROLES2[0], self.ROLES2))
        assert "密室での発言" in visible
        assert "密室の描写" in visible

    def test_legacy_events_unaffected(self):
        """presentの無い旧イベントは従来判定のみ（後方互換）。"""
        visible = _texts(filter_history_for_role(self.HIST, self.ROLES2[1], self.ROLES2))
        assert "presence無しの旧発言" in visible
