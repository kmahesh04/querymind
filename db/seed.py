"""Seed the e-commerce database with realistic synthetic data.

    python -m db.seed            # writes data/shop.db (rebuilt from scratch)

Deterministic: the same seed always produces the same rows, so gold SQL in the
evaluation set keeps returning the same results.
"""
from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "db" / "schema.sql"
DB_PATH = ROOT / "data" / "shop.db"
RNG = random.Random(42)

START, END = date(2025, 1, 1), date(2026, 9, 30)
DAYS = (END - START).days

CATEGORY_TREE = {
    "Electronics": ["Audio", "Computers", "Phones", "Cameras"],
    "Home & Kitchen": ["Cookware", "Small Appliances", "Furniture", "Bedding"],
    "Clothing": ["Men", "Women", "Kids", "Footwear"],
    "Books": ["Fiction", "Non-fiction", "Textbooks"],
    "Sports & Outdoors": ["Fitness", "Cycling", "Camping"],
    "Beauty & Personal Care": ["Skincare", "Haircare"],
    "Toys & Games": ["Board Games", "Building Sets"],
}

PRODUCT_NOUNS = {
    "Audio": ["Wireless Earbuds", "Bluetooth Speaker", "Noise-Cancelling Headphones", "Soundbar"],
    "Computers": ["Laptop 14in", "Mechanical Keyboard", "USB-C Hub", "External SSD 1TB"],
    "Phones": ["Smartphone 128GB", "Phone Case", "Fast Charger", "Screen Protector"],
    "Cameras": ["Mirrorless Camera", "Action Camera", "Tripod", "Memory Card 128GB"],
    "Cookware": ["Non-stick Pan", "Cast Iron Skillet", "Knife Set", "Stock Pot"],
    "Small Appliances": ["Air Fryer", "Coffee Grinder", "Blender", "Electric Kettle"],
    "Furniture": ["Office Chair", "Bookshelf", "Floor Lamp", "Side Table"],
    "Bedding": ["Cotton Sheet Set", "Memory Foam Pillow", "Weighted Blanket", "Duvet Cover"],
    "Men": ["Cotton T-Shirt", "Denim Jacket", "Chino Trousers", "Hoodie"],
    "Women": ["Summer Dress", "Yoga Leggings", "Knit Cardigan", "Blouse"],
    "Kids": ["School Backpack", "Raincoat", "Sneakers", "Story Pajamas"],
    "Footwear": ["Running Shoes", "Leather Boots", "Sandals", "Trail Shoes"],
    "Fiction": ["Mystery Novel", "Fantasy Trilogy Book 1", "Science Fiction Novel", "Thriller"],
    "Non-fiction": ["Productivity Guide", "History of Science", "Cookbook", "Biography"],
    "Textbooks": ["Intro to Statistics", "Organic Chemistry", "Data Structures Textbook", "World History"],
    "Fitness": ["Resistance Bands", "Yoga Mat", "Adjustable Dumbbells", "Foam Roller"],
    "Cycling": ["Bike Helmet", "Bike Light Set", "Water Bottle Cage", "Cycling Gloves"],
    "Camping": ["Two-person Tent", "Sleeping Bag", "Camp Stove", "Headlamp"],
    "Skincare": ["Vitamin C Serum", "Gentle Cleanser", "Moisturiser SPF30", "Sheet Mask Pack"],
    "Haircare": ["Repair Shampoo", "Argan Conditioner", "Hair Dryer", "Scalp Scrub"],
    "Board Games": ["Strategy Board Game", "Family Card Game", "Trivia Game", "Co-op Puzzle Game"],
    "Building Sets": ["City Building Set", "Robotics Kit", "Space Station Set", "Mini Vehicles Set"],
}

BRANDS = ["Northwind", "Apex", "Lumen", "Harbor", "Kestrel", "Meridian", "Orbit", "Pinecrest", "Summit", "Vale"]
TAGS = [
    "bestseller", "gift-idea", "eco-friendly", "budget", "premium", "new-arrival", "back-in-stock",
    "limited-edition", "travel", "office", "kids-safe", "waterproof", "wireless", "organic", "vegan",
    "handmade", "energy-saving", "compact", "family-pack", "winter", "summer", "outdoor", "studio",
    "beginner", "pro", "bundle", "clearance", "international", "dishwasher-safe", "lightweight",
]

