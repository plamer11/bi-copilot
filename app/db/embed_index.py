
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from app.db.catalog import TABLES
from app.db.embedder import cosine

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = BACKEND_ROOT / "data" / "schema_embeddings.json"

TABLE_PREFIX = "table:"
COL_PREFIX = "col:"


def table_document(table: str) -> str:

    meta = TABLES.get(table)
    if not meta:
        return ""
    parts = [table, meta["desc"], " ".join(meta.get("aliases", []))]
    for cname, cm in meta["columns"].items():
        parts.append(f"{cname} {cm['desc']} {' '.join(cm.get('aliases', []))}")
    return " ".join(p for p in parts if p)


def column_document(table: str, column: str) -> str:

    meta = TABLES.get(table, {})
    cm = meta.get("columns", {}).get(column)
    if not cm:
        return ""
    return f"{table} {column} {cm['desc']} {' '.join(cm.get('aliases', []))}"


def build_documents() -> tuple[list[str], list[str]]:

    keys, docs = [], []
    for table, meta in TABLES.items():
        keys.append(f"{TABLE_PREFIX}{table}")
        docs.append(table_document(table))
        for cname in meta["columns"]:
            keys.append(f"{COL_PREFIX}{table}.{cname}")
            docs.append(column_document(table, cname))
    return keys, docs


def embedder_id(embedder) -> str:

    model = getattr(embedder, "model_name", "") or ""
    dim = getattr(embedder, "dim", 0) or 0
    return f"{type(embedder).__name__}|{model}|{dim}"


def _fingerprint(docs: list[str], backend: str = "") -> str:
    blob = "\n".join(docs) + "\n##backend##\n" + backend
    return hashlib.md5(blob.encode("utf-8")).hexdigest()[:16]


class SchemaEmbeddingIndex:


    def __init__(self, keys: list[str], docs: list[str], vectors: list[list[float]], fingerprint: str):
        self.keys = keys
        self.docs = docs
        self.vectors = vectors
        self.fingerprint = fingerprint


    @classmethod
    def load_or_build(cls, embedder) -> "SchemaEmbeddingIndex":
        keys, docs = build_documents()
        backend = embedder_id(embedder)
        fp = _fingerprint(docs, backend)

        cached = cls._read_cache()
        if (
            cached
            and cached.get("fingerprint") == fp
            and cached.get("backend") == backend
            and len(cached.get("vectors", [])) == len(docs)
        ):
            return cls(keys, docs, cached["vectors"], fp)

        logger.info("重建 schema 向量索引（%d 条，后端 %s）", len(docs), backend)
        vectors = embedder.embed(docs)
        cls._write_cache({
            "fingerprint": fp, "backend": backend, "keys": keys, "vectors": vectors,
        })
        return cls(keys, docs, vectors, fp)

    @staticmethod
    def _read_cache() -> dict | None:
        if not CACHE_PATH.exists():
            return None
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            logger.info("schema 向量缓存损坏，将重建: %s", e)
            return None

    @staticmethod
    def _write_cache(payload: dict) -> None:
        try:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            CACHE_PATH.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:

            logger.info("写入 schema 向量缓存失败（不影响本次）: %s", e)


    def query(self, text: str, embedder, top_k: int | None = None) -> list[tuple[str, float]]:

        if not self.vectors:
            return []
        qv = embedder.embed([text])[0]
        scored = [(k, cosine(qv, v)) for k, v in zip(self.keys, self.vectors)]
        scored.sort(key=lambda x: -x[1])
        return scored[:top_k] if top_k else scored

    def table_scores(self, text: str, embedder) -> dict[str, float]:
        pairs = self.query(text, embedder)
        out: dict[str, float] = {}
        for key, s in pairs:
            if key.startswith(TABLE_PREFIX):
                out[key[len(TABLE_PREFIX):]] = s
        return out

    def column_scores(self, table: str, text: str, embedder) -> dict[str, float]:
        pairs = self.query(text, embedder)
        prefix = f"{COL_PREFIX}{table}."
        return {k[len(prefix):]: s for k, s in pairs if k.startswith(prefix)}


def _normalize(scores: dict[str, float]) -> dict[str, float]:

    if not scores:
        return {}
    hi = max(scores.values())
    if hi <= 0:
        return {k: 0.0 for k in scores}
    return {k: (v / hi) for k, v in scores.items()}


def fuse(keyword: dict[str, float], semantic: dict[str, float], weight: float = 0.5) -> dict[str, float]:

    kw = _normalize(keyword)
    sem = _normalize(semantic)
    w = min(max(weight, 0.0), 1.0)
    keys = set(kw) | set(sem)
    return {k: round((1 - w) * kw.get(k, 0.0) + w * sem.get(k, 0.0), 4) for k in keys}
