
from __future__ import annotations

import argparse
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

SEED = 42
START = date(2026, 4, 1)
DAYS = 90
END = START + timedelta(days=DAYS - 1)

N_PRODUCTS = 60
N_ORDERS = 4200
N_REVIEWS = 1600
N_PROMOS = 200

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCHEMA_SQL = HERE / "schema.sql"
DB_PATH = ROOT / "data" / "app.db"

CATEGORIES = {
    "Kitchen": ["Cookware", "Cutlery", "Bakeware", "Small Appliance", "Food Storage"],
    "Bedding": ["Sheet Set", "Duvet", "Pillow", "Mattress Topper", "Blanket"],
    "Bath": ["Towel", "Shower Curtain", "Bath Mat", "Storage Caddy", "Faucet"],
    "Storage": ["Shelf", "Drawer Organizer", "Storage Box", "Closet Rack", "Vacuum Bag"],
    "Decor": ["Wall Art", "Vase", "Candle", "Mirror", "Clock"],
    "Lighting": ["Floor Lamp", "Table Lamp", "String Light", "Ceiling Light", "Night Light"],
    "Furniture": ["Desk", "Chair", "Nightstand", "Bookshelf", "Sofa Cover"],
    "Outdoor": ["Patio Set", "Garden Hose", "Grill Cover", "Planter", "Umbrella"],
}

BRANDS = {
    "Kitchen": ["HomeNest", "ChefCraft"],
    "Bedding": ["PureRest", "DreamWeave"],
    "Bath": ["AquaLuxe", "SpaHaven"],
    "Storage": ["Orderly", "StackMax"],
    "Decor": ["Vividly", "Ardene"],
    "Lighting": ["Lumos", "BrightNest"],
    "Furniture": ["Woodcraft", "StudioLine"],
    "Outdoor": ["Verdant", "PatioPro"],
}

FEATURES = ["Nonstick", "Memory Foam", "Quick-Dry", "Adjustable", "Bamboo", "LED",
            "Foldable", "Heavy-Duty", "Cordless", "Vintage", "Matte", "Reinforced"]

REASONS = ["damaged", "not_as_described", "no_longer_needed", "wrong_item",
           "defective", "arrived_late"]
REASON_W = [0.18, 0.22, 0.25, 0.11, 0.12, 0.12]

CAMPAIGNS = ["SP", "SB", "SD"]


def _d(offset: int) -> str:
    return (START + timedelta(days=offset)).isoformat()


def _rand_date(rng: random.Random) -> str:

    off = rng.choices(range(DAYS), weights=[1.15 if (START + timedelta(days=i)).weekday() >= 5 else 1.0
                                            for i in range(DAYS)])[0]
    return _d(off)


def build_products(rng: random.Random):

    rows, meta = [], {}
    cats = list(CATEGORIES)
    idx = 0
    for i in range(N_PRODUCTS):
        cat = cats[i % len(cats)]
        sub = rng.choice(CATEGORIES[cat])
        brand = rng.choice(BRANDS[cat])
        feat = rng.choice(FEATURES)
        sku = f"HN-{cat[:3].upper()}-{1000 + idx}"
        idx += 1
        title = f"{brand} {feat} {sub}"
        cost = round(rng.uniform(3.5, 120), 2)
        price = round(cost * rng.uniform(2.1, 3.3), 2)

        launch = _d(-rng.randint(30, 400)) if rng.random() < 0.75 else _d(rng.randint(0, 60))
        status = "delisted" if rng.random() < 0.05 else ("paused" if rng.random() < 0.08 else "active")
        rows.append((
            sku, title, cat, sub, brand, launch, cost, price,
            1 if rng.random() < 0.72 else 0, round(rng.uniform(0.2, 12), 2), None, 0, status,
        ))
        pop = rng.uniform(0.25, 3.0)
        if status == "delisted":
            pop *= 0.15
        elif status == "paused":
            pop *= 0.5
        meta[sku] = {
            "cat": cat, "price": price, "cost": cost,
            "popularity": round(pop, 3),
            "return_rate": 0.09,
            "ad_sku": rng.random() < 0.68 and status == "active",
            "star": 0,
        }

    skus = list(meta)

    bedding = [s for s in skus if meta[s]["cat"] == "Bedding"]
    for s in rng.sample(bedding, 2):
        meta[s]["return_rate"] = rng.uniform(0.30, 0.42)
        meta[s]["defect_bias"] = True
        meta[s]["star"] = -1

    lighting = [s for s in skus if meta[s]["cat"] == "Lighting"]
    burn = rng.choice(lighting)
    meta[burn]["ad_sku"] = True
    meta[burn]["burn_money"] = True

    low_return = [s for s in skus if meta[s]["return_rate"] < 0.2]
    for s in rng.sample(low_return, 3):
        meta[s]["stockout"] = True

    promo_hero = rng.choice([s for s in skus if meta[s]["popularity"] > 0.8])
    meta[promo_hero]["promo_hero"] = True
    return rows, meta, skus, promo_hero


