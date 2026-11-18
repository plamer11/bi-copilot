
from __future__ import annotations

import json
import uuid
from typing import Any

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.config import settings
from app.db.catalog import METRICS, TABLES
from app.db.history import (
    clear_session,
    load_recent,
    render_history,
    stats as history_stats,
)
from app.graph.build import aget_graph, new_thread_config
from app.guard.audit import log_event, read_events, stats as audit_stats
from app.guard.sql_guard import inspect
from app.tools.sqlite_tool import run_sql


FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(title="BI Copilot", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="自然语言业务问题")
    session_id: str | None = None


class ApproveRequest(BaseModel):
    session_id: str
    action: str = Field("approve", description="approve / edit / reject")
    sql: str | None = None


class SqlRequest(BaseModel):
    sql: str
    run: bool = Field(False, description="True 则真正执行（走守卫），False 只做检查")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _fresh_state(session_id: str, question: str) -> dict:

    return {
        "session_id": session_id,
        "question": question,


        "history": None,
        "standalone_question": "",
        "is_followup": False,
        "rewrite_reason": "",
        "decision": "",
        "clarify_question": "",
        "supervisor_reason": "",
        "recalled_tables": [],
        "schema_text": "",
        "sql": "",
        "repair_round": 0,
        "attempts": [],
        "guard_level": "",
        "guard_reasons": [],
        "guard_sql": "",
        "needs_approval": False,
        "approval_action": "",
        "edited_sql": "",
        "result_ok": False,
        "result_columns": [],
        "result_rows": [],
        "result_preview": "",
        "result_error": "",
        "row_count": 0,
        "answer": "",
        "chart_type": "",
        "error": "",
        "trace": [],
    }


def _final_payload(state: dict) -> dict:
    return {
        "type": "final",
        "ok": bool(state.get("answer")) and not state.get("error"),
        "answer": state.get("answer", ""),
        "chart_type": state.get("chart_type", "table"),
        "sql": state.get("guard_sql") or state.get("sql", ""),

        "standalone_question": state.get("standalone_question") or state.get("question", ""),
        "is_followup": bool(state.get("is_followup", False)),
        "columns": state.get("result_columns", []),
        "rows": state.get("result_rows", []),
        "row_count": state.get("row_count", 0),
        "attempts": state.get("attempts", []),
        "trace": state.get("trace", []),
        "error": state.get("error", ""),
    }


@app.get("/")
def index():

    idx = FRONTEND_DIR / "index.html"
    if not idx.exists():
        return {"message": "BI Copilot API 已启动；前端页面缺失，接口见 /api/health"}
    return FileResponse(idx)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "llm_configured": bool(settings.api_key),
        "model": settings.llm_model,
        "hitl_enabled": settings.enable_hitl,
        "max_repair_rounds": settings.max_repair_rounds,
        "multi_turn_enabled": True,
        "embedding_retrieval": settings.use_embedding_retrieval,
        "history": history_stats(),
    }


