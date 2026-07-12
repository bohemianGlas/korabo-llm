"""設定・プロトコルのデータモデル定義。"""
from __future__ import annotations

import os
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# 設定 (config.jsonc)
# ---------------------------------------------------------------------------

class EndpointConfig(BaseModel):
    """OpenAI互換APIエンドポイント。base_url="mock" でダミー動作。"""
    base_url: str = ""
    api_key: str = ""
    api_key_env: str = ""
    default_model: str = ""
    max_retries: int = 2      # 一過性エラー時の追加試行回数（=最大 max_retries+1 回試行）
    retry_backoff: float = 1.5  # 指数バックオフの基準秒

    def resolve_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            return os.environ.get(self.api_key_env, "")
        return ""


class MasterConfig(BaseModel):
    endpoint: str = "mock"
    model: str = ""
    prompt_file: str = "data/master/master_prompt.md"
    temperature: float = 0.7
    important_prompt_file: str = "data/master/important_prompt.md"  # 重要プロンプト（作品の設計図）
    memory_file: str = "data/memories/_master.md"  # 語り手（Master）の外部記憶
    memory_enabled: bool = True  # Masterの記憶機能の有効・無効
    directive: str = ""  # 最優先指令（絶対厳守・systemの最上位に前置される。空なら無効）


class SubDefaults(BaseModel):
    endpoint: str = "mock"
    model: str = ""
    temperature: float = 0.8


class RoleConfig(BaseModel):
    id: str
    name: str = ""
    faction: str = ""   # 陣営（例: A / B / C）。空なら「設定なし」で影響を与えない
    endpoint: str = ""  # 空なら sub_defaults を使用
    model: str = ""     # 空なら endpoint の default_model / sub_defaults を使用
    temperature: Optional[float] = None
    role_prompt_file: str = ""
    memory_file: str = ""
    memory_enabled: bool = True  # このロール個別の記憶機能の有効・無効


class Dial(BaseModel):
    """作品の味付けダイヤル（ラベルは編集可、値は1〜10）。"""
    label: str = ""
    value: int = 5


class RunConfig(BaseModel):
    default_mode: str = "master_stop_limited"
    default_max_turns: int = 20
    target_main_chars: int = 0  # 目指すmain.mdの文字数（0で無効）
    default_style: str = ""
    dials: list[Dial] = Field(default_factory=list)
    sub_memory_enabled: bool = True    # サブ（キャラクターロール）全体の記憶機能の有効・無効
    sub_in_main_log: bool = True       # サブの生のセリフ・心情もメインログに反映するか
    sub_main_show_name: bool = True    # 生ブロックにロール名見出し（**名前**）を付けるか
    sub_main_show_action: bool = True  # 生ブロックに仕草・行動(action)を含めるか
    sub_main_show_inner: bool = True   # 生ブロックに（心の声）行を含めるか
    sub_main_inner_prefix: str = "（心の声）"  # 心の声の接頭辞（空文字・空白も可）
    narrative_style: str = "third"     # third / first / script / custom
    pov_role: str = ""                 # narrative_style=first のときの視点ロールid
    narrative_custom: str = ""         # narrative_style=custom のときの自由記述指示


class AppConfig(BaseModel):
    ui_lang: str = "ja"  # WebUIの表示言語 / UI display language ("ja" or "en")
    prompt_lang: str = "ja"  # システム指示プロンプトの言語 / system-instruction language ("ja" or "en")
    endpoints: dict[str, EndpointConfig] = Field(default_factory=dict)
    master: MasterConfig = Field(default_factory=MasterConfig)
    sub_defaults: SubDefaults = Field(default_factory=SubDefaults)
    roles: list[RoleConfig] = Field(default_factory=list)
    run: RunConfig = Field(default_factory=RunConfig)

    def get_role(self, role_id: str) -> Optional[RoleConfig]:
        for r in self.roles:
            if r.id == role_id:
                return r
        return None


# ---------------------------------------------------------------------------
# Master ⇔ Sub プロトコル
# ---------------------------------------------------------------------------

class SceneInfo(BaseModel):
    """Masterが申告する現在の場面情報（call_sub時・任意）。

    present_roles は「その場に居合わせているロールid」。設定されたターンの
    出来事は、不在ロールの履歴から自動的に除外される（presence可視性）。
    """
    location: str = ""
    time: str = ""
    present_roles: list[str] = Field(default_factory=list)
    constraints: str = ""

    @field_validator("present_roles", mode="before")
    @classmethod
    def _coerce_roles(cls, v):
        if isinstance(v, str):
            return [p.strip() for p in v.replace("、", ",").split(",") if p.strip()]
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return []


class MasterDecision(BaseModel):
    """MasterLLM の1ターンの出力。"""
    thought: str = ""
    narration: str = ""
    action: Literal["call_sub", "continue", "finish"] = "continue"
    target_role: str = ""
    message_to_role: str = ""
    memory_append: str = ""  # 語り手の記憶メモに残したい内容（記憶機能が有効なときのみ）
    scene: Optional[SceneInfo] = None  # 現在の場面（任意。不正な形状はNoneに落とす）

    @field_validator("scene", mode="before")
    @classmethod
    def _tolerant_scene(cls, v):
        # sceneフィールドの不備でMasterDecision全体のパースを壊さない
        if v is None or isinstance(v, SceneInfo):
            return v
        if isinstance(v, dict):
            try:
                return SceneInfo.model_validate(v)
            except Exception:
                return None
        return None


class SubResponse(BaseModel):
    """SubLLM（ロール）の応答。"""
    speech: str = ""       # セリフ（声に出す言葉）
    action: str = ""       # 言動・行動・仕草・表情
    inner_voice: str = ""  # 心の声・心情（内面。声には出さない）
    reply: str = ""        # 後方互換/フォールバック（旧形式の統合テキスト）
    memory_append: str = ""

    def outward_text(self) -> str:
        """他者（Master・同席者）から見える“表向き”のテキスト（心の声は含めない）。"""
        parts = []
        if self.action.strip():
            parts.append(self.action.strip())
        if self.speech.strip():
            parts.append(f"「{self.speech.strip()}」")
        if parts:
            return "\n".join(parts)
        return self.reply.strip()

    def main_log_block(
        self,
        name: str,
        show_name: bool = True,
        show_action: bool = True,
        show_inner: bool = True,
        inner_prefix: str = "（心の声）",
    ) -> str:
        """メインログ反映用の整形ブロック（トグルON時）。

        show_name=False で名前見出し、show_action=False で仕草(action)、
        show_inner=False で（心の声）行を省略。全てFalseなら「セリフ」のみになる。
        inner_prefix は心の声の接頭辞（空文字・空白も可。stripしない）。
        """
        lines: list[str] = []
        if show_name:
            lines.append(f"**{name}**")
        if show_action and self.action.strip():
            lines.append(self.action.strip())
        if self.speech.strip():
            lines.append(f"「{self.speech.strip()}」")
        if show_inner and self.inner_voice.strip():
            lines.append(f"{inner_prefix}{self.inner_voice.strip()}")
        has_content = any(not l.startswith("**") for l in lines)
        if not has_content and self.reply.strip():
            lines.append(self.reply.strip())
        return "\n\n".join(lines)
