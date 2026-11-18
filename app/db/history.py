
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
HISTORY_DB = BACKEND_ROOT / "data" / "history.db"


DEFAULT_LOOKBACK = 3

_DDL = """
CREATE TABLE IF NOT EXISTS query_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    ts REAL NOT NULL,
    question TEXT NOT NULL,
    standalone_question TEXT NOT NULL DEFAULT '',
    sql TEXT NOT NULL DEFAULT '',
    tables TEXT NOT NULL DEFAULT '',
    row_count INTEGER NOT NULL DEFAULT 0,
    answer TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_turns_session ON query_turns(session_id, id);
"""


def _connect() -> sqlite3.Connection:
    HISTORY_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(HISTORY_DB))
    conn.executescript(_DDL)
    return conn


def save_turn(
    session_id: str,
    question: str,
    standalone_question: str = "",
    sql: str = "",
    tables: list[str] | None = None,
    row_count: int = 0,
    answer: str = "",
) -> None:

    if not session_id:
        return
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO query_turns"
            " (session_id, ts, question, standalone_question, sql, tables, row_count, answer)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                session_id,
                time.time(),
                question,
                standalone_question or question,
                sql,
                ",".join(tables or []),
                row_count,

                (answer or "")[:200],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def load_recent(session_id: str, limit: int = DEFAULT_LOOKBACK) -> list[dict]:

    if not session_id:
        return []
    conn = _connect()
    try:
        cur = conn.execute(
            "SELECT question, standalone_question, sql, tables, row_count, answer"
            " FROM query_turns WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    turns = [
        {
            "question": r[0],
            "standalone_question": r[1] or r[0],
            "sql": r[2],
            "tables": [t for t in (r[3] or "").split(",") if t],
            "row_count": r[4],
            "answer": r[5],
        }
        for r in reversed(rows)
    ]
    return turns


def render_history(turns: list[dict]) -> str:

    if not turns:
        return ""
    lines = []
    for i, t in enumerate(turns, 1):
        lines.append(
            f"{i}. 用户问：{t['question']}\n"
            f"   理解成：{t['standalone_question']}\n"
            f"   执行的 SQL：{t['sql'] or '（未执行）'}"
        )
    return "\n".join(lines)


def clear_session(session_id: str) -> int:

    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM query_turns WHERE session_id = ?", (session_id,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def stats() -> dict:
    conn = _connect()
    try:
        sessions = conn.execute("SELECT COUNT(DISTINCT session_id) FROM query_turns").fetchone()[0]
        turns = conn.execute("SELECT COUNT(*) FROM query_turns").fetchone()[0]
    finally:
        conn.close()
    return {"sessions": sessions, "turns": turns}