def main(force: bool = False) -> None:
    if DB_PATH.exists() and not force:
        print(f"[skip] {DB_PATH} 已存在，如需重建请加 --force")
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)

    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))

    products, meta, skus, promo_hero = build_products(rng)
    con.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", products)


    weights = [meta[s]["popularity"] for s in skus]
    orders, items = [], []
    for i in range(N_ORDERS):
        oid = f"112-{100000 + i}"
        odate = _rand_date(rng)
        mk = rng.choices(["US", "CA", "MX"], weights=[0.85, 0.10, 0.05])[0]
        region = rng.choice(["West", "East", "Central", "South"])
        status = rng.choices(["delivered", "shipped", "cancelled", "returned"],
                             weights=[0.74, 0.16, 0.05, 0.05])[0]
        orders.append((oid, odate, mk, region, 1 if rng.random() < 0.62 else 0,
                       status, "new" if rng.random() < 0.38 else "returning"))
        for _ in range(rng.choices([1, 2, 3], weights=[0.62, 0.28, 0.10])[0]):
            sku = rng.choices(skus, weights=weights)[0]
            qty = rng.choices([1, 2, 3, 4], weights=[0.66, 0.22, 0.08, 0.04])[0]
            disc = round(rng.uniform(0, meta[sku]["price"] * 0.25), 2) if rng.random() < 0.35 else 0.0
            ship = round(rng.uniform(0, 6.5), 2)
            items.append((oid, sku, qty, round(meta[sku]["price"] - disc, 2), disc, ship))
    con.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?)", orders)
    con.executemany(
        "INSERT INTO order_items (order_id, sku, quantity, item_price_usd, discount_usd, shipping_fee_usd)"
        " VALUES (?,?,?,?,?,?)", items)


    reviews = []
    for _ in range(N_REVIEWS):
        sku = rng.choices(skus, weights=weights)[0]
        base = 4.4 if meta[sku]["star"] >= 0 else 3.1
        rating = max(1, min(5, int(round(rng.gauss(base, 0.95)))))
        reviews.append((sku, _rand_date(rng), rating, 1 if rng.random() < 0.78 else 0,
                        1 if rng.random() < 0.41 else 0, rng.choices([0, 1, 2, 3, 5, 8, 15],
                        weights=[0.42, 0.22, 0.14, 0.09, 0.07, 0.04, 0.02])[0],
                        rng.choice(["Great quality", "As described", "Not what I expected",
                                    "Fast shipping", "Broke quickly", "Love it", "Meh"])))
    con.executemany(
        "INSERT INTO reviews (sku, review_date, rating, is_verified, has_image, helpful_votes, title)"
        " VALUES (?,?,?,?,?,?,?)", reviews)


    agg = con.execute("SELECT sku, COUNT(*), AVG(rating) FROM reviews GROUP BY sku").fetchall()
    con.executemany("UPDATE products SET review_count=?, rating=? WHERE sku=?",
                    [(c, round(a, 2), s) for s, c, a in agg])


    ad = []
    ad_skus = [s for s in skus if meta[s]["ad_sku"]]
    for s in ad_skus:
        burn = meta[s].get("burn_money", False)
        for d in range(DAYS):
            for camp in rng.sample(CAMPAIGNS, rng.choice([1, 1, 2])):
                impressions = rng.randint(400, 9000)
                ctr = rng.uniform(0.002, 0.012)
                clicks = max(0, int(impressions * ctr))
                cpc = rng.uniform(1.05, 1.45) if burn else rng.uniform(0.32, 0.92)
                spend = round(clicks * cpc, 2)
                cvr = rng.uniform(0.004, 0.02) if burn else rng.uniform(0.03, 0.13)
                ad_sales = round(clicks * cvr * meta[s]["price"], 2)
                ad.append((_d(d), s, camp, impressions, clicks, spend, ad_sales))
    con.executemany(
        "INSERT INTO ad_spend (stat_date, sku, campaign_type, impressions, clicks, spend_usd, ad_sales_usd)"
        " VALUES (?,?,?,?,?,?,?)", ad)


    rets = []
    for oid, sku, qty, price, _, _ in items:
        p = meta[sku]["return_rate"]
        if rng.random() >= p:
            continue
        if meta[sku].get("defect_bias"):
            reason = rng.choices(REASONS, weights=[0.30, 0.10, 0.05, 0.05, 0.45, 0.05])[0]
        else:
            reason = rng.choices(REASONS, weights=REASON_W)[0]
        od = con.execute("SELECT order_date FROM orders WHERE order_id=?", (oid,)).fetchone()[0]
        y, m, dd = map(int, od.split("-"))
        rd = date(y, m, dd) + timedelta(days=rng.randint(3, 25))
        if rd > END:
            continue
        rets.append((oid, sku, rd.isoformat(), reason,
                     round(price * qty * rng.uniform(0.85, 1.0), 2),
                     1 if reason in ("defective", "damaged") else 0,
                     1 if (reason == "no_longer_needed" or rng.random() < 0.55) else 0))
    con.executemany(
        "INSERT INTO returns (order_id, sku, return_date, reason, refund_usd, is_defective, is_resellable)"
        " VALUES (?,?,?,?,?,?,?)", rets)


    inv = []
    daily = {s: max(0.05, meta[s]["popularity"] * 2.2) for s in skus}
    for s in skus:
        stock = 30 if meta[s].get("stockout") else int(rng.uniform(120, 900))
        for d in range(DAYS):
            avail = max(0, int(stock * rng.uniform(0.75, 1.25)))
            inv.append((_d(d), s, avail, rng.randint(0, 260), rng.randint(0, 90),
                        round(avail / daily[s], 1)))
    con.executemany(
        "INSERT INTO inventory (snapshot_date, sku, available_units, inbound_units, reserved_units, days_of_cover)"
        " VALUES (?,?,?,?,?,?)", inv)


    promos = []
    for i in range(N_PROMOS):
        s = promo_hero if i % 40 == 0 else rng.choice(skus)
        sd = rng.randint(0, DAYS - 8)
        ed = min(DAYS - 1, sd + rng.randint(7, 30))
        pct = round(rng.uniform(0.05, 0.35), 3)
        promos.append((s, rng.choice(["coupon", "lightning_deal", "subscribe_save", "prime_exclusive"]),
                       _d(sd), _d(ed), pct, round(meta[s]["price"] * (1 - pct), 2)))
    con.executemany(
        "INSERT INTO promotions (sku, promo_type, start_date, end_date, discount_pct, promo_price_usd)"
        " VALUES (?,?,?,?,?,?)", promos)

    con.commit()

    print(f"[ok] 数据库已生成: {DB_PATH}")
    for t in ["products", "orders", "order_items", "ad_spend", "returns",
              "inventory", "reviews", "promotions"]:
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"     {t:<12} {n:>7,} 行")
    print(f"\n植入的高退货 SKU: {[s for s in skus if meta[s]['return_rate'] > 0.2]}")
    print(f"植入的烧钱广告 SKU: {[s for s in skus if meta[s].get('burn_money')]}")
    print(f"植入的断货风险 SKU: {[s for s in skus if meta[s].get('stockout')]}")
    print(f"促销放量 SKU: {promo_hero}")
    con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="强制重建数据库")
    main(force=ap.parse_args().force)
