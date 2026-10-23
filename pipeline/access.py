"""Role-based access: what each role may read, and whether personal data is masked for them.

Roles (see the proposal agreed for this project):
  ceo      every table and column, full customer names and emails
  manager  operations: no customers, no payments, no customer IDs, no refund amounts
  ba       business analysis: products, orders, shipments, reviews; no customers, payments or returns,
           no customer IDs

Enforcement is in the database engine, not in the prompt. SQLite calls an authorizer for every
table and column a query touches, while it compiles the query. A denied read fails even if the
model writes it, including through joins, subqueries and COUNT(*).
"""
import sqlite3

from pipeline.schema_info import ALLOWED_TABLES

ALL_TABLES = frozenset(ALLOWED_TABLES)

ROLES = {
    "ceo": {
        "label": "CEO",
        "tables": ALL_TABLES,
        "denied": frozenset(),
        "mask_pii": False,
    },
    "manager": {
        "label": "Manager",
        "tables": frozenset({"categories", "products", "tags", "product_tags", "orders", "order_items",
                             "shipments", "returns", "reviews"}),
        "denied": frozenset({
            ("orders", "customer_id"), ("orders", "payment_method"),
            ("reviews", "customer_id"), ("returns", "refund_amount"),
        }),
        "mask_pii": True,
    },
    "ba": {
        "label": "Business analyst",
        "tables": frozenset({"categories", "products", "tags", "product_tags", "orders", "order_items",
                             "shipments", "reviews"}),
        "denied": frozenset({
            ("orders", "customer_id"), ("orders", "payment_method"), ("reviews", "customer_id"),
        }),
        "mask_pii": True,
    },
}


def policy(role: str) -> dict:
    if role not in ROLES:
        raise ValueError(f"unknown role: {role}")
    return ROLES[role]


def allowed_tables(role: str) -> frozenset:
    return policy(role)["tables"]


def mask_pii(role: str) -> bool:
    return policy(role)["mask_pii"]


def authorizer_for(role: str | None):
    """A callback for sqlite3's set_authorizer. None means no restriction (the CEO, or an unrestricted run)."""
    if role is None or role == "ceo":
        return None
    rules = policy(role)
    tables, denied = rules["tables"], rules["denied"]

    def authorize(action, arg1, arg2, dbname, source):
        if action == sqlite3.SQLITE_READ:
            if arg1 not in tables or (arg1, arg2) in denied:
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    return authorize
