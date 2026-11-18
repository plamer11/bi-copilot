
from __future__ import annotations

import asyncio

import pytest

from app.config import settings
from app.graph.build import aclose_graph, aget_graph, new_thread_config
from app.graph.build import (
    route_after_approval,
    route_after_execute,
    route_after_guard,
    route_after_supervisor,
)


def _run(coro):

    return asyncio.run(coro)


def test_route_after_supervisor():
    assert route_after_supervisor({"decision": "clarify"}) == "clarify"
    assert route_after_supervisor({"decision": "chitchat"}) == "chitchat"
    assert route_after_supervisor({"decision": "query"}) == "query"
    assert route_after_supervisor({}) == "query"
    assert route_after_supervisor({"decision": "投诉"}) == "query"


def test_route_after_guard():
    assert route_after_guard({"guard_level": "BLOCKED"}) == "reject"
    assert route_after_guard({"guard_level": "SAFE"}) == "execute"
    assert route_after_guard({"guard_level": "UNPARSEABLE", "repair_round": 0}) == "repair"
    assert route_after_guard({"guard_level": "UNPARSEABLE", "repair_round": 3}) == "exhausted"
    assert route_after_guard({"guard_level": "NEEDS_APPROVAL"}) == "approval"


def test_route_after_guard_respects_hitl_switch(monkeypatch):
    monkeypatch.setattr(settings, "enable_hitl", False)
    assert route_after_guard({"guard_level": "NEEDS_APPROVAL"}) == "execute"


def test_route_after_execute():
    assert route_after_execute({"result_ok": True}) == "analyst"
    assert route_after_execute({"result_ok": False, "repair_round": 0}) == "repair"
    assert route_after_execute({"result_ok": False, "repair_round": 3}) == "exhausted"


def test_route_after_approval():
    assert route_after_approval({"approval_action": "reject"}) == "__end__"
    assert route_after_approval({"approval_action": "approve"}) == "execute"
    assert route_after_approval({"approval_action": "edit"}) == "execute"


def test_repair_loop_recovers_from_bad_column(fake_structured, fake_text):

    fake_text([
        "SELECT sku, SUM(quantity_sold) AS units FROM order_items GROUP BY sku LIMIT 5",
        "SELECT sku, SUM(quantity) AS units FROM order_items GROUP BY sku LIMIT 5",
    ])

    async def _go():
        g = await aget_graph()
        try:
            return await g.ainvoke(
                {"session_id": "t-repair", "question": "销量最高的 SKU"},
                new_thread_config("t-repair"),
            )
        finally:
            await aclose_graph()

    out = _run(_go())
    assert out["result_ok"] is True
    assert out["repair_round"] == 1
    assert len(out["attempts"]) == 2

    assert "no such column" in out["attempts"][0]["error"]
    assert out["attempts"][1]["error"] == ""


def test_exhausted_after_max_rounds(fake_structured, fake_text):

    fake_text(["SELECT bad_col FROM products LIMIT 5"] * (settings.max_repair_rounds + 1))

    async def _go():
        g = await aget_graph()
        try:
            return await g.ainvoke(
                {"session_id": "t-exhaust", "question": "销量"},
                new_thread_config("t-exhaust"),
            )
        finally:
            await aclose_graph()

    out = _run(_go())
    assert out["result_ok"] is False
    assert out["repair_round"] == settings.max_repair_rounds
    assert "REPAIR_EXHAUSTED" in out.get("error", "")
    assert out["answer"]


def test_guard_blocked_does_not_retry(fake_structured, fake_text):

    fake_text(["DELETE FROM orders"])

    async def _go():
        g = await aget_graph()
        try:
            return await g.ainvoke(
                {"session_id": "t-block", "question": "把所有订单删掉"},
                new_thread_config("t-block"),
            )
        finally:
            await aclose_graph()

    out = _run(_go())
    assert out["guard_level"] == "BLOCKED"
    assert "拦截" in out["answer"]
    assert out.get("result_rows", []) == []


def test_successful_query_produces_answer_and_chart(fake_structured, fake_text):
    fake_text([
        "SELECT p.category, SUM(oi.quantity) AS units FROM order_items oi "
        "JOIN products p ON oi.sku = p.sku GROUP BY p.category LIMIT 10"
    ])

    async def _go():
        g = await aget_graph()
        try:
            return await g.ainvoke(
                {"session_id": "t-ok", "question": "各品类销量"},
                new_thread_config("t-ok"),
            )
        finally:
            await aclose_graph()

    out = _run(_go())
    assert out["result_ok"] is True
    assert out["row_count"] > 0
    assert out["answer"]
    assert out["chart_type"] in {"bar", "line", "pie", "table"}

    nodes_seen = [t["node"] for t in out["trace"]]
    for n in ("supervisor", "schema_agent", "sql_writer", "guard", "executor", "analyst"):
        assert n in nodes_seen


def test_hitl_suspends_and_resumes(fake_structured, fake_text):

    fake_text([
        "SELECT * FROM orders",
    ])

    async def _go():
        from langgraph.types import Command
        g = await aget_graph()
        cfg = new_thread_config("t-hitl")
        try:
            out = await g.ainvoke(
                {"session_id": "t-hitl", "question": "导出订单明细"},
                cfg,
            )
            assert out["__interrupt__"], "应当挂起等待确认"
            payload = out["__interrupt__"][0].value
            assert payload["type"] == "approval_required"
            assert "orders" in payload["sql"]

            resumed = await g.ainvoke(
                Command(resume={"action": "edit",
                                "sql": "SELECT order_id FROM orders LIMIT 20"}),
                cfg,
            )
            return resumed
        finally:
            await aclose_graph()

    out = _run(_go())
    assert out["approval_action"] == "edit"
    assert out["result_ok"] is True


def test_hitl_reject_stops_execution(fake_structured, fake_text):
    fake_text(["SELECT * FROM orders"])

    async def _go():
        from langgraph.types import Command
        g = await aget_graph()
        cfg = new_thread_config("t-hitl-no")
        try:
            await g.ainvoke({"session_id": "t-hitl-no", "question": "导出订单明细"}, cfg)
            return await g.ainvoke(Command(resume={"action": "reject"}), cfg)
        finally:
            await aclose_graph()

    out = _run(_go())
    assert out["approval_action"] == "reject"
    assert not out.get("result_rows")
    assert "取消" in out["answer"]
