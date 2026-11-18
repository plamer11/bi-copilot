
from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from app.agents.prompts import (
    ANALYST_PROMPT,
    CHITCHAT_PROMPT,
    REPAIR_PROMPT,
    REWRITE_PROMPT,
    SQL_WRITER_PROMPT,
    SUPERVISOR_PROMPT,
)
from app.config import settings
from app.db.embedder import resolve_embedder
from app.db.history import load_recent, render_history, save_turn
from app.db.schema_retriever import build_context
from app.guard.sql_guard import inspect
from app.llm import get_llm, get_structured_llm
from app.tools.sqlite_tool import render_preview, run_sql

MAX_ROUNDS = settings.max_repair_rounds


class SupervisorDecision(BaseModel):


    decision: str = Field(description="只能是 query / clarify / chitchat 之一")
    clarify_question: str = Field(default="", description="判定为 clarify 时，要反问用户的那一句话")
    reason: str = Field(default="", description="一句话说明判定依据")


class AnalystOutput(BaseModel):


    answer: str = Field(description="给运营看的中文结论，含关键数字")
    chart_type: str = Field(default="table", description="bar / line / pie / table 之一")


class RewriteOutput(BaseModel):


    is_followup: bool = Field(description="本轮是否依赖上文才能理解")
    standalone_question: str = Field(description="补全上下文后可独立理解的完整问句")
    reason: str = Field(default="", description="一句话说明补全了什么")


def _trace(state: dict, node: str, detail: str) -> list[dict]:
    return list(state.get("trace", [])) + [{"node": node, "detail": detail}]


def extract_sql(raw: str) -> str:

    if not raw:
        return ""
    t = raw.strip()
    m = re.search(r"```(?:sql)?\s*(.*?)```", t, re.S | re.I)
    if m:
        t = m.group(1).strip()
    t = t.strip().rstrip(";").strip()

    if not re.match(r"^\s*(select|with)\b", t, re.I):
        idx = t.upper().find("SELECT")
        if idx > 0:
            t = t[idx:]
    return t.strip()


def _llm_text(prompt: str) -> str:
    resp = get_llm().invoke([HumanMessage(content=prompt)])
    return (resp.content or "").strip()


def effective_question(state: dict) -> str:

    return state.get("standalone_question") or state.get("question", "")


def supervisor_node(state: dict) -> dict:

    q = effective_question(state)
    try:
        llm = get_structured_llm(SupervisorDecision)
        res = llm.invoke([HumanMessage(content=SUPERVISOR_PROMPT.format(question=q))])
        decision = res.decision.strip().lower()
        if decision not in {"query", "clarify", "chitchat"}:
            decision = "query"
    except Exception as e:
        decision = "query"
        res = None

    clarify = getattr(res, "clarify_question", "") or ""
    reason = getattr(res, "reason", "") or (f"调度失败已降级为直接查询: {e}" if decision == "query" else "")
    return {
        "decision": decision,
        "clarify_question": clarify,
        "supervisor_reason": reason,
        "trace": _trace(state, "supervisor", f"判定={decision}"),
    }


def chitchat_node(state: dict) -> dict:

    try:
        answer = _llm_text(CHITCHAT_PROMPT.format(question=effective_question(state)))
    except Exception as e:
        answer = f"（闲聊回复生成失败）{e}"
    return {
        "answer": answer,
        "chart_type": "table",
        "trace": _trace(state, "chitchat", "闲聊直答"),
    }


def clarify_node(state: dict) -> dict:

    return {
        "answer": f"需要先确认一下：{state.get('clarify_question') or '你想看哪个时间段、哪个品类的数据？'}",
        "chart_type": "table",
        "trace": _trace(state, "clarify", "反问用户补充条件"),
    }


