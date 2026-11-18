
from __future__ import annotations

import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from app.db.catalog import SENSITIVE_TABLES, TABLES

DEFAULT_LIMIT = 200
MAX_LIMIT = 2000
MAX_JOIN_TABLES = 4


ALLOWED_TYPES = (exp.Select,)


DANGEROUS_TOKENS = (
    "load_extension", "pragma", "attach", "detach", "sqlite_master",
    "sqlite_temp_master", "vacuum", "reindex", "writable_schema",
)


@dataclass
class GuardVerdict:
    level: str
    sql: str
    reasons: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.level == "BLOCKED"

    @property
    def needs_approval(self) -> bool:
        return self.level == "NEEDS_APPROVAL"

    def explain(self) -> str:
        return "；".join(self.reasons) if self.reasons else "通过安全检查"


def _extract_tables(node: exp.Expression) -> list[str]:

    cte_names = {c.alias.lower() for c in node.find_all(exp.CTE) if c.alias}
    seen, out = set(), []
    for t in node.find_all(exp.Table):
        name = t.name.lower()
        if name and name not in seen and name not in cte_names:
            seen.add(name)
            out.append(name)
    return out


def _has_where(node: exp.Expression) -> bool:
    return node.args.get("where") is not None


def _is_select_star(node: exp.Expression) -> bool:
    return any(isinstance(e, exp.Star) for e in (node.expressions or []))


def _is_aggregate(node: exp.Expression) -> bool:

    if node.args.get("group"):
        return True
    return next(node.find_all(exp.AggFunc), None) is not None


def inspect(sql: str) -> GuardVerdict:

    raw = (sql or "").strip().rstrip(";")
    if not raw:
        return GuardVerdict("BLOCKED", sql or "", ["空语句"])

    lowered = raw.lower()


    hit_tokens = [tok for tok in DANGEROUS_TOKENS if tok in lowered]
    if hit_tokens:
        return GuardVerdict("BLOCKED", raw, [f"包含高危关键字: {', '.join(hit_tokens)}"])


    if ";" in raw:
        return GuardVerdict("BLOCKED", raw, ["检测到多条语句，一次只允许执行一条 SELECT"])


    try:
        node = sqlglot.parse_one(raw, dialect="sqlite")
    except Exception as e:
        return GuardVerdict("UNPARSEABLE", raw, [f"SQL 无法解析: {type(e).__name__}: {e}"])

    if not isinstance(node, exp.Select) and not (

        isinstance(node, (exp.Union, exp.Subquery)) and node.find(exp.Select)
    ):
        kind = type(node).__name__
        return GuardVerdict("BLOCKED", raw, [f"只允许 SELECT 查询，检测到 {kind}"])


    tables = _extract_tables(node)
    unknown = [t for t in tables if t not in TABLES]
    if unknown:
        return GuardVerdict("BLOCKED", raw, [f"未知或不允许访问的表: {', '.join(unknown)}"])

    reasons: list[str] = []
    rewritten = raw


    limit_node = node.args.get("limit")
    if limit_node is None:
        node = node.limit(DEFAULT_LIMIT)
        rewritten = node.sql(dialect="sqlite")
        reasons.append(f"未指定 LIMIT，已自动补 LIMIT {DEFAULT_LIMIT}")
    else:
        try:
            n = int(limit_node.expression.this)
            if n > MAX_LIMIT:
                node.args["limit"] = exp.Limit(expression=exp.Literal.number(MAX_LIMIT))
                rewritten = node.sql(dialect="sqlite")
                reasons.append(f"LIMIT {n} 超过上限，已收敛到 {MAX_LIMIT}")
        except Exception:
            pass


    sensitive = [t for t in tables if t in SENSITIVE_TABLES]
    risky = []

    agg = _is_aggregate(node)
    if len(tables) > MAX_JOIN_TABLES:
        risky.append(f"一次关联 {len(tables)} 张表，超过 {MAX_JOIN_TABLES} 张")

    if sensitive and not _has_where(node) and not agg:
        risky.append(f"对敏感表（{', '.join(sensitive)}）做无过滤全量查询")
    if sensitive and _is_select_star(node):
        risky.append(f"对敏感表（{', '.join(sensitive)}）使用 SELECT *，可能暴露明细字段")
    if re.search(r"\bjoin\b", lowered) and not _has_where(node) and not agg:
        risky.append("多表关联但无 WHERE 过滤，结果集可能爆炸")

    if risky:
        return GuardVerdict("NEEDS_APPROVAL", rewritten, reasons + risky, tables)

    return GuardVerdict("SAFE", rewritten, reasons, tables)
