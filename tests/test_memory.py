"""記憶テスト: 旧形式互換・構造化テンプレ・タグルーティング・重複抑制。"""
from __future__ import annotations

from korabo.memory import (
    MASTER_STATE_SECTIONS,
    MEMORY_SECTIONS,
    append_memory,
    extract_memory_section,
    master_state_template,
    memory_template,
    read_memory,
)


class TestTemplates:
    def test_role_template_has_all_sections(self):
        t = memory_template("アリス")
        assert t.startswith("# アリス の記憶メモ")
        for s in MEMORY_SECTIONS:
            assert f"## {s}" in t

    def test_master_template_has_all_sections(self):
        t = master_state_template()
        for s in MASTER_STATE_SECTIONS:
            assert f"## {s}" in t


class TestLegacyCompat:
    def test_old_freeform_append_unchanged(self, tmp_path):
        """見出しの無い旧形式ファイルへは従来どおりタイムスタンプ追記。"""
        p = tmp_path / "old.md"
        p.write_text("# 旧メモ\n\n昔の記録。\n", encoding="utf-8")
        assert append_memory(p, "新しい出来事") is True
        text = read_memory(p)
        assert "昔の記録。" in text          # 旧内容を破壊しない
        assert "新しい出来事" in text
        assert "## " in text                 # タイムスタンプ見出しで追記

    def test_tag_without_headings_falls_back(self, tmp_path):
        """タグ付きでも見出しが無ければfallback追記（旧ファイルを壊さない）。"""
        p = tmp_path / "old2.md"
        p.write_text("# 旧メモ\n", encoding="utf-8")
        assert append_memory(p, "［伝聞］誰かから聞いた話", turn=3) is True
        text = read_memory(p)
        assert "誰かから聞いた話" in text
        assert "## T3" in text  # タイムスタンプ見出し（ターン付き）

    def test_missing_file_created(self, tmp_path):
        p = tmp_path / "sub" / "new.md"
        assert append_memory(p, "初記録") is True
        assert "初記録" in read_memory(p)


class TestTagRouting:
    def test_routes_to_matching_section(self, tmp_path):
        p = tmp_path / "mem.md"
        p.write_text(memory_template("アキラ"), encoding="utf-8")
        assert append_memory(p, "［伝聞］佐伯が倉庫の鍵を持っていると本人から聞いた", turn=12) is True
        section = extract_memory_section(read_memory(p), "聞いた")
        assert "佐伯が倉庫の鍵を持っている" in section
        assert "［T12］" in section

    def test_multiple_tags_route_to_own_sections(self, tmp_path):
        p = tmp_path / "mem.md"
        p.write_text(memory_template("アキラ"), encoding="utf-8")
        append_memory(p, "［事実］地下室で血痕を直接確認した", turn=15)
        append_memory(p, "［推測］美紀が何かを隠していると疑っている", turn=15)
        append_memory(p, "［状態］左腕を負傷した", turn=16)
        text = read_memory(p)
        assert "血痕" in extract_memory_section(text, "事実")
        assert "美紀" in extract_memory_section(text, "推測")
        assert "左腕" in extract_memory_section(text, "状態")
        # 事実と推測が別セクションに区別される
        assert "美紀" not in extract_memory_section(text, "事実")

    def test_master_state_tags(self, tmp_path):
        p = tmp_path / "master.md"
        p.write_text(master_state_template(), encoding="utf-8")
        append_memory(p, "［予定］次章で正体が明かされる予定", turn=8)
        append_memory(p, "［未解決］手紙の差出人が不明のまま", turn=8)
        text = read_memory(p)
        assert "正体" in extract_memory_section(text, "予定")
        assert "手紙" in extract_memory_section(text, "未解決")


class TestDedup:
    def test_exact_duplicate_skipped(self, tmp_path):
        p = tmp_path / "mem.md"
        p.write_text(memory_template("アキラ"), encoding="utf-8")
        assert append_memory(p, "［事実］同じ内容", turn=1) is True
        before = read_memory(p)
        assert append_memory(p, "［事実］同じ内容", turn=2) is False
        assert read_memory(p) == before  # ファイル不変

    def test_duplicate_detected_across_tags(self, tmp_path):
        """タグや ［T..］メタが違っても本文が同一ならスキップ。"""
        p = tmp_path / "mem.md"
        p.write_text(memory_template("アキラ"), encoding="utf-8")
        assert append_memory(p, "［事実］鍵は佐伯が持っている", turn=1) is True
        assert append_memory(p, "鍵は佐伯が持っている", turn=9) is False

    def test_different_content_appended(self, tmp_path):
        p = tmp_path / "mem.md"
        p.write_text(memory_template("アキラ"), encoding="utf-8")
        assert append_memory(p, "［事実］内容A") is True
        assert append_memory(p, "［事実］内容B") is True


class TestExtractSection:
    def test_extract_and_missing(self):
        text = "# x\n\n## 身体・所持品・現在状態\n\n- 元気\n\n## 未完了の行動\n\n- 手紙を出す\n"
        assert extract_memory_section(text, "身体") == "- 元気"
        assert extract_memory_section(text, "未完了") == "- 手紙を出す"
        assert extract_memory_section(text, "存在しない") == ""
        assert extract_memory_section("", "身体") == ""