def rewrite_node(state: dict) -> dict:

    question = state.get("question", "")


    raw_history = state.get("history")
    if raw_history is None:
        history = load_recent(state.get("session_id", ""))
    else:
        history = raw_history

    if not history:
        return {
            "history": [],
            "standalone_question": question,
            "is_followup": False,
            "rewrite_reason": "无历史，跳过改写",
            "trace": _trace(state, "rewriter", "无历史，跳过改写"),
        }

    prompt = REWRITE_PROMPT.format(history=render_history(history), question=question)
    try:
        llm = get_structured_llm(RewriteOutput)
        out = llm.invoke([HumanMessage(content=prompt)])
        standalone = (out.standalone_question or "").strip() or question
        is_followup = bool(out.is_followup)
        reason = out.reason or ""
    except Exception as e:

        standalone, is_followup, reason = question, False, f"改写失败已降级: {e}"

    return {
        "history": history,
        "standalone_question": standalone,
        "is_followup": is_followup,
        "rewrite_reason": reason,
        "trace": _trace(
            state, "rewriter",
            f"追问改写={is_followup} → {standalone[:60]}",
        ),
    }


def schema_node(state: dict) -> dict:

    ctx = build_context(
        effective_question(state),
        top_k=settings.schema_top_k,
        top_n_cols=settings.schema_top_n_cols,
        embedder=resolve_embedder(),
    )
    return {
        "recalled_tables": ctx.tables,
        "schema_text": ctx.render(),
        "trace": _trace(state, "schema_agent", f"召回 {len(ctx.tables)} 张表: {', '.join(ctx.tables)}"),
    }


def _history_hint(state: dict) -> str:

    if not state.get("is_followup"):
        return ""
    history = state.get("history") or []
    if not history:
        return ""
    prev = history[-1]
    return (
        "## 上一轮查询（本轮是它的追问，沿用同样的指标口径与过滤条件，只换维度）\n"
        f"上一轮问句：{prev.get('standalone_question', '')}\n"
        f"上一轮 SQL：\n```sql\n{prev.get('sql', '')}\n```"
    )


def write_sql_node(state: dict) -> dict:

    prompt = SQL_WRITER_PROMPT.format(
        schema_context=state.get("schema_text", ""),
        question=effective_question(state),
        history_hint=_history_hint(state),
    )
    try:
        sql = extract_sql(_llm_text(prompt))
    except Exception as e:
        return {
            "sql": "", "error": f"生成 SQL 失败: {e}", "repair_round": 0,
            "attempts": [{"round": 0, "sql": "", "error": str(e)}],
            "trace": _trace(state, "sql_writer", f"生成失败: {e}"),
        }
    return {
        "sql": sql,
        "repair_round": 0,
        "attempts": [{"round": 0, "sql": sql, "error": ""}],
        "trace": _trace(state, "sql_writer", f"生成 SQL: {sql[:80]}"),
    }


def repair_node(state: dict) -> dict:

    attempts = state.get("attempts", [])
    last = attempts[-1] if attempts else {"sql": state.get("sql", ""), "error": state.get("result_error", "")}
    round_no = int(state.get("repair_round", 0)) + 1

    error_msg = last.get("error") or state.get("result_error", "")
    prompt = REPAIR_PROMPT.format(
        schema_context=state.get("schema_text", ""),
        failed_sql=last.get("sql", ""),
        error=error_msg,
        question=effective_question(state),
    )
    try:
        sql = extract_sql(_llm_text(prompt))
    except Exception as e:
        sql = ""
        error_msg = f"{error_msg} | 修复调用失败: {e}"


    return {
        "sql": sql,
        "repair_round": round_no,
        "attempts": attempts + [{"round": round_no, "sql": sql, "error": ""}],
        "trace": _trace(state, "repair", f"第 {round_no} 轮修复（{error_msg[:40]}）"),
    }


def guard_node(state: dict) -> dict:

    sql = state.get("sql", "")
    verdict = inspect(sql)
    trace_msg = f"{verdict.level}: {verdict.explain()[:60]}"


    return {
        "guard_level": verdict.level,
        "guard_reasons": verdict.reasons,
        "guard_sql": verdict.sql,
        "result_error": verdict.explain() if verdict.level == "UNPARSEABLE" else "",
        "trace": _trace(state, "guard", trace_msg),
    }