FIRST = ["Aanya", "Rohan", "Maya", "Liam", "Sofia", "Ethan", "Priya", "Noah", "Isabella", "Arjun",
         "Olivia", "Kabir", "Emma", "Dev", "Chloe", "Vikram", "Ava", "Ishaan", "Mia", "Lucas"]
LAST = ["Shah", "Patel", "Nguyen", "Garcia", "Kim", "Brown", "Singh", "Khan", "Rossi", "Müller",
        "Okafor", "Silva", "Lopez", "Chen", "Walker", "Iyer", "Morgan", "Reddy", "Dubois", "Novak"]
CITIES = [
    ("Austin", "TX"), ("Seattle", "WA"), ("Denver", "CO"), ("Chicago", "IL"), ("Boston", "MA"),
    ("Atlanta", "GA"), ("Portland", "OR"), ("Phoenix", "AZ"), ("Nashville", "TN"), ("Miami", "FL"),
    ("Minneapolis", "MN"), ("San Diego", "CA"), ("Raleigh", "NC"), ("Columbus", "OH"),
]
PAYMENT_METHODS = ["card", "upi", "wallet", "cod"]
CARRIERS = ["FastShip", "MetroExpress", "PostLine", "SwiftCourier"]
RETURN_REASONS = ["damaged", "wrong_item", "not_as_described", "changed_mind"]

N_CUSTOMERS, N_PRODUCTS, N_ORDERS = 1200, 300, 5000


def rand_date(start: date = START, end: date = END) -> date:
    return start + timedelta(days=RNG.randint(0, (end - start).days))


def build_categories(conn: sqlite3.Connection) -> dict[str, int]:
    ids: dict[str, int] = {}
    next_id = 1
    for parent, children in CATEGORY_TREE.items():
        conn.execute("INSERT INTO categories VALUES (?, ?, NULL)", (next_id, parent))
        ids[parent] = next_id
        next_id += 1
    for parent, children in CATEGORY_TREE.items():
        for child in children:
            conn.execute("INSERT INTO categories VALUES (?, ?, ?)", (next_id, child, ids[parent]))
            ids[child] = next_id
            next_id += 1
    return ids


def build_customers(conn: sqlite3.Connection) -> list[tuple[int, str, str]]:
    rows = []
    segments = ["standard"] * 6 + ["prime"] * 3 + ["business"]
    for cid in range(1, N_CUSTOMERS + 1):
        first, last = RNG.choice(FIRST), RNG.choice(LAST)
        city, state = RNG.choice(CITIES)
        signup = rand_date(date(2022, 1, 1), date(2025, 6, 30))
        name = f"{first} {last}"
        email = f"{first.lower()}.{last.lower()}{cid}@example.com"
        conn.execute(
            "INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?)",
            (cid, name, email, city, state, RNG.choice(segments), signup.isoformat()),
        )
        rows.append((cid, city, state))
    return rows


def build_products(conn: sqlite3.Connection, category_ids: dict[str, int]) -> list[tuple[int, float]]:
    leaves = [child for children in CATEGORY_TREE.values() for child in children]
    rows = []
    pid = 1
    while pid <= N_PRODUCTS:
        leaf = leaves[(pid - 1) % len(leaves)]
        noun = RNG.choice(PRODUCT_NOUNS[leaf])
        brand = RNG.choice(BRANDS)
        unit = round(RNG.uniform(6, 480), 2)
        cost = round(unit * RNG.uniform(0.45, 0.7), 2)
        conn.execute(
            "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pid, f"SKU-{pid:05d}", f"{brand} {noun}", category_ids[leaf], brand,
             unit, cost, 1 if RNG.random() > 0.05 else 0, rand_date(date(2023, 1, 1), date(2025, 12, 31)).isoformat()),
        )
        rows.append((pid, unit))
        pid += 1
    return rows


def build_tags_and_links(conn: sqlite3.Connection, product_ids: list[int]) -> None:
    for tid, name in enumerate(TAGS, start=1):
        conn.execute("INSERT INTO tags VALUES (?, ?)", (tid, name))
    links = set()
    for pid in product_ids:
        for tid in RNG.sample(range(1, len(TAGS) + 1), RNG.randint(1, 4)):
            links.add((pid, tid))
    conn.executemany("INSERT INTO product_tags VALUES (?, ?)", sorted(links))


