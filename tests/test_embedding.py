
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import settings
from app.db.embed_index import (
    SchemaEmbeddingIndex,
    build_documents,
    column_document,
    embedder_id,
    fuse,
    table_document,
)
from app.db.embedder import (
    HashEmbedder,
    cosine,
    get_embedder,
    reset_embedder_cache,
    resolve_embedder,
)
from app.db.schema_retriever import build_context, score_columns, score_tables


_TEST_CACHE = Path(__file__).resolve().parents[1] / "data" / "test_schema_embeddings.json"


@pytest.fixture
def test_cache(monkeypatch):

    monkeypatch.setattr("app.db.embed_index.CACHE_PATH", _TEST_CACHE)
    return _TEST_CACHE


def test_hash_embedder_is_deterministic_and_normalized():
    emb = HashEmbedder()
    a = emb.embed(["退货率最高的品类"])
    b = emb.embed(["退货率最高的品类"])
    assert a == b, "同一文本两次向量化必须一致，否则缓存毫无意义"
    norm = sum(x * x for x in a[0])
    assert abs(norm - 1.0) < 1e-6, "向量要 L2 归一化，余弦相似度才等价于点积"


def test_cosine_basics():
    assert abs(cosine([1, 0], [1, 0]) - 1.0) < 1e-9
    assert abs(cosine([1, 0], [0, 1])) < 1e-9
    assert cosine([1, 0], []) == 0.0
    assert cosine([1, 0], [1, 0, 0]) == 0.0


def test_hash_embedder_captures_char_overlap():
    emb = HashEmbedder()
    v_refund = emb.embed(["退款金额"])[0]
    v_return = emb.embed(["退货金额"])[0]
    v_ad = emb.embed(["广告花费"])[0]
    assert cosine(v_refund, v_return) > cosine(v_refund, v_ad)


def test_build_documents_covers_tables_and_columns():
    from app.db.catalog import TABLES

    keys, docs = build_documents()
    n_cols = sum(len(m["columns"]) for m in TABLES.values())
    assert len(keys) == len(TABLES) + n_cols
    assert all(d.strip() for d in docs), "空文档会让向量变成零向量，检索时永远排在最后"


def test_documents_include_desc_and_aliases():
    assert "退货" in table_document("returns")
    assert "广告" in table_document("ad_spend")
    doc = column_document("ad_spend", "spend_usd")
    assert "spend_usd" in doc and doc.strip()


def test_index_cache_is_reused_across_calls(tmp_path, monkeypatch):

    calls = []
    emb = HashEmbedder()
    original = emb.embed

    def _count(texts):
        calls.append(len(texts))
        return original(texts)

    emb.embed = _count
    monkeypatch.setattr(
        "app.db.embed_index.CACHE_PATH", tmp_path / "schema_embeddings.json"
    )

    idx1 = SchemaEmbeddingIndex.load_or_build(emb)
    idx2 = SchemaEmbeddingIndex.load_or_build(emb)
    assert len(calls) == 1, "有缓存就不该重复向量化"
    assert idx1.vectors == idx2.vectors


def test_index_cache_invalidated_when_backend_changes(tmp_path, monkeypatch):

    monkeypatch.setattr(
        "app.db.embed_index.CACHE_PATH", tmp_path / "schema_embeddings.json"
    )
    SchemaEmbeddingIndex.load_or_build(HashEmbedder())

    class OtherEmbedder(HashEmbedder):
        dim = 128

    calls = []
    other = OtherEmbedder()
    original = other.embed
    other.embed = lambda texts: (calls.append(1), original(texts))[1]

    SchemaEmbeddingIndex.load_or_build(other)
    assert calls, "后端变了就必须重建索引"


def test_cache_file_content_has_backend_tag(tmp_path, monkeypatch):
    path = tmp_path / "schema_embeddings.json"
    monkeypatch.setattr("app.db.embed_index.CACHE_PATH", path)
    SchemaEmbeddingIndex.load_or_build(HashEmbedder())
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["backend"] == embedder_id(HashEmbedder())
    assert len(payload["vectors"]) == len(payload["keys"])


