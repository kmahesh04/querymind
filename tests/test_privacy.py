"""Checks that personal data is masked before answers leave the API. Offline: no model calls.

Run: python3 tests/test_privacy.py
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.privacy import mask_answer, mask_email, mask_name, mask_rows, mask_text  # noqa: E402

DB = ROOT / "data" / "shop.db"


def _real_customer():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        return con.execute("SELECT full_name, email FROM customers LIMIT 1").fetchone()
    finally:
        con.close()


def test_mask_formats():
    assert mask_email("komal@example.com") == "k***@example.com"
    assert mask_name("Komal Shah") == "K*** S***"


def test_real_name_and_email_are_masked_in_rows():
    name, email = _real_customer()
    rows = mask_rows(["who", "contact"], [[name, email]], DB)
    assert rows[0][0] == mask_name(name), rows
    assert rows[0][1] == mask_email(email), rows


def test_renamed_column_is_still_masked():
    # The column is aliased, so the column name gives nothing away. The value is still found.
    name, _ = _real_customer()
    rows = mask_rows(["buyer"], [[name]], DB)
    assert rows[0][0] == mask_name(name), rows


def test_phone_and_address_columns_are_hidden():
    rows = mask_rows(["phone", "address"], [["555-0100", "1 Main St"]], DB)
    assert rows[0] == ["***", "***"], rows


def test_numbers_and_other_text_are_untouched():
    rows = mask_rows(["orders", "status"], [[272, "delivered"]], DB)
    assert rows[0] == [272, "delivered"], rows


def test_email_in_free_text_is_masked():
    assert "k***@example.com" in mask_text("Contact komal@example.com for help", DB)


def test_mask_answer_masks_rows_summary_and_question():
    name, email = _real_customer()
    data = {
        "question": f"orders for {email}",
        "summary": f"{name} placed 1 order.",
        "sql": f"SELECT * FROM customers WHERE email = '{email}'",
        "columns": ["buyer"],
        "rows": [[name]],
    }
    out = mask_answer(data, DB)
    assert name not in out["summary"]
    assert email not in out["question"]
    assert email not in out["sql"]
    assert out["rows"][0][0] == mask_name(name)
    # The original dict is not changed.
    assert data["rows"][0][0] == name


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
