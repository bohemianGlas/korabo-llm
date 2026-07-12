"""場面パケット: Sub呼び出し時に渡す動的コンテキストの構造化と可視性フィルタ。

Subへ渡す情報の組立をここへ一元化する（「渡す前に除外」の単一の門）:
- recent_visible_events は filter_history_for_role を通した後の履歴のみ
- direct_perceptions は Master が本人の知覚として書いた message_to_role
- 身体・所持品は本人の記憶md「身体・所持品・現在状態」節から抽出
- excluded_kinds は可視性フィルタで除外された種別カウント（デバッグ用）
"""
from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field

from .master import filter_history_for_role, render_history
from .memory import extract_memory_section
from .schemas import MasterDecision, RoleConfig


class ScenePacket(BaseModel):
    """Subへ渡す1回分の場面コンテキスト（可視情報のみ）。"""
    scene_id: int = 0                 # = ターン番号
    location: str = ""
    time: str = ""
    present_roles: list[str] = Field(default_factory=list)
    known_constraints: str = ""
    recent_visible_events: str = ""   # 可視性フィルタ済みの直近経過（render済みテキスト）
    direct_perceptions: str = ""      # 本人が直接知覚した状況・応答のきっかけ（= message_to_role）
    physical_state: str = ""          # 本人の身体・所持品・現在状態（記憶mdの該当節より）
    excluded_kinds: dict[str, int] = Field(default_factory=dict)  # デバッグ: 除外種別→件数


def build_scene_packet(
    turn: int,
    decision: MasterDecision,
    viewer: RoleConfig,
    roles: list[RoleConfig],
    history: list[dict],
    memory_text: str = "",
    window: int = 20,
    lang: str = "ja",
) -> ScenePacket:
    """Master側の全情報から、viewer に見せてよい場面パケットを組み立てる。"""
    visible = filter_history_for_role(history, viewer, roles)

    # 除外された種別のカウント（デバッグ・検証用）
    all_kinds = Counter(e.get("kind", "?") for e in history)
    vis_kinds = Counter(e.get("kind", "?") for e in visible)
    excluded = {k: all_kinds[k] - vis_kinds.get(k, 0) for k in all_kinds if all_kinds[k] > vis_kinds.get(k, 0)}

    scene = decision.scene
    # 身体・所持品セクションは日英どちらの見出しでも拾う
    physical = extract_memory_section(memory_text, "身体") or extract_memory_section(memory_text, "Body")
    return ScenePacket(
        scene_id=turn,
        location=(scene.location if scene else "").strip(),
        time=(scene.time if scene else "").strip(),
        present_roles=list(scene.present_roles) if scene else [],
        known_constraints=(scene.constraints if scene else "").strip(),
        recent_visible_events=render_history(visible, window, lang),
        direct_perceptions=(decision.message_to_role or "").strip(),
        physical_state=physical,
        excluded_kinds=excluded,
    )


def render_scene_packet(packet: ScenePacket, roles: list[RoleConfig], lang: str = "ja") -> str:
    """場面パケットをSubのuserメッセージ用テキストブロックへ整形する。"""
    name_of = {r.id: (r.name or r.id) for r in roles}
    en = str(lang).lower().startswith("en")
    if en:
        lines = [f"# Current scene (only what you perceive; scene {packet.scene_id})", ""]
        lines.append(f"- Place: {packet.location or 'unknown'}")
        lines.append(f"- Time: {packet.time or 'unknown'}")
        if packet.present_roles:
            names = ", ".join(name_of.get(rid, rid) for rid in packet.present_roles)
            lines.append(f"- People present: {names}")
        if packet.known_constraints:
            lines.append(f"- Constraints here: {packet.known_constraints}")
        lines += ["", "## Recent progress you can see", ""]
        lines.append(packet.recent_visible_events or "(nothing has happened yet)")
        if packet.physical_state:
            lines += ["", "## Your body, belongings & current state (from your memory note)", ""]
            lines.append(packet.physical_state)
        lines += ["", "## What just happened (what you directly perceive)", ""]
        lines.append(packet.direct_perceptions or "(no notable change)")
        return "\n".join(lines)
    lines = [f"# 現在の場面（あなたが知覚している範囲・場面 {packet.scene_id}）", ""]
    lines.append(f"- 場所: {packet.location or '不明'}")
    lines.append(f"- 時刻: {packet.time or '不明'}")
    if packet.present_roles:
        names = "、".join(name_of.get(rid, rid) for rid in packet.present_roles)
        lines.append(f"- 居合わせている人物: {names}")
    if packet.known_constraints:
        lines.append(f"- この場の制約: {packet.known_constraints}")
    lines.append("")
    lines.append("## あなたから見える直近の経過")
    lines.append("")
    lines.append(packet.recent_visible_events or "（まだ何も起きていません）")
    if packet.physical_state:
        lines.append("")
        lines.append("## あなたの身体・所持品・現在状態（記憶メモより）")
        lines.append("")
        lines.append(packet.physical_state)
    lines.append("")
    lines.append("## いま起きたこと（あなたが直接知覚した状況）")
    lines.append("")
    lines.append(packet.direct_perceptions or "（特筆すべき変化はない）")
    return "\n".join(lines)


def packet_debug_summary(packet: ScenePacket) -> str:
    """full.md / コンソールDEBUG向けの1行要約。"""
    parts = [f"場面{packet.scene_id}"]
    if packet.location:
        parts.append(f"場所={packet.location}")
    if packet.time:
        parts.append(f"時刻={packet.time}")
    if packet.present_roles:
        parts.append(f"在席={','.join(packet.present_roles)}")
    if packet.excluded_kinds:
        ex = " ".join(f"{k}:{v}" for k, v in sorted(packet.excluded_kinds.items()))
        parts.append(f"除外[{ex}]")
    else:
        parts.append("除外なし")
    return " / ".join(parts)
