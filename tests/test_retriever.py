
from __future__ import annotations

from app.db.catalog import METRICS, TABLES
from app.db.schema_retriever import build_context, schema_recall, score_columns, score_tables


def test_chinese_alias_hits_english_column():

    ctx = build_context("上个月广告花费最高的 SKU")
    assert "ad_spend" in ctx.tables
    assert "spend_usd" in ctx.columns["ad_spend"]


def test_metric_hit_forces_table_recall():

    ctx = build_context("哪些 SKU 的 ACOS 太高了")
    assert "ad_spend" in ctx.tables
    assert "ad_spend" in ctx.forced_tables


def test_implicit_dependency_table_is_recalled():

    ctx = build_context("上个月销量最高的 5 个 SKU")
    assert "order_items" in ctx.tables
    assert "orders" in ctx.tables


def test_join_key_columns_are_always_included():

    ctx = build_context("退货率最高的 SKU")
    assert "sku" in ctx.columns["returns"]
    assert "order_id" in ctx.columns["returns"]


def test_dimension_table_is_boosted():

    ctx = build_context("上个月退货率最高的 SKU")
    assert "products" in ctx.tables
    assert "title" in ctx.columns["products"]


def test_noise_table_is_filtered_out():

    ctx = build_context("上个月退货率最高的 3 个 SKU")
    assert "ad_spend" not in ctx.tables


def test_relative_threshold_keeps_second_relevant_table():

    ctx = build_context("Kitchen 品类 4 月销量")
    assert "order_items" in ctx.tables
    assert "products" in ctx.tables
    assert "category" in ctx.columns["products"]


def test_join_hint_for_returns_double_key():

    ctx = build_context("退货率最高的 SKU")
    hints = " ".join(ctx.join_hints)
    assert "returns.order_id = order_items.order_id" in hints
    assert "returns.sku = order_items.sku" in hints


def test_schema_recall_scores_fully_recovered_sql():
    gold = "SELECT SUM(oi.quantity) FROM order_items oi JOIN orders o ON oi.order_id = o.order_id"
    ctx = build_context("总销量是多少")
    assert schema_recall(gold, ctx) == 1.0


def test_schema_recall_penalizes_missing_column():
    gold = "SELECT SUM(spend_usd) FROM ad_spend"
    ctx = build_context("退货率最高的 SKU")
    assert schema_recall(gold, ctx) == 0.0


def test_context_render_contains_ddl_and_rules():
    ctx = build_context("上个月销量")
    text = ctx.render()
    assert "CREATE TABLE" in text
    assert "业务规则" in text


def test_every_metric_has_required_fields():
    for m in METRICS:
        assert m["name"] and m["expr"] and m["aliases"]

        for t in TABLES:
            if f"{t}." in m["expr"]:
                assert t in TABLES


def test_score_columns_returns_sorted():
    ranked = score_columns("ad_spend", "广告花费是多少")
    assert ranked[0][1] >= ranked[-1][1]


def test_all_tables_have_descriptions_and_aliases():
    for name, meta in TABLES.items():
        assert meta["desc"], f"{name} 缺少表描述"
        assert meta["aliases"], f"{name} 缺少别名"
        for cname, cm in meta["columns"].items():
            assert cm["type"], f"{name}.{cname} 缺类型"
            assert cm["aliases"], f"{name}.{cname} 缺别名"


def test_score_tables_covers_all_tables():
    ranked = score_tables("销量")
    assert len(ranked) == len(TABLES)
