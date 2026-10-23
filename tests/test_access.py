"""Checks the role rules against the real database engine. Offline: no model calls.

Run: python3 tests/test_access.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.access import allowed_tables, authorizer_for, mask_pii  # noqa: E402
from pipeline.execute import ExecutionError, run_readonly  # noqa: E402
from pipeline.validate_sql import SqlRejected, check_sql  # noqa: E402

DB = ROOT / "data" / "shop.db"


def _runs(role, sql):
    """True if the role can run the SQL against the database."""
    try:
        run_readonly(sql, DB, authorizer=authorizer_for(role))
        return True
    except ExecutionError:
        return False


def test_ceo_reads_everything():
    assert _runs("ceo", "SELECT full_name, email FROM customers LIMIT 1")
    assert _runs("ceo", "SELECT COUNT(*) FROM payments")
    assert _runs("ceo", "SELECT refund_amount FROM returns LIMIT 1")
    assert _runs("ceo", "SELECT customer_id FROM orders LIMIT 1")


def test_ba_cannot_read_customers_payments_or_returns():
    assert not _runs("ba", "SELECT full_name FROM customers")
    assert not _runs("ba", "SELECT COUNT(*) FROM customers")
    assert not _runs("ba", "SELECT COUNT(*) FROM payments")
    assert not _runs("ba", "SELECT COUNT(*) FROM returns")


def test_ba_cannot_reach_customers_through_a_join_or_subquery():
    assert not _runs("ba", "SELECT o.order_id, c.full_name FROM orders o "
                           "JOIN customers c ON c.customer_id = o.customer_id")
    assert not _runs("ba", "SELECT COUNT(*) FROM orders WHERE customer_id IN "
                           "(SELECT customer_id FROM customers)")


def test_ba_reads_business_data_but_not_customer_ids():
    assert _runs("ba", "SELECT status, COUNT(*) FROM orders GROUP BY status")
    assert _runs("ba", "SELECT name, unit_price FROM products LIMIT 5")
    assert not _runs("ba", "SELECT customer_id FROM orders LIMIT 1")
    assert not _runs("ba", "SELECT payment_method FROM orders LIMIT 1")


def test_manager_sees_operations_but_not_refunds_or_payments():
    assert _runs("manager", "SELECT reason, COUNT(*) FROM returns GROUP BY reason")
    assert _runs("manager", "SELECT order_id, status FROM orders LIMIT 5")
    assert not _runs("manager", "SELECT refund_amount FROM returns LIMIT 1")
    assert not _runs("manager", "SELECT COUNT(*) FROM payments")
    assert not _runs("manager", "SELECT full_name FROM customers")


def test_validator_rejects_forbidden_tables_before_execution():
    try:
        check_sql("SELECT email FROM customers", DB, authorizer_for("ba"))
    except SqlRejected:
        pass
    else:
        raise AssertionError("the BA role should be refused at validation")


def test_allowed_tables_and_masking_by_role():
    assert "customers" in allowed_tables("ceo")
    assert "customers" not in allowed_tables("ba")
    assert "customers" not in allowed_tables("manager")
    assert mask_pii("ceo") is False
    assert mask_pii("ba") is True
    assert mask_pii("manager") is True


if __name__ == "__main__":
    funcs = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    failed = 0
    for fn in funcs:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc!r}")
    print(f"\n{len(funcs) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
