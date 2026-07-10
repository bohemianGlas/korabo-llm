"""LangGraph による1ターン分のグラフ定義。

master_node ──(action=call_sub)──> sub_node ──> END
     └──────(continue / finish)──────────────> END

セッション全体のループ（実行モード・一時停止・介入）は session.SessionRunner が
このグラフをターンごとに invoke することで制御する。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from langgraph.graph import END, StateGraph

from .schemas import MasterDecision

if TYPE_CHECKING:
    from .session import SessionRunner


class TurnState(TypedDict, total=False):
    decision: MasterDecision


def build_turn_graph(runner: "SessionRunner"):
    def master_node(state: TurnState) -> TurnState:
        decision = runner.run_master()
        return {"decision": decision}

    def sub_node(state: TurnState) -> TurnState:
        runner.run_sub(state["decision"])
        return {}

    def route(state: TurnState) -> str:
        d = state.get("decision")
        if d is not None and d.action == "call_sub" and d.target_role:
            return "sub"
        return END

    g = StateGraph(TurnState)
    g.add_node("master", master_node)
    g.add_node("sub", sub_node)
    g.set_entry_point("master")
    g.add_conditional_edges("master", route, {"sub": "sub", END: END})
    g.add_edge("sub", END)
    return g.compile()