def test_fuse_normalizes_each_channel_before_weighting():

    out = fuse({"a": 20.0, "b": 1.0}, {"a": 0.1, "b": 0.9}, weight=0.5)
    assert out["a"] == pytest.approx(0.5 + 0.5 * (0.1 / 0.9), abs=1e-3)
    assert out["b"] == pytest.approx(0.5 * (1.0 / 20.0) + 0.5, abs=1e-3)


def test_fuse_weight_zero_is_keyword_only():
    assert fuse({"a": 5.0, "b": 1.0}, {"a": 0.1, "b": 0.9}, weight=0.0)["a"] == 1.0
    assert fuse({"a": 5.0, "b": 1.0}, {"a": 0.1, "b": 0.9}, weight=0.0)["b"] == pytest.approx(0.2)


def test_fuse_handles_empty_and_negative():
    assert fuse({}, {}, weight=0.5) == {}
    assert fuse({"a": 0.0}, {"a": 0.0}, weight=0.5)["a"] == 0.0


def test_get_embedder_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "use_embedding_retrieval", False)
    reset_embedder_cache()
    assert get_embedder() is None
    assert resolve_embedder() is None


def test_resolve_embedder_probes_only_once(monkeypatch):
    monkeypatch.setattr(settings, "use_embedding_retrieval", True)
    monkeypatch.setattr(settings, "embedding_provider", "hash")
    reset_embedder_cache()
    first = resolve_embedder()
    assert isinstance(first, HashEmbedder)

    assert resolve_embedder() is first
    reset_embedder_cache()


def test_unavailable_backend_degrades_to_none(monkeypatch):

    monkeypatch.setattr(settings, "use_embedding_retrieval", True)
    monkeypatch.setattr(settings, "embedding_provider", "local")
    reset_embedder_cache()

    def _boom(*a, **k):
        raise RuntimeError("sentence-transformers 没装")

    import builtins
    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name.startswith("sentence_transformers"):
            raise ImportError("no module")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    try:
        assert get_embedder() is None
    finally:
        monkeypatch.setattr(builtins, "__import__", real_import)
        reset_embedder_cache()


class TopicEmbedder:


    dim = 4
    model_name = "stub-topic"

    def __init__(self):
        self.rules = [
            (("退货", "退款", "退回", "退单"), [1.0, 0, 0, 0]),
            (("广告", "acos", "投放", "花费"), [0, 1.0, 0, 0]),
            (("库存", "断货", "可售"), [0, 0, 1.0, 0]),
        ]

    def embed(self, texts):
        out = []
        for t in texts:
            low = (t or "").lower()
            vec = [0.0, 0.0, 0.0, 1.0]
            for keywords, v in self.rules:
                if any(k in low for k in keywords):
                    vec = list(v)
                    break
            out.append(vec)
        return out


def test_semantic_channel_can_rescue_table_without_keyword_hit(test_cache):

    emb = TopicEmbedder()

    assert dict(score_tables("退单情况怎么样"))["returns"] == 0.0
    ranked = dict(score_tables("退单情况怎么样", embedder=emb))
    assert ranked.get("returns", 0) > 0, "语义通道应当把 returns 捞上来"


def test_forced_metric_tables_survive_with_embedding(test_cache):

    ctx = build_context("各品类的 ACOS 是多少", embedder=TopicEmbedder())
    assert "ad_spend" in ctx.tables, "ACOS 必须召回 ad_spend，否则后面怎么写都是错"
    assert "order_items" in ctx.tables


def test_build_context_without_embedder_is_unchanged():

    a = build_context("上个月销量最高的 5 个 SKU")
    b = build_context("上个月销量最高的 5 个 SKU", embedder=None)
    assert a.tables == b.tables
    assert a.columns == b.columns


def test_score_columns_respects_semantic_threshold(test_cache):

    cols = dict(score_columns("returns", "广告投放花了多少钱", embedder=TopicEmbedder()))

    assert len(cols) <= 3
