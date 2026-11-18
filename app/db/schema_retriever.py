
from __future__ import annotations

import re
from dataclasses import dataclass, field

try:
    import jieba
except ImportError:
    jieba = None

from app.config import settings
from app.db.embed_index import SchemaEmbeddingIndex, fuse
from app.db.catalog import (
    DIMENSION_BOOST,
    DISPLAY_COLUMNS,
    JOINS,
    KEY_COLUMNS,
    METRICS,
    RELATIVE_THRESHOLD,
    SERVICE_RULES,
    TABLES,
    table_ddl,
)


def _always_columns(table: str) -> list[str]:

    return list(dict.fromkeys(KEY_COLUMNS.get(table, []) + DISPLAY_COLUMNS.get(table, [])))

_TABLE_RE = re.compile(r"\b(products|orders|order_items|ad_spend|returns|inventory|reviews|promotions)\b")


EMBED_MIN_TABLE_SCORE = 0.15
EMBED_MIN_COL_SIM = 0.45


@dataclass
class SchemaContext:


    query: str
    tables: list[str] = field(default_factory=list)
    columns: dict[str, list[str]] = field(default_factory=dict)
    metrics: list[dict] = field(default_factory=list)
    join_hints: list[str] = field(default_factory=list)
    forced_tables: list[str] = field(default_factory=list)

    @property
    def ddl(self) -> str:
        return "\n\n".join(table_ddl(t, self.columns.get(t)) for t in self.tables)

    def render(self) -> str:
        parts = ["## 相关表结构（已按问题筛选）", self.ddl]
        if self.join_hints:
            parts.append("## 可用的 JOIN 条件\n" + "\n".join(f"- {h}" for h in self.join_hints))
        if self.metrics:
            parts.append("## 指标口径（必须按此计算）\n" + "\n".join(
                f"- {m['name']} = {m['expr']}\n  说明：{m['note']}" for m in self.metrics))
        parts.append("## 业务规则\n" + "\n".join(f"- {r}" for r in SERVICE_RULES))
        return "\n\n".join(parts)


def tokenize(text: str) -> set[str]:

    text = (text or "").lower().strip()
    if not text:
        return set()
    toks = {text}
    toks |= set(re.findall(r"[a-z_][a-z0-9_]*", text))
    if jieba is not None:
        toks |= {w for w in jieba.cut(text) if len(w.strip()) > 1}
    else:
        cn = re.findall(r"[\u4e00-\u9fff]+", text)
        for seg in cn:
            toks |= {seg[i:i + 2] for i in range(len(seg) - 1)}
    return {t for t in toks if len(t) >= 2}


def _hit_score(tokens: set[str], target: str) -> float:

    if not target:
        return 0.0
    t = target.lower()
    score = 0.0
    for tok in tokens:
        if tok in t:
            score += len(tok) * 0.6
    return score


def _forced_tables_by_metrics(tokens: set[str], query: str = "") -> tuple[list[str], list[dict]]:

    forced, hit_metrics = [], []
    for m in METRICS:
        blob = " ".join([m["name"], m["expr"], *m["aliases"]])
        hit = _hit_score(tokens, blob) > 0 or any(a in query for a in m["aliases"])
        if hit:
            hit_metrics.append(m)

            for t in _TABLE_RE.findall(m["expr"]) + list(m.get("requires", [])):
                if t not in forced:
                    forced.append(t)
    return forced, hit_metrics


def _keyword_table_scores(query: str) -> dict[str, float]:

    tokens = tokenize(query)
    out = {}
    for name, meta in TABLES.items():
        s = _hit_score(tokens, f"{name} {meta['desc']} {' '.join(meta['aliases'])}")
        col_score = 0.0
        for cname, cm in meta["columns"].items():
            col_score += _hit_score(tokens, f"{cname} {cm['desc']} {' '.join(cm['aliases'])}")
        out[name] = s + col_score * 0.8 + DIMENSION_BOOST.get(name, 0.0)
    return out


def score_tables(query: str, embedder=None, weight: float | None = None) -> list[tuple[str, float]]:

    tokens = tokenize(query)
    forced, _ = _forced_tables_by_metrics(tokens, query)
    kw = _keyword_table_scores(query)

    if embedder is not None:
        idx = SchemaEmbeddingIndex.load_or_build(embedder)
        base = fuse(kw, idx.table_scores(query, embedder), _weight(weight))
    else:
        base = kw

    out = []
    for name, s in base.items():
        total = s + 100.0 if name in forced else s
        out.append((name, round(total, 4)))
    return sorted(out, key=lambda x: -x[1])


def _weight(weight: float | None) -> float:
    return settings.embedding_weight if weight is None else weight


def score_columns(table: str, query: str, embedder=None) -> list[tuple[str, float]]:

    tokens = tokenize(query)
    meta = TABLES.get(table)
    if not meta:
        return []

    kw = {c: _hit_score(tokens, f"{c} {cm['desc']} {' '.join(cm['aliases'])}")
          for c, cm in meta["columns"].items()}

    if embedder is not None:
        idx = SchemaEmbeddingIndex.load_or_build(embedder)
        sem = idx.column_scores(table, query, embedder)
        candidates = {c for c, v in kw.items() if v > 0}
        candidates |= {c for c, v in sem.items() if v >= EMBED_MIN_COL_SIM}
        merged = fuse({c: kw.get(c, 0.0) for c in candidates},
                      {c: sem.get(c, 0.0) for c in candidates}, _weight(None))
    else:
        merged = {c: v for c, v in kw.items() if v > 0}

    return sorted(merged.items(), key=lambda x: -x[1])


def build_context(query: str, top_k: int = 4, top_n_cols: int = 8, embedder=None) -> SchemaContext:

    tokens = tokenize(query)
    forced, metrics = _forced_tables_by_metrics(tokens, query)

    ranked = score_tables(query, embedder=embedder)


    top_score = ranked[0][1] if ranked else 0.0
    if embedder is not None:
        threshold = max(top_score * RELATIVE_THRESHOLD, EMBED_MIN_TABLE_SCORE)
    else:
        threshold = max(top_score * RELATIVE_THRESHOLD, 1.0)
    tables = [t for t, s in ranked if s >= threshold][:top_k]
    for t in forced:
        if t not in tables:
            tables.append(t)
    if not tables:
        tables = [ranked[0][0]] if ranked else []

    ctx = SchemaContext(query=query, tables=tables, metrics=metrics, forced_tables=forced)

    for t in tables:
        cols = [c for c, s in score_columns(t, query, embedder=embedder)][:top_n_cols]
        for k in _always_columns(t):
            if k not in cols:
                cols.append(k)
        if not cols:
            cols = list(TABLES[t]["columns"])[:top_n_cols]
        ctx.columns[t] = cols

    s = set(tables)
    ctx.join_hints = [j["on"] for j in JOINS if j["from"] in s and j["to"] in s]
    return ctx


def schema_recall(gold_sql: str, ctx: SchemaContext) -> float:

    used = set()
    sql = gold_sql.lower()
    for t, c in re.findall(r"\b([a-z_]+)\.([a-z_]+)", sql):
        if t in TABLES and c in TABLES[t]["columns"]:
            used.add((t, c))


    for c in re.findall(r"\b([a-z_][a-z0-9_]*)\b", sql):
        owners = [t for t in TABLES if c in TABLES[t]["columns"]]
        if len(owners) == 1:
            used.add((owners[0], c))
    if not used:
        return 1.0
    recalled = {(t, c) for (t, c) in used if c in ctx.columns.get(t, [])}
    return round(len(recalled) / len(used), 4)
