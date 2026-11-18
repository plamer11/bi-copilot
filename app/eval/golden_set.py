
from __future__ import annotations


Q2_START, Q2_END = "2026-04-01", "2026-06-29"
MAY_START, MAY_END = "2026-05-01", "2026-05-31"
APR_START, APR_END = "2026-04-01", "2026-04-30"

GOLDEN: list[dict] = [

    {
        "id": 1, "difficulty": "easy", "tables": ["order_items", "orders"],
        "question": "4 月份一共卖了多少件？",
        "sql": f"""SELECT SUM(oi.quantity) AS units
FROM order_items oi JOIN orders o ON oi.order_id = o.order_id
WHERE o.order_date BETWEEN '{APR_START}' AND '{APR_END}'
  AND o.order_status <> 'cancelled'""",
    },
    {
        "id": 2, "difficulty": "easy", "tables": ["products"],
        "question": "现在有多少个 SKU 处于在售状态？",
        "sql": "SELECT COUNT(*) AS active_skus FROM products WHERE status = 'active'",
    },
    {
        "id": 3, "difficulty": "easy", "tables": ["orders"],
        "question": "各个站点的订单量分别是多少？",
        "sql": "SELECT marketplace, COUNT(*) AS order_cnt FROM orders GROUP BY marketplace ORDER BY order_cnt DESC",
    },
    {
        "id": 4, "difficulty": "easy", "tables": ["returns"],
        "question": "退货原因一共有哪几种，各出现了多少次？",
        "sql": "SELECT reason, COUNT(*) AS cnt FROM returns GROUP BY reason ORDER BY cnt DESC",
    },
    {
        "id": 5, "difficulty": "easy", "tables": ["inventory"],
        "question": "6 月 29 日这天全部 SKU 的可售库存加起来是多少件？",
        "sql": "SELECT SUM(available_units) AS total_available FROM inventory WHERE snapshot_date = '2026-06-29'",
    },
    {
        "id": 6, "difficulty": "easy", "tables": ["ad_spend"],
        "question": "整个季度广告一共花了多少钱？",
        "sql": "SELECT ROUND(SUM(spend_usd), 2) AS total_spend FROM ad_spend",
    },
    {
        "id": 7, "difficulty": "easy", "tables": ["returns"],
        "question": "一共有多少条退货记录？",
        "sql": "SELECT COUNT(*) AS return_cnt FROM returns",
    },
    {
        "id": 8, "difficulty": "easy", "tables": ["reviews"],
        "question": "差评（1 星和 2 星）一共有多少条？",
        "sql": "SELECT COUNT(*) AS bad_reviews FROM reviews WHERE rating <= 2",
    },
    {
        "id": 9, "difficulty": "easy", "tables": ["products"],
        "question": "Kitchen 品类下有多少个 SKU？",
        "sql": "SELECT COUNT(*) AS sku_cnt FROM products WHERE category = 'Kitchen'",
    },
    {
        "id": 10, "difficulty": "easy", "tables": ["products"],
        "question": "售价最高的商品定价是多少？",
        "sql": "SELECT MAX(price_usd) AS max_price FROM products",
    },
    {
        "id": 11, "difficulty": "easy", "tables": ["returns"],
        "question": "Q2 一共退了多少钱？",
        "sql": f"SELECT ROUND(SUM(refund_usd), 2) AS total_refund FROM returns "
               f"WHERE return_date BETWEEN '{Q2_START}' AND '{Q2_END}'",
    },
    {
        "id": 12, "difficulty": "easy", "tables": ["orders"],
        "question": "有多少订单是 Prime 订单？",
        "sql": "SELECT COUNT(*) AS prime_orders FROM orders WHERE is_prime = 1",
    },


    {
        "id": 13, "difficulty": "medium", "tables": ["order_items", "orders", "products"],
        "question": "4 月份 Kitchen 品类的销售额是多少？",
        "sql": f"""SELECT ROUND(SUM(oi.quantity * oi.item_price_usd), 2) AS gmv
FROM order_items oi
JOIN orders o ON oi.order_id = o.order_id
JOIN products p ON oi.sku = p.sku
WHERE o.order_date BETWEEN '{APR_START}' AND '{APR_END}'
  AND o.order_status <> 'cancelled' AND p.category = 'Kitchen'""",
    },
    {
        "id": 14, "difficulty": "medium", "tables": ["order_items", "orders"],
        "question": "上个月销量最高的 5 个 SKU 是哪些？",
        "sql": f"""SELECT oi.sku, SUM(oi.quantity) AS units
FROM order_items oi JOIN orders o ON oi.order_id = o.order_id
WHERE o.order_date BETWEEN '{MAY_START}' AND '{MAY_END}' AND o.order_status <> 'cancelled'
GROUP BY oi.sku ORDER BY units DESC LIMIT 5""",
    },
    {
        "id": 15, "difficulty": "medium", "tables": ["order_items", "orders", "products"],
        "question": "5 月份各品类的销量排名是怎样的？",
        "sql": f"""SELECT p.category, SUM(oi.quantity) AS units
FROM order_items oi
JOIN orders o ON oi.order_id = o.order_id
JOIN products p ON oi.sku = p.sku
WHERE o.order_date BETWEEN '{MAY_START}' AND '{MAY_END}' AND o.order_status <> 'cancelled'
GROUP BY p.category ORDER BY units DESC""",
    },
    {
        "id": 16, "difficulty": "medium", "tables": ["products"],
        "question": "Bedding 品类的平均星级是多少？",
        "sql": "SELECT ROUND(AVG(rating), 2) AS avg_rating FROM products WHERE category = 'Bedding'",
    },
    {
        "id": 17, "difficulty": "medium", "tables": ["ad_spend"],
        "question": "5 月份三种广告类型各自花了多少钱？",
        "sql": f"""SELECT campaign_type, ROUND(SUM(spend_usd), 2) AS spend
FROM ad_spend WHERE stat_date BETWEEN '{MAY_START}' AND '{MAY_END}'
GROUP BY campaign_type ORDER BY spend DESC""",
    },
    {
        "id": 18, "difficulty": "medium", "tables": ["returns", "products"],
        "question": "退款金额最高的 5 个 SKU 是哪些？",
        "sql": """SELECT r.sku, ROUND(SUM(r.refund_usd), 2) AS refund
FROM returns r JOIN products p ON r.sku = p.sku
GROUP BY r.sku ORDER BY refund DESC LIMIT 5""",
    },
    {
        "id": 19, "difficulty": "medium", "tables": ["order_items", "orders"],
        "question": "5 月份各个站点的销售额是多少？",
        "sql": f"""SELECT o.marketplace, ROUND(SUM(oi.quantity * oi.item_price_usd), 2) AS gmv
FROM order_items oi JOIN orders o ON oi.order_id = o.order_id
WHERE o.order_date BETWEEN '{MAY_START}' AND '{MAY_END}' AND o.order_status <> 'cancelled'
GROUP BY o.marketplace ORDER BY gmv DESC""",
    },
    {
        "id": 20, "difficulty": "medium", "tables": ["orders"],
        "question": "新客和老客的订单量分别是多少？",
        "sql": "SELECT customer_type, COUNT(*) AS order_cnt FROM orders GROUP BY customer_type ORDER BY order_cnt DESC",
    },
    {
        "id": 21, "difficulty": "medium", "tables": ["orders"],
        "question": "Q2 每个月的订单量分别是多少？",
        "sql": f"""SELECT SUBSTR(order_date, 1, 7) AS month, COUNT(*) AS order_cnt
FROM orders WHERE order_date BETWEEN '{Q2_START}' AND '{Q2_END}'
GROUP BY month ORDER BY month""",
    },
    {
        "id": 22, "difficulty": "medium", "tables": ["ad_spend", "products"],
        "question": "广告花费最高的 5 个 SKU 是哪些？",
        "sql": """SELECT a.sku, ROUND(SUM(a.spend_usd), 2) AS spend
FROM ad_spend a JOIN products p ON a.sku = p.sku
GROUP BY a.sku ORDER BY spend DESC LIMIT 5""",
    },
    {
        "id": 23, "difficulty": "medium", "tables": ["promotions", "products"],
        "question": "参加过秒杀（lightning_deal）的商品有多少个？",
        "sql": """SELECT COUNT(DISTINCT p.sku) AS sku_cnt
FROM promotions p JOIN products pr ON p.sku = pr.sku
WHERE p.promo_type = 'lightning_deal'""",
    },
    {
        "id": 24, "difficulty": "medium", "tables": ["order_items", "orders", "products"],
        "question": "5 月份 Bedding 品类的销量是多少件？",
        "sql": f"""SELECT SUM(oi.quantity) AS units
FROM order_items oi
JOIN orders o ON oi.order_id = o.order_id
JOIN products p ON oi.sku = p.sku
WHERE o.order_date BETWEEN '{MAY_START}' AND '{MAY_END}'
  AND o.order_status <> 'cancelled' AND p.category = 'Bedding'""",
    },
    {
        "id": 25, "difficulty": "medium", "tables": ["products"],
        "question": "各个品类的平均售价是多少？",
        "sql": "SELECT category, ROUND(AVG(price_usd), 2) AS avg_price FROM products GROUP BY category ORDER BY avg_price DESC",
    },
    {
        "id": 26, "difficulty": "medium", "tables": ["order_items", "orders", "products"],
        "question": "FBA 和自发货的销量各是多少？",
        "sql": f"""SELECT p.is_fba, SUM(oi.quantity) AS units
FROM order_items oi
JOIN orders o ON oi.order_id = o.order_id
JOIN products p ON oi.sku = p.sku
WHERE o.order_status <> 'cancelled'
GROUP BY p.is_fba""",
    },
    {
        "id": 27, "difficulty": "medium", "tables": ["reviews", "products"],
        "question": "评论数最多的 5 个 SKU 是哪些？",
        "sql": """SELECT r.sku, COUNT(*) AS review_cnt
FROM reviews r JOIN products p ON r.sku = p.sku
GROUP BY r.sku ORDER BY review_cnt DESC LIMIT 5""",
    },
    {
        "id": 28, "difficulty": "medium", "tables": ["ad_spend"],
        "question": "5 月份广告带来的销售额总共是多少？",
        "sql": f"""SELECT ROUND(SUM(ad_sales_usd), 2) AS ad_sales
FROM ad_spend WHERE stat_date BETWEEN '{MAY_START}' AND '{MAY_END}'""",
    },
    {
        "id": 29, "difficulty": "medium", "tables": ["returns", "products"],
        "question": "各个品类因为质量问题（defective）退货的有多少单？",
        "sql": """SELECT p.category, COUNT(*) AS defect_cnt
FROM returns r JOIN products p ON r.sku = p.sku
WHERE r.reason = 'defective'
GROUP BY p.category ORDER BY defect_cnt DESC""",
    },
    {
        "id": 30, "difficulty": "medium", "tables": ["inventory", "products"],
        "question": "6 月 29 日可售库存最少的 5 个 SKU 是哪些？",
        "sql": """SELECT i.sku, i.available_units
FROM inventory i JOIN products p ON i.sku = p.sku
WHERE i.snapshot_date = '2026-06-29'
ORDER BY i.available_units ASC LIMIT 5""",
    },


    {
        "id": 31, "difficulty": "hard", "tables": ["ad_spend"],
        "question": "哪些 SKU 的 ACOS 超过 50%，也就是广告费花得多但产出低？",
        "sql": """SELECT sku, ROUND(SUM(spend_usd) / SUM(ad_sales_usd) * 100, 1) AS acos_pct
FROM ad_spend GROUP BY sku
HAVING SUM(spend_usd) / SUM(ad_sales_usd) > 0.5
ORDER BY acos_pct DESC""",
    },
    {
        "id": 32, "difficulty": "hard", "tables": ["inventory", "products"],
        "question": "哪些商品快断货了，可售天数低于 15 天？",
        "sql": """SELECT i.sku, p.title, i.available_units, i.days_of_cover
FROM inventory i JOIN products p ON i.sku = p.sku
WHERE i.snapshot_date = '2026-06-29' AND i.days_of_cover < 15
ORDER BY i.days_of_cover ASC""",
    },
    {
        "id": 33, "difficulty": "hard", "tables": ["reviews", "products"],
        "question": "差评率最高的 5 个 SKU 是哪些？",
        "sql": """SELECT r.sku,
       ROUND(SUM(CASE WHEN r.rating <= 2 THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4) AS bad_rate
FROM reviews r JOIN products p ON r.sku = p.sku
GROUP BY r.sku HAVING COUNT(*) >= 10
ORDER BY bad_rate DESC LIMIT 5""",
    },
    {
        "id": 34, "difficulty": "hard", "tables": ["order_items", "orders", "products"],
        "question": "哪些 SKU 的销量高于所有 SKU 的平均销量？",
        "sql": f"""SELECT oi.sku, SUM(oi.quantity) AS units
FROM order_items oi JOIN orders o ON oi.order_id = o.order_id
WHERE o.order_status <> 'cancelled'
GROUP BY oi.sku
HAVING SUM(oi.quantity) > (
    SELECT AVG(sku_units) FROM (
        SELECT oi2.sku, SUM(oi2.quantity) AS sku_units
        FROM order_items oi2 JOIN orders o2 ON oi2.order_id = o2.order_id
        WHERE o2.order_status <> 'cancelled' GROUP BY oi2.sku
    )
)
ORDER BY units DESC""",
    },
    {
        "id": 35, "difficulty": "hard", "tables": ["order_items", "orders", "products"],
        "question": "各个品类的毛利率大概是多少？",
        "sql": f"""SELECT p.category,
       ROUND((SUM(oi.quantity * oi.item_price_usd) - SUM(oi.quantity * p.cost_usd))
             / SUM(oi.quantity * oi.item_price_usd), 4) AS margin_rate
FROM order_items oi
JOIN orders o ON oi.order_id = o.order_id
JOIN products p ON oi.sku = p.sku
WHERE o.order_status <> 'cancelled'
GROUP BY p.category ORDER BY margin_rate DESC""",
    },
    {
        "id": 36, "difficulty": "hard", "tables": ["order_items", "orders", "promotions"],
        "question": "做过促销的商品和没做过促销的商品，销量差多少？",
        "sql": f"""SELECT CASE WHEN pm.sku IS NOT NULL THEN '有促销' ELSE '无促销' END AS promo_flag,
       SUM(oi.quantity) AS units
FROM order_items oi
JOIN orders o ON oi.order_id = o.order_id
LEFT JOIN (SELECT DISTINCT sku FROM promotions) pm ON oi.sku = pm.sku
WHERE o.order_status <> 'cancelled'
GROUP BY promo_flag ORDER BY units DESC""",
    },
    {
        "id": 37, "difficulty": "hard", "tables": ["order_items", "returns", "orders"],
        "question": "退货率最高的 3 个 SKU 是哪些？",
        "sql": f"""SELECT oi.sku,
       ROUND(COUNT(r.return_id) * 1.0 / SUM(oi.quantity), 4) AS return_rate
FROM order_items oi
JOIN orders o ON oi.order_id = o.order_id
LEFT JOIN returns r ON r.order_id = oi.order_id AND r.sku = oi.sku
WHERE o.order_status <> 'cancelled'
GROUP BY oi.sku HAVING SUM(oi.quantity) >= 40
ORDER BY return_rate DESC LIMIT 3""",
    },
    {
        "id": 38, "difficulty": "hard", "tables": ["ad_spend", "products"],
        "question": "广告投产比 ROAS 最高的 5 个 SKU 是哪些？",
        "sql": """SELECT a.sku, ROUND(SUM(a.ad_sales_usd) / SUM(a.spend_usd), 2) AS roas
FROM ad_spend a JOIN products p ON a.sku = p.sku
GROUP BY a.sku HAVING SUM(a.spend_usd) > 0
ORDER BY roas DESC LIMIT 5""",
    },
    {
        "id": 39, "difficulty": "hard", "tables": ["orders"],
        "question": "Q2 每个月相比上个月的订单量增长了多少？",
        "sql": f"""WITH m AS (
    SELECT SUBSTR(order_date, 1, 7) AS month, COUNT(*) AS cnt
    FROM orders WHERE order_date BETWEEN '{Q2_START}' AND '{Q2_END}' GROUP BY month
)
SELECT month, cnt,
       cnt - LAG(cnt) OVER (ORDER BY month) AS mom_growth
FROM m ORDER BY month""",
    },
    {
        "id": 40, "difficulty": "hard", "tables": ["inventory", "ad_spend", "products"],
        "question": "哪些 SKU 既快断货了，还在继续投广告？",
        "sql": """SELECT DISTINCT i.sku, i.days_of_cover
FROM inventory i
JOIN ad_spend a ON i.sku = a.sku
JOIN products p ON i.sku = p.sku
WHERE i.snapshot_date = '2026-06-29' AND i.days_of_cover < 15
ORDER BY i.days_of_cover ASC""",
    },
]


def by_difficulty(level: str) -> list[dict]:
    return [g for g in GOLDEN if g["difficulty"] == level]


def summary() -> dict:
    out = {}
    for d in ("easy", "medium", "hard"):
        out[d] = len(by_difficulty(d))
    out["total"] = len(GOLDEN)
    return out
