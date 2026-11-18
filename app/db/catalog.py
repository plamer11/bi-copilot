
from __future__ import annotations


TABLES: dict[str, dict] = {
    "products": {
        "desc": "SKU 主数据：商品标题、品类、品牌、成本、售价、上架日期、是否 FBA、评分、在售状态",
        "aliases": ["商品", "产品", "SKU", "品类", "品牌", "成本", "售价", "定价", "链接", "在售", "评分", "星级", "重量"],
        "columns": {
            "sku": {"type": "TEXT", "desc": "商品唯一编码，如 HN-BED-1001", "aliases": ["SKU", "编码", "货号", "商品编号"]},
            "title": {"type": "TEXT", "desc": "商品标题", "aliases": ["标题", "品名", "名称"]},
            "category": {"type": "TEXT", "desc": "一级品类：Kitchen/Bedding/Bath/Storage/Decor/Lighting/Furniture/Outdoor", "aliases": ["品类", "类目", "一级类目", "大类"]},
            "sub_category": {"type": "TEXT", "desc": "二级品类，如 Sheet Set、Floor Lamp", "aliases": ["二级品类", "子类目", "细分类目"]},
            "brand": {"type": "TEXT", "desc": "品牌名", "aliases": ["品牌"]},
            "launch_date": {"type": "TEXT", "desc": "上架日期 YYYY-MM-DD", "aliases": ["上架日期", "上新时间", "上市"]},
            "cost_usd": {"type": "REAL", "desc": "单件采购成本（美元）", "aliases": ["成本", "采购价", "进货价"]},
            "price_usd": {"type": "REAL", "desc": "挂牌售价（美元）", "aliases": ["售价", "价格", "定价", "客单价", "卖价"]},
            "is_fba": {"type": "INTEGER", "desc": "是否走 FBA 配送，1=是", "aliases": ["FBA", "配送方式", "是否FBA"]},
            "weight_kg": {"type": "REAL", "desc": "单件重量（公斤）", "aliases": ["重量", "克重", "体积重量"]},
            "rating": {"type": "REAL", "desc": "当前星级评分 1~5，来自 reviews 聚合", "aliases": ["评分", "星级", "星评", "分数"]},
            "review_count": {"type": "INTEGER", "desc": "累计评论数", "aliases": ["评论数", "评价数", "review数"]},
            "status": {"type": "TEXT", "desc": "在售状态：active/paused/delisted", "aliases": ["状态", "在售", "是否下架", "停售"]},
        },
    },
    "orders": {
        "desc": "订单头：订单号、下单日期、站点、区域、是否 Prime、订单状态、新老客",
        "aliases": ["订单", "单量", "订单量", "下单", "站点", "区域", "Prime", "新老客", "订单状态"],
        "columns": {
            "order_id": {"type": "TEXT", "desc": "订单号", "aliases": ["订单号", "订单ID"]},
            "order_date": {"type": "TEXT", "desc": "下单日期 YYYY-MM-DD", "aliases": ["下单日期", "订单日期", "时间", "日期"]},
            "marketplace": {"type": "TEXT", "desc": "站点：US/CA/MX", "aliases": ["站点", "国家", "市场", "站点代码"]},
            "region": {"type": "TEXT", "desc": "美国区域：West/East/Central/South", "aliases": ["区域", "地区", "州区域"]},
            "is_prime": {"type": "INTEGER", "desc": "是否 Prime 订单，1=是", "aliases": ["Prime", "会员", "Prime订单"]},
            "order_status": {"type": "TEXT", "desc": "shipped/delivered/cancelled/returned", "aliases": ["订单状态", "是否取消", "配送状态"]},
            "customer_type": {"type": "TEXT", "desc": "new=新客 / returning=老客", "aliases": ["新老客", "客户类型", "新客", "复购"]},
        },
    },
    "order_items": {
        "desc": "订单明细：一单一行，含 SKU、件数、成交单价、折扣、运费。算销量和销售额都从这里出",
        "aliases": ["销量", "件数", "销售额", "GMV", "营收", "成交", "折扣", "明细", "出单"],
        "columns": {
            "item_id": {"type": "INTEGER", "desc": "明细行主键", "aliases": ["明细ID"]},
            "order_id": {"type": "TEXT", "desc": "所属订单号，关联 orders.order_id", "aliases": ["订单号", "订单ID"]},
            "sku": {"type": "TEXT", "desc": "商品编码，关联 products.sku", "aliases": ["SKU", "商品"]},
            "quantity": {"type": "INTEGER", "desc": "购买件数", "aliases": ["件数", "销量", "数量", "销售数量", "卖了多少"]},
            "item_price_usd": {"type": "REAL", "desc": "成交单价（已扣促销）", "aliases": ["成交价", "单价", "售价"]},
            "discount_usd": {"type": "REAL", "desc": "该行折扣金额", "aliases": ["折扣", "优惠", "让利"]},
            "shipping_fee_usd": {"type": "REAL", "desc": "该行运费", "aliases": ["运费", "配送费"]},
        },
    },
    "ad_spend": {
        "desc": "广告投放日报：按天 × SKU × 广告类型记录曝光、点击、花费、广告归因销售额。算 ACOS/ROAS/CTR 用这张表",
        "aliases": ["广告", "广告费", "投放", "花费", "曝光", "点击", "ACOS", "ROAS", "CTR", "广告销售", "CPC", "推广"],
        "columns": {
            "id": {"type": "INTEGER", "desc": "主键", "aliases": ["ID"]},
            "stat_date": {"type": "TEXT", "desc": "投放日期 YYYY-MM-DD", "aliases": ["投放日期", "广告日期", "日期"]},
            "sku": {"type": "TEXT", "desc": "商品编码，关联 products.sku", "aliases": ["SKU", "商品"]},
            "campaign_type": {"type": "TEXT", "desc": "广告类型：SP=商品推广 / SB=品牌推广 / SD=展示型推广", "aliases": ["广告类型", "广告形式", "SP", "SB", "SD", "campaign"]},
            "impressions": {"type": "INTEGER", "desc": "曝光量", "aliases": ["曝光", "曝光量", "展示量", "impression"]},
            "clicks": {"type": "INTEGER", "desc": "点击量", "aliases": ["点击", "点击量", "click"]},
            "spend_usd": {"type": "REAL", "desc": "广告花费（美元）", "aliases": ["广告花费", "广告费", "花费", "spend", "投放金额", "烧了多少"]},
            "ad_sales_usd": {"type": "REAL", "desc": "广告归因销售额（美元）", "aliases": ["广告销售额", "广告产出", "广告带来的销售额"]},
        },
    },
    "returns": {
        "desc": "退货记录：退货原因、退款金额、是否缺陷品、是否可二次销售。算退货率/退款额用这张表",
        "aliases": ["退货", "退款", "退货率", "退货原因", "差评", "缺陷", "残次", "退货金额"],
        "columns": {
            "return_id": {"type": "INTEGER", "desc": "退货记录主键", "aliases": ["退货ID"]},
            "order_id": {"type": "TEXT", "desc": "关联 orders.order_id", "aliases": ["订单号"]},
            "sku": {"type": "TEXT", "desc": "商品编码，关联 products.sku", "aliases": ["SKU", "商品"]},
            "return_date": {"type": "TEXT", "desc": "退货日期 YYYY-MM-DD", "aliases": ["退货日期", "退款日期", "日期"]},
            "reason": {"type": "TEXT", "desc": "退货原因：damaged/not_as_described/no_longer_needed/wrong_item/defective/arrived_late", "aliases": ["退货原因", "原因", "为什么退", "退货理由"]},
            "refund_usd": {"type": "REAL", "desc": "退款金额（美元）", "aliases": ["退款", "退款金额", "退了多少钱"]},
            "is_defective": {"type": "INTEGER", "desc": "是否缺陷/损坏，1=是", "aliases": ["缺陷", "损坏", "质量问题", "残次品"]},
            "is_resellable": {"type": "INTEGER", "desc": "是否可二次销售，1=是", "aliases": ["可二次销售", "能否再卖", "可再售"]},
        },
    },
    "inventory": {
        "desc": "库存日报快照：可售库存、在途、占用、可售天数。判断断货风险用这张表",
        "aliases": ["库存", "存货", "在途", "可售", "断货", "备货", "可售天数", "压货"],
        "columns": {
            "id": {"type": "INTEGER", "desc": "主键", "aliases": ["ID"]},
            "snapshot_date": {"type": "TEXT", "desc": "快照日期 YYYY-MM-DD", "aliases": ["库存日期", "快照日期", "日期"]},
            "sku": {"type": "TEXT", "desc": "商品编码，关联 products.sku", "aliases": ["SKU", "商品"]},
            "available_units": {"type": "INTEGER", "desc": "可售库存件数", "aliases": ["可售库存", "库存量", "可用库存", "还有多少货"]},
            "inbound_units": {"type": "INTEGER", "desc": "在途库存件数", "aliases": ["在途", "在途库存", "路上"]},
            "reserved_units": {"type": "INTEGER", "desc": "已被订单占用件数", "aliases": ["占用", "预留", "锁定库存"]},
            "days_of_cover": {"type": "REAL", "desc": "可售天数 = 可售库存 / 日均销量，越小越容易断货", "aliases": ["可售天数", "覆盖天数", "还能卖几天", "断货风险"]},
        },
    },
    "reviews": {
        "desc": "评论明细：评分、是否 VP、是否带图、点赞数。算差评率/口碑趋势用这张表",
        "aliases": ["评论", "评价", "review", "差评", "好评", "星级", "口碑", "带图"],
        "columns": {
            "review_id": {"type": "INTEGER", "desc": "主键", "aliases": ["评论ID"]},
            "sku": {"type": "TEXT", "desc": "商品编码，关联 products.sku", "aliases": ["SKU", "商品"]},
            "review_date": {"type": "TEXT", "desc": "评论日期 YYYY-MM-DD", "aliases": ["评论日期", "评价时间", "日期"]},
            "rating": {"type": "INTEGER", "desc": "评分 1~5，1~2 星视为差评", "aliases": ["评分", "星级", "星数", "分数"]},
            "is_verified": {"type": "INTEGER", "desc": "是否真实购买（VP）评论，1=是", "aliases": ["VP", "是否VP", "真实购买", "认证评论"]},
            "has_image": {"type": "INTEGER", "desc": "是否带图，1=是", "aliases": ["带图", "图片评论", "是否有图"]},
            "helpful_votes": {"type": "INTEGER", "desc": "点赞数", "aliases": ["点赞", "点赞数", "有用数"]},
            "title": {"type": "TEXT", "desc": "评论标题", "aliases": ["评论标题", "标题"]},
        },
    },
    "promotions": {
        "desc": "促销活动：券/秒杀/订阅省/Prime专享，含折扣力度与生效区间。看促销对销量的拉动用这张表",
        "aliases": ["促销", "活动", "优惠券", "coupon", "秒杀", "deal", "折扣", "降价", "订阅省"],
        "columns": {
            "promo_id": {"type": "INTEGER", "desc": "主键", "aliases": ["活动ID"]},
            "sku": {"type": "TEXT", "desc": "商品编码，关联 products.sku", "aliases": ["SKU", "商品"]},
            "promo_type": {"type": "TEXT", "desc": "coupon/lightning_deal/subscribe_save/prime_exclusive", "aliases": ["促销类型", "活动类型", "券类型"]},
            "start_date": {"type": "TEXT", "desc": "活动开始日期", "aliases": ["开始日期", "生效日", "活动开始"]},
            "end_date": {"type": "TEXT", "desc": "活动结束日期", "aliases": ["结束日期", "失效日", "活动结束"]},
            "discount_pct": {"type": "REAL", "desc": "折扣力度，0~1 之间的小数，0.2 表示打八折", "aliases": ["折扣", "折扣率", "折扣力度", "打几折", "优惠力度"]},
            "promo_price_usd": {"type": "REAL", "desc": "促销价（美元）", "aliases": ["促销价", "活动价", "券后价"]},
        },
    },
}


