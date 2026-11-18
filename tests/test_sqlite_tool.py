
from __future__ import annotations

from app.tools.sqlite_tool import MAX_ROWS, render_preview, run_sql


def test_select_works():
    res = run_sql("SELECT sku FROM products LIMIT 3")
    assert res.ok
    assert res.row_count == 3
    assert res.columns == ["sku"]


def test_write_is_rejected_by_readonly_connection():

    res = run_sql("UPDATE products SET price_usd = 1")
    assert not res.ok
    assert "readonly" in res.error.lower()


def test_drop_is_rejected():
    res = run_sql("DROP TABLE products")
    assert not res.ok


def test_error_message_is_preserved_for_self_healing():

    res = run_sql("SELECT no_such_col FROM products")
    assert not res.ok
    assert "no such column" in res.error
    assert "no_such_col" in res.error


def test_result_is_truncated():
    res = run_sql("SELECT sku FROM products", max_rows=5)
    assert res.ok
    assert res.row_count == 5
    assert res.truncated is True


def test_default_max_rows_is_respected():
    res = run_sql("SELECT sku FROM products")
    assert res.row_count <= MAX_ROWS


def test_render_preview_shows_columns_and_rows():
    res = run_sql("SELECT sku, price_usd FROM products LIMIT 2")
    text = render_preview(res)
    assert "sku" in text
    assert "price_usd" in text


def test_render_preview_shows_error():
    res = run_sql("SELECT bad FROM products")
    text = render_preview(res)
    assert "执行失败" in text


def test_aggregate_query_runs_fast():
    res = run_sql("SELECT COUNT(*) FROM order_items")
    assert res.ok
    assert res.row_count == 1
    assert res.elapsed_ms < 3000
