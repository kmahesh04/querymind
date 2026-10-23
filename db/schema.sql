-- QueryMind AI: e-commerce schema (SQLite dialect)
-- Dates are ISO-8601 text (YYYY-MM-DD). Use date() / julianday() for arithmetic.
PRAGMA foreign_keys = ON;

CREATE TABLE categories (
    category_id        INTEGER PRIMARY KEY,
    name               TEXT NOT NULL UNIQUE,
    parent_category_id INTEGER REFERENCES categories(category_id)
);

CREATE TABLE customers (
    customer_id  INTEGER PRIMARY KEY,
    full_name    TEXT NOT NULL,
    email        TEXT NOT NULL UNIQUE,
    city         TEXT NOT NULL,          -- home city (the account address)
    state        TEXT NOT NULL,
    segment      TEXT NOT NULL CHECK (segment IN ('standard', 'prime', 'business')),
    signup_date  TEXT NOT NULL
);

CREATE TABLE products (
    product_id   INTEGER PRIMARY KEY,
    sku          TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    category_id  INTEGER NOT NULL REFERENCES categories(category_id),
    brand        TEXT NOT NULL,
    unit_price   REAL NOT NULL CHECK (unit_price >= 0),
    cost_price   REAL NOT NULL CHECK (cost_price >= 0),
    is_active    INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    listed_date  TEXT NOT NULL
);

CREATE TABLE tags (
    tag_id  INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE
);

-- Many-to-many: a product can have many tags, a tag many products.
CREATE TABLE product_tags (
    product_id  INTEGER NOT NULL REFERENCES products(product_id),
    tag_id      INTEGER NOT NULL REFERENCES tags(tag_id),
    PRIMARY KEY (product_id, tag_id)
);

CREATE TABLE orders (
    order_id         INTEGER PRIMARY KEY,
    customer_id      INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date       TEXT NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('placed', 'shipped', 'delivered', 'cancelled', 'returned')),
    shipping_city    TEXT NOT NULL,      -- where this order was sent (can differ from home city)
    shipping_state   TEXT NOT NULL,
    payment_method   TEXT NOT NULL CHECK (payment_method IN ('card', 'upi', 'wallet', 'cod')),
    shipping_fee     REAL NOT NULL DEFAULT 0 CHECK (shipping_fee >= 0),
    discount_amount  REAL NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    total_amount     REAL NOT NULL CHECK (total_amount >= 0)   -- items - discount + shipping
);

CREATE TABLE order_items (
    order_item_id  INTEGER PRIMARY KEY,
    order_id       INTEGER NOT NULL REFERENCES orders(order_id),
    product_id     INTEGER NOT NULL REFERENCES products(product_id),
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    unit_price     REAL NOT NULL CHECK (unit_price >= 0),
    line_total     REAL NOT NULL CHECK (line_total >= 0)   -- quantity * unit_price, before discount
);

CREATE TABLE payments (
    payment_id  INTEGER PRIMARY KEY,
    order_id    INTEGER NOT NULL REFERENCES orders(order_id),
    amount      REAL NOT NULL CHECK (amount >= 0),
    method      TEXT NOT NULL,
    paid_at     TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('captured', 'failed', 'refunded'))
);

CREATE TABLE shipments (
    shipment_id     INTEGER PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES orders(order_id),
    carrier         TEXT NOT NULL CHECK (carrier IN ('FastShip', 'MetroExpress', 'PostLine', 'SwiftCourier')),
    tracking_number TEXT NOT NULL UNIQUE,
    shipped_at      TEXT NOT NULL,
    delivered_at    TEXT             -- NULL until delivered
);

CREATE TABLE returns (
    return_id      INTEGER PRIMARY KEY,
    order_item_id  INTEGER NOT NULL REFERENCES order_items(order_item_id),
    reason         TEXT NOT NULL CHECK (reason IN ('damaged', 'wrong_item', 'not_as_described', 'changed_mind')),
    requested_at   TEXT NOT NULL,
    refund_amount  REAL NOT NULL CHECK (refund_amount >= 0)
);

CREATE TABLE reviews (
    review_id    INTEGER PRIMARY KEY,
    product_id   INTEGER NOT NULL REFERENCES products(product_id),
    customer_id  INTEGER NOT NULL REFERENCES customers(customer_id),
    rating       INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    created_at   TEXT NOT NULL
);

CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_order_items_product ON order_items(product_id);
CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_payments_order ON payments(order_id);
CREATE INDEX idx_shipments_order ON shipments(order_id);
CREATE INDEX idx_reviews_product ON reviews(product_id);