JOINS: list[dict] = [
    {"from": "order_items", "to": "orders", "on": "order_items.order_id = orders.order_id"},
    {"from": "order_items", "to": "products", "on": "order_items.sku = products.sku"},

    {"from": "returns", "to": "order_items",
     "on": "returns.order_id = order_items.order_id AND returns.sku = order_items.sku"},
    {"from": "returns", "to": "orders", "on": "returns.order_id = orders.order_id"},
    {"from": "returns", "to": "products", "on": "returns.sku = products.sku"},
    {"from": "ad_spend", "to": "products", "on": "ad_spend.sku = products.sku"},
    {"from": "inventory", "to": "products", "on": "inventory.sku = products.sku"},
    {"from": "reviews", "to": "products", "on": "reviews.sku = products.sku"},
    {"from": "promotions", "to": "products", "on": "promotions.sku = products.sku"},
]


DISPLAY_COLUMNS: dict[str, list[str]] = {
    "products": ["title", "category"],
}


KEY_COLUMNS: dict[str, list[str]] = {
    "products": ["sku"],
    "orders": ["order_id"],
    "order_items": ["order_id", "sku"],
    "ad_spend": ["sku", "stat_date"],
    "returns": ["order_id", "sku"],
    "inventory": ["sku", "snapshot_date"],
    "reviews": ["sku"],
    "promotions": ["sku"],
}