@app.post("/api/ask")
async def ask(req: AskRequest):

    session_id = req.session_id or f"s-{uuid.uuid4().hex[:8]}"
    graph = await aget_graph()
    cfg = new_thread_config(session_id)
    init = _fresh_state(session_id, req.question)

    async def gen():
        yield _sse("start", {"type": "start", "session_id": session_id, "question": req.question})
        try:
            async for chunk in graph.astream(init, cfg, stream_mode="updates"):
                for node, delta in chunk.items():
                    if node == "__interrupt__":
                        continue
                    if not isinstance(delta, dict):
                        continue
                    for t in delta.get("trace", []) or []:
                        yield _sse("trace", {"type": "trace", "node": t["node"], "detail": t["detail"]})
                    if delta.get("guard_sql"):
                        yield _sse("sql", {"type": "sql", "sql": delta["guard_sql"],
                                           "level": delta.get("guard_level", "")})
        except Exception as e:
            log_event(session_id, "error", message=str(e))
            yield _sse("error", {"type": "error", "message": f"执行失败: {e}"})
            return

        snapshot = await graph.aget_state(cfg)
        pending = list(snapshot.next or [])
        state = snapshot.values or {}

        if pending:
            interrupts = []
            for t in snapshot.tasks or []:
                interrupts.extend(getattr(i, "value", i) for i in (t.interrupts or []))
            payload = interrupts[0] if interrupts else {}
            log_event(session_id, "approval_required", sql=payload.get("sql", ""),
                      reasons=payload.get("reasons", []))
            yield _sse("approval_required", {
                "type": "approval_required",
                "session_id": session_id,
                "sql": payload.get("sql", ""),
                "reasons": payload.get("reasons", []),
                "message": "这条查询风险较高，需要你确认后才执行",
            })
            return

        ok = bool(state.get("answer")) and not state.get("error")
        log_event(session_id, "ask_done", ok=ok, sql=state.get("guard_sql", ""),
                  rows=state.get("row_count", 0), attempts=len(state.get("attempts", [])))
        yield _sse("final", _final_payload(state))

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/approve")
async def approve(req: ApproveRequest):

    graph = await aget_graph()
    cfg = new_thread_config(req.session_id)
    snapshot = await graph.aget_state(cfg)
    if not snapshot.next:
        raise HTTPException(404, "该会话没有待确认的查询")

    payload: dict[str, Any] = {"action": req.action}
    if req.sql:
        payload["sql"] = req.sql
    log_event(req.session_id, "approval_decision", action=req.action,
              edited=bool(req.sql), original_sql=(snapshot.values or {}).get("guard_sql", ""))

    try:
        out = await graph.ainvoke(Command(resume=payload), cfg)
    except Exception as e:
        log_event(req.session_id, "approval_failed", message=str(e))
        raise HTTPException(500, f"恢复失败: {e}")

    return _final_payload(out)


@app.get("/api/schema")
def schema(table: str | None = None):

    if table:
        if table not in TABLES:
            raise HTTPException(404, f"未知表: {table}")
        meta = TABLES[table]
        return {
            "table": table,
            "desc": meta["desc"],
            "columns": [
                {"name": c, "type": v["type"], "desc": v["desc"], "aliases": v["aliases"]}
                for c, v in meta["columns"].items()
            ],
        }
    return {
        "tables": [{"name": t, "desc": m["desc"], "columns": len(m["columns"])}
                   for t, m in TABLES.items()],
        "metrics": [{"name": m["name"], "expr": m["expr"], "note": m["note"]} for m in METRICS],
    }


@app.post("/api/sql")
def check_sql(req: SqlRequest):

    verdict = inspect(req.sql)
    out = {
        "level": verdict.level,
        "reasons": verdict.reasons,
        "sql": verdict.sql,
        "tables": verdict.tables,
    }
    if req.run and verdict.level in {"SAFE", "NEEDS_APPROVAL"}:
        res = run_sql(verdict.sql)
        out["result"] = {
            "ok": res.ok,
            "columns": res.columns,
            "rows": [list(r) for r in res.rows],
            "row_count": res.row_count,
            "error": res.error,
            "elapsed_ms": res.elapsed_ms,
        }
    return out


@app.get("/api/audit")
def audit(limit: int = 100, session_id: str | None = None):
    return {"events": read_events(limit=limit, session_id=session_id), "stats": audit_stats()}


@app.get("/api/history/{session_id}")
def get_history(session_id: str, limit: int = 5, rendered: bool = False):

    turns = load_recent(session_id, limit)
    out = {"session_id": session_id, "count": len(turns), "turns": turns}
    if rendered:
        out["rendered"] = render_history(turns)
    return out


@app.delete("/api/history/{session_id}")
def delete_history(session_id: str):

    return {"session_id": session_id, "deleted": clear_session(session_id)}


if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8001)
