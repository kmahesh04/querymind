"""Data dictionary: the single source for the schema linker, the SQL prompt and the admin schema page.

Keep this in sync with db/schema.sql. tests/test_pipeline.py checks that every table here exists.
"""

TABLES = {
    "customers": {
        "description": "Shoppers. city/state is the HOME address on the account, not where orders ship.",
        "keywords": {"customer", "customers", "shopper", "buyer", "member", "members", "segment", "prime",
                     "business", "signup", "signed", "home", "account", "city", "state", "people", "who"},
        "columns": {
            "customer_id": "primary key",
            "full_name": "customer name",
            "email": "unique email address",
            "city": "HOME city (use for 'customers in X' or 'X customers')",
            "state": "home state code",
            "segment": "standard | prime | business",
            "signup_date": "YYYY-MM-DD",
        },
    },
    "categories": {
        "description": "Product categories. parent_category_id gives a two-level tree (e.g. Audio -> Electronics).",
        "keywords": {"category", "categories", "electronics", "clothing", "books", "kitchen", "sports",
                     "beauty", "toys", "home", "department"},
        "columns": {
            "category_id": "primary key",
            "name": "category name",
            "parent_category_id": "parent category, NULL for top-level categories",
        },
    },
    "products": {
        "description": "Products for sale. unit_price is the current list price.",
        "keywords": {"product", "products", "item", "sku", "brand", "price", "priced", "sell", "sells", "name"},
        "columns": {
            "product_id": "primary key",
            "sku": "unique SKU",
            "name": "product name",
            "category_id": "references categories",
            "brand": "brand name",
            "unit_price": "list price",
            "cost_price": "cost to the store",
            "is_active": "1 = listed, 0 = delisted",
            "listed_date": "YYYY-MM-DD",
        },
    },
    "tags": {
        "description": "Labels such as eco-friendly or bestseller.",
        "keywords": {"tag", "tags", "label", "labels", "eco", "friendly", "bestseller", "gift"},
        "columns": {"tag_id": "primary key", "name": "tag name"},
    },
    "product_tags": {
        "description": "Many-to-many link between products and tags.",
        "keywords": {"tag", "tags", "tagged"},
        "columns": {"product_id": "references products", "tag_id": "references tags"},
    },
    "orders": {
        "description": "One row per order. status: placed, shipped, delivered, cancelled, returned. "
                       "shipping_city is where the order was sent. total_amount = items - discount + shipping.",
        "keywords": {"order", "orders", "status", "placed", "shipped", "delivered", "cancelled", "canceled",
                     "returned", "revenue", "sales", "total", "spend", "spent", "discount", "shipping",
                     "month", "year", "week", "date", "recent", "average", "value", "percentage", "rate",
                     "payment", "cod", "upi", "wallet", "card", "ship", "sent", "city"},
        "columns": {
            "order_id": "primary key",
            "customer_id": "references customers",
            "order_date": "YYYY-MM-DD",
            "status": "placed | shipped | delivered | cancelled | returned",
            "shipping_city": "city the order was shipped to",
            "shipping_state": "state the order was shipped to",
            "payment_method": "card | upi | wallet | cod",
            "shipping_fee": "shipping charged",
            "discount_amount": "discount applied",
            "total_amount": "amount paid for the order",
        },
    },
    "order_items": {
        "description": "Line items: which products are in which order, and how many.",
        "keywords": {"sold", "sell", "units", "unit", "quantity", "item", "items", "bought", "line", "top", "popular"},
        "columns": {
            "order_item_id": "primary key",
            "order_id": "references orders",
            "product_id": "references products",
            "quantity": "units in this line",
            "unit_price": "price per unit at time of order",
            "line_total": "quantity * unit_price, before discount",
        },
    },
    "payments": {
        "description": "Payment attempts for each order. status: captured, failed, refunded.",
        "keywords": {"payment", "payments", "paid", "pay", "failed", "captured", "refund", "refunded"},
        "columns": {
            "payment_id": "primary key",
            "order_id": "references orders",
            "amount": "amount charged",
            "method": "card | upi | wallet | cod",
            "paid_at": "YYYY-MM-DD",
            "status": "captured | failed | refunded",
        },
    },
    "shipments": {
        "description": "Shipment for each order that left the warehouse. delivered_at is NULL until delivered.",
        "keywords": {"shipment", "shipments", "carrier", "delivery", "deliver", "delivered", "delivery",
                     "tracking", "shipped", "transit", "courier", "days", "arrive", "arrived", "fastship",
                     "metroexpress", "postline", "swiftcourier", "ship", "time"},
        "columns": {
            "shipment_id": "primary key",
            "order_id": "references orders",
            "carrier": "FastShip | MetroExpress | PostLine | SwiftCourier",
            "tracking_number": "unique tracking number",
            "shipped_at": "YYYY-MM-DD",
            "delivered_at": "YYYY-MM-DD, NULL if not yet delivered",
        },
    },
    "returns": {
        "description": "A return request for one order line.",
        "keywords": {"return", "returns", "returned", "refund", "refunds", "reason", "reasons", "damaged"},
        "columns": {
            "return_id": "primary key",
            "order_item_id": "references order_items",
            "reason": "damaged | wrong_item | not_as_described | changed_mind",
            "requested_at": "YYYY-MM-DD",
            "refund_amount": "amount refunded",
        },
    },
    "reviews": {
        "description": "Customer ratings of products (1 to 5 stars).",
        "keywords": {"review", "reviews", "rating", "ratings", "rated", "stars", "star", "average", "feedback"},
        "columns": {
            "review_id": "primary key",
            "product_id": "references products",
            "customer_id": "references customers",
            "rating": "1 to 5",
            "created_at": "YYYY-MM-DD",
        },
    },
}

# (child table, parent table): the child holds a foreign key to the parent.
FOREIGN_KEYS = [
    ("products", "categories"),
    ("product_tags", "products"),
    ("product_tags", "tags"),
    ("orders", "customers"),
    ("order_items", "orders"),
    ("order_items", "products"),
    ("payments", "orders"),
    ("shipments", "orders"),
    ("returns", "order_items"),
    ("reviews", "products"),
    ("reviews", "customers"),
]

ALLOWED_TABLES = set(TABLES)