METRICS: list[dict] = [
    {
        "name": "销量",
        "expr": "SUM(order_items.quantity)",
        "note": "销量一律取 order_items.quantity，不要用 COUNT(*)；统计时应剔除已取消订单",
        "aliases": ["销量", "卖了多少", "出货量", "件数"],


        "requires": ["orders"],
    },
    {
        "name": "销售额 / GMV",
        "expr": "SUM(order_items.quantity * order_items.item_price_usd)",
        "note": "用成交单价而非挂牌价；剔除 cancelled 订单",
        "aliases": ["销售额", "GMV", "营收", "卖了多少钱", "营业额"],
        "requires": ["orders"],
    },
    {
        "name": "退货率（件数口径）",
        "expr": "COUNT(returns.return_id) * 1.0 / SUM(order_items.quantity)",
        "note": "分子用退货记录数，分母用销量件数；必须按 order_id + sku 双键关联，否则会笛卡尔放大",
        "aliases": ["退货率", "退货比例", "退款率"],
        "requires": ["orders"],
    },
    {
        "name": "ACOS 广告销售成本比",
        "expr": "SUM(ad_spend.spend_usd) / SUM(ad_spend.ad_sales_usd) * 100",


        "note": "统一输出百分比（乘 100），字段命名为 acos_pct；越低越好，>30% 视为投放效率差",
        "aliases": ["ACOS", "广告成本占比", "投产比"],
    },
    {
        "name": "ROAS 广告支出回报",
        "expr": "SUM(ad_spend.ad_sales_usd) / SUM(ad_spend.spend_usd)",
        "note": "输出倍数（8.5 表示 1 元广告费带来 8.5 元销售额），不乘 100；越高越好",
        "aliases": ["ROAS", "广告回报率"],
    },
    {
        "name": "CTR 点击率",
        "expr": "SUM(ad_spend.clicks) * 1.0 / SUM(ad_spend.impressions)",
        "note": "广告点击率",
        "aliases": ["CTR", "点击率"],
    },
    {
        "name": "毛利率",
        "expr": "(SUM(order_items.quantity * order_items.item_price_usd) - SUM(order_items.quantity * products.cost_usd)) / SUM(order_items.quantity * order_items.item_price_usd)",
        "note": "成本取自 products.cost_usd，需 JOIN products",
        "aliases": ["毛利率", "利润率", "毛利"],
    },
    {
        "name": "差评率",
        "expr": "SUM(CASE WHEN reviews.rating <= 2 THEN 1 ELSE 0 END) * 1.0 / COUNT(*)",

        "note": "1~2 星计为差评；参与排名的 SKU 要求评论数 >= 10（HAVING COUNT(*) >= 10）",
        "aliases": ["差评率", "差评比例", "低分率"],
    },
    {
        "name": "环比 / 同比增长",
        "expr": "当期值 - LAG(上期值) OVER (ORDER BY 期)",
        "note": "问「增长了多少」必须输出增长量这一列，不能只给当期值；用窗口函数 LAG，按月份排序",
        "aliases": ["环比", "同比增长", "增长了多少", "mom", "yoy"],
    },
    {
        "name": "可售天数 / 断货风险",
        "expr": "inventory.days_of_cover",
        "note": "直接取字段；判断断货用最新快照日 2026-06-29，days_of_cover < 15 视为高风险",
        "aliases": ["可售天数", "还能卖几天", "断货风险", "覆盖天数"],
    },
]


