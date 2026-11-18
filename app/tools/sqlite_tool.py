
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

MAX_ROWS = 200
QUERY_TIMEOUT_SEC = 5.0


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = BACKEND_ROOT / "data" / "app.db"


@dataclass
class QueryResult:
    ok: bool
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    error: str = ""
    elapsed_ms: int = 0


def _connect_readonly() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"数据库不存在: {DB_PATH}，请先运行 python -m app.db.seed")
    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True, timeout=QUERY_TIMEOUT_SEC)
    con.execute("PRAGMA query_only = ON")
    con.execute("PRAGMA temp_store = MEMORY")
    return con


def run_sql(sql: str, max_rows: int = MAX_ROWS) -> QueryResult:

    started = time.perf_counter()
    deadline = started + QUERY_TIMEOUT_SEC
    try:
        con = _connect_readonly()
    except Exception as e:
        return QueryResult(ok=False, error=f"{type(e).__name__}: {e}")

    def _progress() -> int:
        return 1 if time.perf_counter() > deadline else 0

    try:
        con.set_progress_handler(_progress, 1000)
        cur = con.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]

        return QueryResult(
            ok=True, columns=columns, rows=rows, row_count=len(rows),
            truncated=truncated, elapsed_ms=int((time.perf_counter() - started) * 1000),
        )
    except Exception as e:
        return QueryResult(
            ok=False, error=f"{type(e).__name__}: {e}",
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )
    finally:
        try:
            con.set_progress_handler(None, 0)
            con.close()
        except Exception:
            pass


def render_preview(result: QueryResult, max_rows: int = 8) -> str:

    if not result.ok:
        return f"[执行失败] {result.error}"
    if not result.columns:
        return "[查询成功但无返回列]"
    head = " | ".join(result.columns)
    lines = [head, "-" * len(head)]
    for r in result.rows[:max_rows]:
        lines.append(" | ".join("" if v is None else str(v) for v in r))
    if result.row_count > max_rows:
        lines.append(f"... 共 {result.row_count} 行，已截断显示前 {max_rows} 行")
    return "\n".join(lines)