def build_orders(conn, customers, products) -> None:
    item_id = 1
    shipment_id = 1
    payment_id = 1
    return_id = 1
    review_id = 1
    for oid in range(1, N_ORDERS + 1):
        cid, home_city, home_state = RNG.choice(customers)
        # 80% ship to the home address; the rest go elsewhere (gifts, work address).
        if RNG.random() < 0.8:
            ship_city, ship_state = home_city, home_state
        else:
            ship_city, ship_state = RNG.choice(CITIES)
        order_day = rand_date()
        method = RNG.choice(PAYMENT_METHODS)

        lines = []
        for _ in range(RNG.randint(1, 4)):
            pid, unit = RNG.choice(products)
            qty = RNG.randint(1, 3)
            lines.append((pid, qty, unit, round(unit * qty, 2)))
        items_total = round(sum(l[3] for l in lines), 2)
        shipping_fee = 0.0 if items_total >= 50 else 5.99
        discount = round(items_total * RNG.choice([0, 0, 0, 0.05, 0.1, 0.15]), 2)
        total = round(items_total - discount + shipping_fee, 2)

        roll = RNG.random()
        if roll < 0.04:
            status = "cancelled"
        elif order_day > END - timedelta(days=10):
            status = "placed" if roll < 0.5 else "shipped"
        elif roll < 0.10:
            status = "returned"
        else:
            status = "delivered"

        conn.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (oid, cid, order_day.isoformat(), status, ship_city, ship_state, method,
             shipping_fee, discount, total),
        )
        for pid, qty, unit, line_total in lines:
            conn.execute(
                "INSERT INTO order_items VALUES (?, ?, ?, ?, ?, ?)",
                (item_id, oid, pid, qty, unit, line_total),
            )
            item_id += 1

        if status == "cancelled":
            conn.execute(
                "INSERT INTO payments VALUES (?, ?, ?, ?, ?, 'failed')",
                (payment_id, oid, total, method, order_day.isoformat()),
            )
            payment_id += 1
            continue

        conn.execute(
            "INSERT INTO payments VALUES (?, ?, ?, ?, ?, ?)",
            (payment_id, oid, total, method, order_day.isoformat(),
             "refunded" if status == "returned" else "captured"),
        )
        payment_id += 1

        if status in ("shipped", "delivered", "returned"):
            shipped = order_day + timedelta(days=RNG.randint(1, 3))
            delivered = None
            if status != "shipped":
                delivered = shipped + timedelta(days=RNG.randint(2, 9))
            conn.execute(
                "INSERT INTO shipments VALUES (?, ?, ?, ?, ?, ?)",
                (shipment_id, oid, RNG.choice(CARRIERS), f"TRK{shipment_id:08d}",
                 shipped.isoformat(), delivered.isoformat() if delivered else None),
            )
            shipment_id += 1

        if status == "returned":
            first_item = item_id - len(lines)
            ret_date = (order_day + timedelta(days=RNG.randint(10, 40))).isoformat()
            conn.execute(
                "INSERT INTO returns VALUES (?, ?, ?, ?, ?)",
                (return_id, first_item, RNG.choice(RETURN_REASONS), ret_date, round(lines[0][3], 2)),
            )
            return_id += 1

        if status in ("delivered", "returned") and RNG.random() < 0.35:
            pid = lines[0][0]
            conn.execute(
                "INSERT INTO reviews VALUES (?, ?, ?, ?, ?)",
                (review_id, pid, cid, RNG.randint(1, 5),
                 (order_day + timedelta(days=RNG.randint(5, 30))).isoformat()),
            )
            review_id += 1


def seed() -> dict[str, int]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))

    category_ids = build_categories(conn)
    customers = build_customers(conn)
    products = build_products(conn, category_ids)
    build_tags_and_links(conn, [p[0] for p in products])
    build_orders(conn, customers, products)
    conn.commit()

    counts = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ["categories", "customers", "products", "tags", "product_tags", "orders",
                      "order_items", "payments", "shipments", "returns", "reviews"]
    }
    conn.close()
    return counts


if __name__ == "__main__":
    for table, n in seed().items():
        print(f"{table:14} {n:>6}")
    print(f"\nWrote {DB_PATH}")
