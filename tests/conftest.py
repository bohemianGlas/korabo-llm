"""pytest 共通設定: リポジトリrootをimport pathへ、作業ディレクトリをtmpへ。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def tmp_cwd(tmp_path, monkeypatch):
    """logs/ や記憶ファイルの書き込みをテスト用tmpへ隔離する。"""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def make_role(role_id: str, faction: str = "", name: str = "", **kw):
    from korabo.schemas import RoleConfig

    return RoleConfig(id=role_id, name=name or role_id, faction=faction, **kw)