def approval_node(state: dict) -> dict:

    payload = {
        "type": "approval_required",
        "sql": state.get("guard_sql", ""),
        "reasons": state.get("guard_reasons", []),
        "question": state.get("question", ""),
    }
    decision = interrupt(payload)
    action = "approve"
    edited = ""
    if isinstance(decision, dict):
        action = str(decision.get("action", "approve")).lower()
        edited = str(decision.get("sql", "") or "")
    elif isinstance(decision, str):
        action = decision.lower()

    if action == "reject":
        return {
            "approval_action": "reject",
            "answer": "这次查询已被你取消，没有执行任何语句。",
            "chart_type": "table",
            "trace": _trace(state, "approval", "人工拒绝执行"),
        }

    if action == "edit" and edited:
        recheck = inspect(edited)
        if recheck.blocked:
            return {
                "approval_action": "reject",
                "answer": f"修改后的 SQL 未通过安全检查：{recheck.explain()}",
                "chart_type": "table",
                "trace": _trace(state, "approval", f"人工改写后被守卫拒绝: {recheck.explain()[:40]}"),
            }
        final_sql = recheck.sql
    else:
        final_sql = state.get("guard_sql", "")

    return {
        "approval_action": action,
        "edited_sql": edited,
        "guard_sql": final_sql,
        "guard_level": "SAFE",
        "trace": _trace(state, "approval", f"人工决策={action}"),
    }


def execute_node(state: dict) -> dict:

    sql = state.get("guard_sql") or state.get("sql", "")
    res = run_sql(sql)
    if not res.ok:
        attempts = state.get("attempts", [])
        attempts = attempts[:-1] + [{**attempts[-1], "error": res.error}] if attempts else [
            {"round": 0, "sql": sql, "error": res.error}
        ]
        return {
            "result_ok": False,
            "result_error": res.error,
            "result_preview": "",
            "row_count": 0,
            "attempts": attempts,
            "trace": _trace(state, "executor", f"执行失败: {res.error[:60]}"),
        }
    preview = render_preview(res, max_rows=20)
    return {
        "result_ok": True,
        "result_error": "",
        "result_columns": res.columns,
        "result_rows": [list(r) for r in res.rows],
        "result_preview": preview,
        "row_count": res.row_count,
        "trace": _trace(state, "executor", f"返回 {res.row_count} 行，耗时 {res.elapsed_ms}ms"),
    }


def analyst_node(state: dict) -> dict:

    prompt = ANALYST_PROMPT.format(
        question=effective_question(state),
        sql=state.get("guard_sql", ""),
        preview=state.get("result_preview", ""),
        row_count=state.get("row_count", 0),
    )
    try:
        llm = get_structured_llm(AnalystOutput)
        out = llm.invoke([HumanMessage(content=prompt)])
        answer, chart = out.answer, (out.chart_type or "table").lower()
        if chart not in {"bar", "line", "pie", "table"}:
            chart = "table"
    except Exception as e:

        try:
            answer = _llm_text(prompt)
        except Exception as e2:
            answer = f"查询已执行，但结论生成失败：{e2}"
        chart = "table"
    return {
        "answer": answer,
        "chart_type": chart,
        "trace": _trace(state, "analyst", f"生成结论（{chart} 图）"),
    }


def persist_node(state: dict) -> dict:

    try:
        save_turn(
            session_id=state.get("session_id", ""),
            question=state.get("question", ""),
            standalone_question=effective_question(state),
            sql=state.get("guard_sql") or state.get("sql", ""),
            tables=state.get("recalled_tables", []),
            row_count=state.get("row_count", 0),
            answer=state.get("answer", ""),
        )
        detail = "已写入会话历史"
    except Exception as e:

        detail = f"写入历史失败（不影响本轮）: {e}"
    return {"trace": _trace(state, "persist", detail)}


def reject_node(state: dict) -> dict:

    reasons = "；".join(state.get("guard_reasons", []))
    return {
        "answer": f"这条查询被安全策略拦截，无法执行：{reasons}。如需查询明细请缩小范围或联系数据同学。",
        "chart_type": "table",
        "error": f"GUARD_BLOCKED: {reasons}",
        "trace": _trace(state, "blocked", f"拦截: {reasons[:60]}"),
    }


def exhausted_node(state: dict) -> dict:

    attempts = state.get("attempts", [])
    last_err = attempts[-1]["error"] if attempts else "未知错误"
    return {
        "answer": (
            f"试了 {len(attempts)} 轮还是没查出来，最后一次报错是：{last_err}。"
            "可以换个说法（比如把时间范围或品类说具体些），我再试一次。"
        ),
        "chart_type": "table",
        "error": f"REPAIR_EXHAUSTED: {last_err}",
        "trace": _trace(state, "exhausted", f"{len(attempts)} 轮修复后仍失败"),
    }
