"""統合テスト: 台本スタブLLMで Master→Sub→記憶→可視性 の一連を SessionRunner 経由で確認。"""
from __future__ import annotations

import json
import time

import pytest

from korabo.memory import extract_memory_section, memory_template, read_memory
from korabo.schemas import AppConfig, EndpointConfig, MasterConfig, RoleConfig
from korabo.session import SessionRunner


class ScriptedClient:
    """決められた応答を順に返し、受け取ったmessagesを記録するスタブ。"""
    model = "stub"
    last_usage = None

    def __init__(self, outputs: list[str]):
        self.outputs = list(outputs)
        self.calls: list[list[dict]] = []

    def chat(self, messages, on_retry=None):
        self.calls.append(messages)
        if len(self.outputs) > 1:
            return self.outputs.pop(0)
        return self.outputs[0]


def _cfg(tmp_path) -> AppConfig:
    mem_a = tmp_path / "mem_a.md"
    mem_b = tmp_path / "mem_b.md"
    mem_a.write_text(memory_template("アキラ"), encoding="utf-8")
    mem_b.write_text(memory_template("ベル"), encoding="utf-8")
    return AppConfig(
        endpoints={"mock": EndpointConfig(base_url="mock")},
        master=MasterConfig(endpoint="mock", memory_enabled=False),
        roles=[
            RoleConfig(id="a", name="アキラ", faction="A", endpoint="mock", memory_file=str(mem_a)),
            RoleConfig(id="b", name="ベル", faction="B", endpoint="mock", memory_file=str(mem_b)),
        ],
    )


def _md(action, target="", message="", narration="", scene=None):
    d = {"thought": "t", "narration": narration, "action": action,
         "target_role": target, "message_to_role": message, "memory_append": ""}
    if scene:
        d["scene"] = scene
    return json.dumps(d, ensure_ascii=False)


def _sr(speech, action="", inner="", memory=""):
    return json.dumps(
        {"speech": speech, "action": action, "inner_voice": inner, "memory_append": memory},
        ensure_ascii=False,
    )


def _run(runner, timeout=15.0):
    runner.start()
    t0 = time.time()
    while runner.is_active and time.time() - t0 < timeout:
        time.sleep(0.05)
    assert not runner.is_active, "セッションがタイムアウトまでに終わらない"


@pytest.fixture
def scripted_session(tmp_cwd):
    cfg = _cfg(tmp_cwd)
    runner = SessionRunner(cfg, "港町の物語。", "master_stop_limited", 10)

    master = ScriptedClient([
        # T1: aだけの場面（presence）で秘密の知覚を渡す
        _md("call_sub", "a", "誰もいない倉庫で古い書類を見つけた。",
            scene={"location": "倉庫", "time": "夜", "present_roles": ["a"]}),
        # T2: aを再度呼ぶ（更新記憶が渡ることを確認）
        _md("call_sub", "a", "書類をどうするか決める時だ。",
            scene={"location": "倉庫", "time": "夜", "present_roles": ["a"]}),
        # T3: bを呼ぶ（a限定情報が漏れないことを確認）
        _md("call_sub", "b", "広場で汽笛が鳴った。",
            scene={"location": "広場", "time": "朝", "present_roles": ["b"]}),
        # T4: 終了
        _md("finish", narration="物語は幕を閉じた。"),
    ])
    sub_a = ScriptedClient([
        _sr("これは……帳簿だ", action="埃を払って書類の束を開こうとする",
            inner="誰かに見られていないだろうか", memory="［伝聞］三枝が金庫の番号を知っていると聞いた"),
        # 同じmemory_appendを再送 → 重複スキップされるべき
        _sr("持ち帰って調べよう", memory="［伝聞］三枝が金庫の番号を知っていると聞いた"),
    ])
    sub_b = ScriptedClient([_sr("いい朝ね")])

    runner._master_client = master
    runner._sub_clients["a"] = sub_a
    runner._sub_clients["b"] = sub_b
    _run(runner)
    return cfg, runner, master, sub_a, sub_b


class TestIntegration:
    def test_master_calls_sub_and_finishes(self, scripted_session):
        _, runner, master, sub_a, sub_b = scripted_session
        assert runner.finished
        assert len(sub_a.calls) == 2 and len(sub_b.calls) == 1

    def test_sub_attempt_reaches_master(self, scripted_session):
        """Subの「試み」（action）が次のMasterコンテキストへ渡る。"""
        _, _, master, _, _ = scripted_session
        second_master_prompt = "\n".join(m["content"] for m in master.calls[1])
        assert "開こうとする" in second_master_prompt

    def test_tagged_memory_routed_to_section(self, scripted_session):
        cfg, _, _, _, _ = scripted_session
        text = read_memory(cfg.roles[0].memory_file)
        assert "三枝が金庫の番号" in extract_memory_section(text, "聞いた")

    def test_duplicate_memory_skipped(self, scripted_session):
        cfg, runner, _, _, _ = scripted_session
        text = read_memory(cfg.roles[0].memory_file)
        assert text.count("三枝が金庫の番号") == 1  # 2回送っても1件
        full = (runner.logger.dir / "full.md").read_text(encoding="utf-8")
        assert "重複スキップ" in full

    def test_updated_memory_used_next_call(self, scripted_session):
        """1回目のmemory_appendが2回目のSub呼び出しのsystemに載る。"""
        _, _, _, sub_a, _ = scripted_session
        second_system = sub_a.calls[1][0]["content"]
        assert "三枝が金庫の番号" in second_system

    def test_no_leak_to_other_faction_or_absent(self, scripted_session):
        """a限定の場面情報・aの心の声・aの記憶が b のプロンプトへ漏れない。"""
        _, _, _, _, sub_b = scripted_session
        b_prompt = "\n".join(m["content"] for m in sub_b.calls[0])
        assert "書類" not in b_prompt          # presence + faction で遮蔽
        assert "誰かに見られていない" not in b_prompt  # aの心の声
        assert "三枝が金庫の番号" not in b_prompt   # aの専用記憶

    def test_scene_packet_logged(self, scripted_session):
        _, runner, _, _, _ = scripted_session
        full = (runner.logger.dir / "full.md").read_text(encoding="utf-8")
        assert "場面パケット" in full


class TestMockE2E:
    def test_mock_run_without_scene_still_works(self, tmp_cwd):
        """既定のMockLLM（scene無し応答）でも従来どおり完走する（後方互換）。"""
        cfg = _cfg(tmp_cwd)
        runner = SessionRunner(cfg, "モック検証。", "master_stop_limited", 10)
        _run(runner, timeout=25.0)
        assert runner.finished and runner._error is None
        assert runner.turn >= 6  # MockはT6でfinish
