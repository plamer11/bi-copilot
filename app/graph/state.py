
from __future__ import annotations

from typing import Any, TypedDict


class Attempt(TypedDict):
    round: int
    sql: str
    error: str


class AgentState(TypedDict, total=False):

    session_id: str
    question: str


    history: list[dict]
    standalone_question: str
    is_followup: bool
    rewrite_reason: str


    decision: str
    clarify_question: str
    supervisor_reason: str


    recalled_tables: list[str]
    schema_text: str


    sql: str
    repair_round: int
    attempts: list[Attempt]


    guard_level: str
    guard_reasons: list[str]
    guard_sql: str


    needs_approval: bool
    approval_action: str
    edited_sql: str


    result_ok: bool
    result_columns: list[str]
    result_rows: list[Any]
    result_preview: str
    result_error: str
    row_count: int


    answer: str
    chart_type: str


    error: str
    trace: list[dict]
