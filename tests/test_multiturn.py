
from __future__ import annotations

import asyncio

from app.db.history import (
    clear_session,
    load_recent,
    render_history,
    save_turn,
    stats as history_stats,
)
from app.graph.nodes import (
    RewriteOutput,
    SupervisorDecision,
    effective_question,
    persist_node,
    rewrite_node,
)

SESSION = "mt-test-session"


def _run(coro):
    return asyncio.run(coro)


def setup_function():

    clear_session(SESSION)


def teardown_function():
    clear_session(SESSION)


def test_history_roundtrip_keeps_chronological_order():
    save_turn(SESSION, "上个月各品类销量", sql="SELECT category FROM products",
              tables=["products"], row_count=5, answer="Kitchen 最高")
    save_turn(SESSION, "那 Kitchen 呢？", standalone_question="Kitchen 品类上月销量",
              sql="SELECT sku FROM order_items LIMIT 5", row_count=2, answer="1.2 万件")

    turns = load_recent(SESSION, limit=5)
    assert len(turns) == 2

    assert turns[0]["question"] == "上个月各品类销量"
    assert turns[1]["standalone_question"] == "Kitchen 品类上月销量"


def test_history_limit_returns_latest_turns():
    for i in range(5):
        save_turn(SESSION, f"问题{i}", sql=f"SELECT {i}")
    turns = load_recent(SESSION, limit=2)
    assert [t["question"] for t in turns] == ["问题3", "问题4"]


def test_history_is_isolated_by_session():
    save_turn(SESSION, "属于本会话的问题")
    save_turn("mt-other-session", "属于别的会话的问题")
    try:
        assert len(load_recent(SESSION)) == 1
        assert load_recent(SESSION)[0]["question"] == "属于本会话的问题"
    finally:
        clear_session("mt-other-session")


def test_render_history_empty_when_no_turns():
    assert render_history([]) == ""
    assert render_history(load_recent("mt-nonexistent-session")) == ""


def test_render_history_contains_question_and_sql():
    save_turn(SESSION, "各品类销量", sql="SELECT category FROM products")
    text = render_history(load_recent(SESSION))
    assert "各品类销量" in text and "SELECT category" in text


def test_rewrite_skipped_without_history(structured_map):

    called = []
    structured_map[RewriteOutput] = RewriteOutput(
        is_followup=True, standalone_question="不该被调用", reason=""
    )

    out = rewrite_node({"session_id": "mt-empty-session", "question": "上个月各品类销量"})

    assert out["standalone_question"] == "上个月各品类销量"
    assert out["is_followup"] is False
    assert "跳过" in out["trace"][-1]["detail"]
    assert called == []


def test_rewrite_resolves_reference(structured_map):
    save_turn(SESSION, "上个月各品类销量", sql="SELECT category, SUM(quantity) FROM order_items")
    structured_map[RewriteOutput] = RewriteOutput(
        is_followup=True,
        standalone_question="Kitchen 品类上个月的销量是多少",
        reason="从上文补回指标=销量、时间=上个月",
    )

    out = rewrite_node({"session_id": SESSION, "question": "那 Kitchen 呢？"})

    assert out["is_followup"] is True
    assert out["standalone_question"] == "Kitchen 品类上个月的销量是多少"
    assert out["history"], "历史要回写进 state，persist 节点后面还要用"


def test_rewrite_degrades_to_original_on_llm_failure(monkeypatch):

    save_turn(SESSION, "上个月各品类销量")

    def _boom(schema=None, **kwargs):
        raise RuntimeError("DeepSeek 挂了")

    monkeypatch.setattr("app.graph.nodes.get_structured_llm", _boom)
    out = rewrite_node({"session_id": SESSION, "question": "那 Kitchen 呢？"})

    assert out["standalone_question"] == "那 Kitchen 呢？"
    assert out["is_followup"] is False
    assert "降级" in out["rewrite_reason"]


def test_rewrite_uses_state_history_without_db_hit(monkeypatch):

    monkeypatch.setattr(
        "app.graph.nodes.load_recent",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("不该查库")),
    )
    out = rewrite_node({
        "session_id": SESSION,
        "question": "原问句",
        "history": [],
    })
    assert out["standalone_question"] == "原问句"


def test_effective_question_prefers_standalone():
    assert effective_question({"question": "那 Kitchen 呢？",
                               "standalone_question": "Kitchen 品类上月销量"}) == "Kitchen 品类上月销量"
    assert effective_question({"question": "各品类销量"}) == "各品类销量"


def test_persist_writes_only_successful_turn():
    persist_node({
        "session_id": SESSION,
        "question": "那 Kitchen 呢？",
        "standalone_question": "Kitchen 品类上月销量",
        "guard_sql": "SELECT sku FROM order_items LIMIT 5",
        "recalled_tables": ["order_items"],
        "row_count": 3,
        "answer": "Kitchen 卖了 1.2 万件",
        "trace": [],
    })
    turns = load_recent(SESSION)
    assert len(turns) == 1
    assert turns[0]["standalone_question"] == "Kitchen 品类上月销量"
    assert turns[0]["row_count"] == 3


def test_persist_failure_does_not_break_turn(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("磁盘满了")

    monkeypatch.setattr("app.graph.nodes.save_turn", _boom)
    out = persist_node({"session_id": SESSION, "question": "x", "trace": []})
    assert "失败" in out["trace"][-1]["detail"]


def test_two_turns_second_uses_rewritten_question(structured_map, fake_text):

    from app.graph.build import aclose_graph, aget_graph, new_thread_config

    seen_prompts: list[str] = []

    def _capture(prompt: str) -> str:
        seen_prompts.append(prompt)
        return "SELECT sku, SUM(quantity) AS units FROM order_items GROUP BY sku LIMIT 5"

    import app.graph.nodes as nodes
    original = nodes._llm_text
    nodes._llm_text = _capture

    structured_map[SupervisorDecision] = SupervisorDecision(decision="query", reason="stub")
    structured_map[RewriteOutput] = RewriteOutput(
        is_followup=True,
        standalone_question="Kitchen 品类上个月的销量是多少",
        reason="补回指标与时间",
    )
    save_turn(SESSION, "上个月各品类销量", sql="SELECT category FROM products")

    async def _go():
        g = await aget_graph()
        try:
            return await g.ainvoke(
                {"session_id": SESSION, "question": "那 Kitchen 呢？"},
                new_thread_config(SESSION),
            )
        finally:
            await aclose_graph()

    try:
        out = _run(_go())
    finally:
        nodes._llm_text = original

    assert out["is_followup"] is True
    assert out["standalone_question"] == "Kitchen 品类上个月的销量是多少"

    writer_prompts = [p for p in seen_prompts if "写 SQL 的硬性要求" in p]
    assert writer_prompts, "没抓到 SQL Writer 的 prompt"
    assert "Kitchen 品类上个月的销量是多少" in writer_prompts[0]
    assert "上一轮查询" in writer_prompts[0], "追问时要把上一轮的 SQL 作为参考给进去"


def test_history_stats_reports_counts():
    save_turn(SESSION, "问题A")
    s = history_stats()
    assert s["sessions"] >= 1 and s["turns"] >= 1