SERVICE_RULES: list[str] = [
    "数据窗口固定在 2026-04-01 ~ 2026-06-29；「上个月」指 2026-05，「本季度/Q2」指 2026-04 至 2026-06。",
    "统计销量和销售额时，默认剔除 orders.order_status = 'cancelled' 的订单；"
    "但单纯数订单量（不涉及件数和金额）时不要过滤，保留全部状态。",
    "退货率、退款相关指标统一走 returns 表，不通过 orders.order_status='returned' 判断。",
    "退款/退货类问题的时间范围按 returns.return_date 过滤，不要用订单下单日期。",
    "关联 order_items 与 returns 时必须双键：order_id 相同且 sku 相同，否则同一订单多 SKU 会造成笛卡尔放大。",
    "算占比类指标时先聚合再相除，注意用 *1.0 触发浮点运算，避免 SQLite 整数除法。",
    "排序取 Top N 时显式写 LIMIT N；不允许返回超过 200 行明细。",
]


SENSITIVE_TABLES = {"orders", "order_items", "returns"}


DIMENSION_BOOST: dict[str, float] = {"products": 4.0}


RELATIVE_THRESHOLD = 0.05


def all_tables() -> list[str]:
    return list(TABLES)


def table_ddl(table: str, columns: list[str] | None = None) -> str:

    meta = TABLES[table]
    cols = columns or list(meta["columns"])
    lines = [f"-- {table}: {meta['desc']}"]
    lines.append(f"CREATE TABLE {table} (")
    parts = []
    for c in cols:
        cm = meta["columns"].get(c)
        if not cm:
            continue
        comment = f"  -- {cm['desc']}" if cm["desc"] else ""
        parts.append(f"    {c} {cm['type']}{comment}")
    lines.append(",\n".join(parts))
    lines.append(");")
    return "\n".join(lines)


def join_hints(tables: list[str]) -> list[str]:

    s = set(tables)
    return [j["on"] for j in JOINS if j["from"] in s and j["to"] in s]
