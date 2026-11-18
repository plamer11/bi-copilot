
from __future__ import annotations

import aiosqlite
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, StateGraph

from app.config import settings
from app.graph.nodes import (
    analyst_node,
    approval_node,
    chitchat_node,
    clarify_node,
    exhausted_node,
    execute_node,
    guard_node,
    persist_node,
    reject_node,
    repair_node,
    rewrite_node,
    schema_node,
    supervisor_node,
    write_sql_node,
)
from app.graph.state import AgentState

MAX_ROUNDS = settings.max_repair_rounds
BACKEND_ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT_DB = BACKEND_ROOT / "data" / "checkpoints.db"

_GRAPH = None
_CONN = None


def route_after_supervisor(state: dict) -> str:
    d = state.get("decision", "query")
    return d if d in {"query", "clarify", "chitchat"} else "query"


def route_after_guard(state: dict) -> str:
    level = state.get("guard_level", "SAFE")
    if level == "BLOCKED":
        return "reject"
    if level == "UNPARSEABLE":
        return "repair" if state.get("repair_round", 0) < MAX_ROUNDS else "exhausted"
    if level == "NEEDS_APPROVAL":
        return "approval" if settings.enable_hitl else "execute"
    return "execute"


def route_after_approval(state: dict) -> str:
    return END if state.get("approval_action") == "reject" else "execute"


def route_after_execute(state: dict) -> str:
    if state.get("result_ok"):
        return "analyst"
    return "repair" if state.get("repair_round", 0) < MAX_ROUNDS else "exhausted"


async def aget_graph():

    g = StateGraph(AgentState)

    g.add_node("supervisor", supervisor_node)
    g.add_node("rewriter", rewrite_node)
    g.add_node("schema_agent", schema_node)
    g.add_node("sql_writer", write_sql_node)
    g.add_node("guard", guard_node)
    g.add_node("approval", approval_node)
    g.add_node("execute", execute_node)
    g.add_node("repair", repair_node)
    g.add_node("analyst", analyst_node)
    g.add_node("persist", persist_node)
    g.add_node("clarify", clarify_node)
    g.add_node("chitchat", chitchat_node)
    g.add_node("reject", reject_node)
    g.add_node("exhausted", exhausted_node)


    g.set_entry_point("rewriter")
    g.add_edge("rewriter", "supervisor")

    g.add_conditional_edges("supervisor", route_after_supervisor, {
        "query": "schema_agent",
        "clarify": "clarify",
        "chitchat": "chitchat",
    })
    g.add_edge("schema_agent", "sql_writer")
    g.add_edge("sql_writer", "guard")

    g.add_conditional_edges("guard", route_after_guard, {
        "reject": "reject",
        "approval": "approval",
        "execute": "execute",
        "repair": "repair",
        "exhausted": "exhausted",
    })

    g.add_conditional_edges("approval", route_after_approval, {
        "execute": "execute",
        END: END,
    })

    g.add_conditional_edges("execute", route_after_execute, {
        "analyst": "analyst",
        "repair": "repair",
        "exhausted": "exhausted",
    })


    g.add_edge("repair", "guard")


    g.add_edge("analyst", "persist")

    for leaf in ("persist", "clarify", "chitchat", "reject", "exhausted"):
        g.add_edge(leaf, END)

    global _GRAPH, _CONN
    if _GRAPH is None:
        CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)

        _CONN = await aiosqlite.connect(str(CHECKPOINT_DB))
        _GRAPH = g.compile(checkpointer=AsyncSqliteSaver(_CONN))
    return _GRAPH


async def aclose_graph() -> None:

    global _CONN, _GRAPH
    if _CONN is not None:
        await _CONN.close()
        _CONN = None

    _GRAPH = None


def new_thread_config(session_id: str) -> dict:

    return {"configurable": {"thread_id": session_id}}
