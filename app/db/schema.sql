-- Amazon US 家居品类运营数据表（BI Copilot 演示库）
-- 数据窗口固定为 2026-04-01 ~ 2026-06-29，保证评测可复现
-- 表/列的业务含义与中文别名见 app/db/catalog.py（Schema 检索 Agent 使用）

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS returns;
DROP TABLE IF EXISTS reviews;
DROP TABLE IF EXISTS promotions;
DROP TABLE IF EXISTS ad_spend;
DROP TABLE IF EXISTS inventory;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;

-- SKU 主数据
CREATE TABLE products (
    sku           TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    category      TEXT NOT NULL,      -- Kitchen / Bedding / Bath / Storage / Decor / Lighting / Furniture / Outdoor
    sub_category  TEXT NOT NULL,
    brand         TEXT NOT NULL,
    launch_date   TEXT NOT NULL,      -- YYYY-MM-DD
    cost_usd      REAL NOT NULL,      -- 单件采购成本
    price_usd     REAL NOT NULL,      -- 挂牌价
    is_fba        INTEGER NOT NULL,   -- 1=走 FBA 配送
    weight_kg     REAL NOT NULL,
    rating        REAL,               -- 当前星级 1~5
    review_count  INTEGER DEFAULT 0,
    status        TEXT NOT NULL       -- active / paused / delisted
);

-- 订单头
CREATE TABLE orders (
    order_id      TEXT PRIMARY KEY,
    order_date    TEXT NOT NULL,      -- YYYY-MM-DD
    marketplace   TEXT NOT NULL,      -- US / CA / MX
    region        TEXT NOT NULL,      -- West / East / Central / South
    is_prime      INTEGER NOT NULL,
    order_status  TEXT NOT NULL,      -- shipped / delivered / cancelled / returned
    customer_type TEXT NOT NULL       -- new / returning
);

-- 订单明细
CREATE TABLE order_items (
    item_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        TEXT NOT NULL REFERENCES orders(order_id),
    sku             TEXT NOT NULL REFERENCES products(sku),
    quantity        INTEGER NOT NULL,
    item_price_usd  REAL NOT NULL,    -- 成交单价（已扣促销）
    discount_usd    REAL NOT NULL DEFAULT 0,
    shipping_fee_usd REAL NOT NULL DEFAULT 0
);

-- 广告投放日报（SP / SB / SD 三种广告）
CREATE TABLE ad_spend (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    stat_date     TEXT NOT NULL,      -- YYYY-MM-DD
    sku           TEXT NOT NULL REFERENCES products(sku),
    campaign_type TEXT NOT NULL,      -- SP=商品推广 / SB=品牌推广 / SD=展示型推广
    impressions   INTEGER NOT NULL,
    clicks        INTEGER NOT NULL,
    spend_usd     REAL NOT NULL,
    ad_sales_usd  REAL NOT NULL       -- 广告归因销售额
);

-- 退货记录
CREATE TABLE returns (
    return_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id      TEXT NOT NULL REFERENCES orders(order_id),
    sku           TEXT NOT NULL REFERENCES products(sku),
    return_date   TEXT NOT NULL,
    reason        TEXT NOT NULL,      -- damaged / not_as_described / no_longer_needed / wrong_item / defective / arrived_late
    refund_usd    REAL NOT NULL,
    is_defective  INTEGER NOT NULL,
    is_resellable INTEGER NOT NULL    -- 1=可二次销售
);

-- 库存快照（每日）
CREATE TABLE inventory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date   TEXT NOT NULL,
    sku             TEXT NOT NULL REFERENCES products(sku),
    available_units INTEGER NOT NULL, -- 可售库存
    inbound_units   INTEGER NOT NULL, -- 在途
    reserved_units  INTEGER NOT NULL, -- 被订单占用
    days_of_cover   REAL NOT NULL     -- 可售天数 = available / 日均销量
);

-- 评论
CREATE TABLE reviews (
    review_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    sku            TEXT NOT NULL REFERENCES products(sku),
    review_date    TEXT NOT NULL,
    rating         INTEGER NOT NULL,  -- 1~5
    is_verified    INTEGER NOT NULL,
    has_image      INTEGER NOT NULL,
    helpful_votes  INTEGER NOT NULL DEFAULT 0,
    title          TEXT
);

-- 促销活动
CREATE TABLE promotions (
    promo_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    sku             TEXT NOT NULL REFERENCES products(sku),
    promo_type      TEXT NOT NULL,    -- coupon / lightning_deal / subscribe_save / prime_exclusive
    start_date      TEXT NOT NULL,
    end_date        TEXT NOT NULL,
    discount_pct    REAL NOT NULL,    -- 0~1
    promo_price_usd REAL NOT NULL
);

CREATE INDEX idx_orders_date       ON orders(order_date);
CREATE INDEX idx_items_order       ON order_items(order_id);
CREATE INDEX idx_items_sku         ON order_items(sku);
CREATE INDEX idx_ad_date           ON ad_spend(stat_date);
CREATE INDEX idx_ad_sku            ON ad_spend(sku);
CREATE INDEX idx_returns_date      ON returns(return_date);
CREATE INDEX idx_returns_sku       ON returns(sku);
CREATE INDEX idx_inv_date          ON inventory(snapshot_date);
CREATE INDEX idx_reviews_sku       ON reviews(sku);
CREATE INDEX idx_promos_sku        ON promotions(sku);
