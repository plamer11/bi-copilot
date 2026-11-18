
from __future__ import annotations

import pytest

from app.guard.sql_guard import inspect


def test_select_with_limit_passes():
    v = inspect("SELECT sku, SUM(quantity) AS s FROM order_items GROUP BY sku LIMIT 5")
    assert v.level == "SAFE"
    assert not v.blocked


def test_missing_limit_is_auto_injected():
    v = inspect("SELECT sku, SUM(quantity) AS s FROM order_items GROUP BY sku")
    assert v.level == "SAFE"
    assert "LIMIT 200" in v.sql
    assert "已自动补 LIMIT" in v.explain()


def test_oversized_limit_is_clamped():
    v = inspect("SELECT sku FROM products LIMIT 99999")
    assert "LIMIT 2000" in v.sql


@pytest.mark.parametrize("sql", [
    "DELETE FROM orders",
    "DROP TABLE products",
    "UPDATE products SET price_usd = 1",
    "INSERT INTO orders VALUES ('x')",
])
def test_write_statements_are_blocked(sql):
    v = inspect(sql)
    assert v.level == "BLOCKED"
    assert v.blocked


def test_multi_statement_is_blocked():
    v = inspect("SELECT 1; DROP TABLE products")
    assert v.blocked
    assert "多条语句" in v.explain()


def test_comment_bypass_attempt_is_blocked():

    v = inspect("SELECT 1 -- ; DROP TABLE products")
    assert v.blocked


def test_unknown_table_is_blocked():
    v = inspect("SELECT * FROM users")
    assert v.blocked
    assert "users" in v.explain()


def test_system_table_is_blocked():
    v = inspect("SELECT name FROM sqlite_master")
    assert v.blocked


def test_attach_database_is_blocked():
    v = inspect("ATTACH DATABASE 'other.db' AS o")
    assert v.blocked


def test_sensitive_table_full_scan_needs_approval():
    v = inspect("SELECT * FROM orders")
    assert v.needs_approval
    assert any("orders" in r for r in v.reasons)


def test_sensitive_table_with_filter_is_safe():
    v = inspect("SELECT order_id FROM orders WHERE order_date = '2026-05-01' LIMIT 10")
    assert v.level == "SAFE"


def test_aggregation_is_not_treated_as_full_scan():

    v = inspect("SELECT sku, SUM(quantity) AS s FROM order_items GROUP BY sku ORDER BY s DESC LIMIT 10")
    assert v.level == "SAFE"


def test_unparsable_sql_is_not_blocked_but_flagged():

    v = inspect("SELECT sku FROMM products")
    assert v.level == "UNPARSEABLE"
    assert not v.blocked


def test_cte_query_is_allowed():
    v = inspect("WITH t AS (SELECT sku FROM products) SELECT sku FROM t LIMIT 5")
    assert v.level == "SAFE"


def test_human_edited_sql_still_goes_through_guard():

    edited = "DELETE FROM orders WHERE order_date = '2026-05-01'"
    recheck = inspect(edited)
    assert recheck.blocked
