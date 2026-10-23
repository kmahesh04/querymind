"""Masks personal data in answers before they leave the API or reach the query log.

Names and emails are looked up from the customers table, so masking still works when a query
renames the column (for example SELECT full_name AS buyer). The database itself is not changed,
and the eval scores raw answers, so masking does not affect accuracy.

Masking rules:
  email   a@example.com  -> a***@example.com
  name    Komal Shah     -> K*** S***
  phone, address, street columns -> ***
"""
import re
import sqlite3
from functools import lru_cache

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ALWAYS_HIDE_COLUMNS = {"phone", "phone_number", "address", "street", "street_address", "postcode", "zip"}


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def mask_name(name: str) -> str:
    return " ".join(f"{word[0]}***" for word in name.split() if word)


@lru_cache(maxsize=4)
def _known_pii(db_path: str) -> tuple[frozenset, frozenset]:
    """Every customer name and email in the database, read once per process."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT full_name, email FROM customers").fetchall()
    finally:
        con.close()
    names = frozenset(r[0] for r in rows if r[0])
    emails = frozenset(r[1] for r in rows if r[1])
    return names, emails


def _mask_value(value, names, emails):
    if not isinstance(value, str):
        return value
    if value in emails or EMAIL_RE.fullmatch(value):
        return mask_email(value)
    if value in names:
        return mask_name(value)
    return value


def mask_rows(columns: list[str], rows: list[list], db_path) -> list[list]:
    names, emails = _known_pii(str(db_path))
    hidden = [str(c).lower() in ALWAYS_HIDE_COLUMNS for c in columns]
    masked = []
    for row in rows:
        masked.append([
            "***" if hidden[i] and value is not None else _mask_value(value, names, emails)
            for i, value in enumerate(row)
        ])
    return masked


def mask_text(text: str | None, db_path) -> str | None:
    """Mask emails and known customer names inside free text (summaries, questions, SQL literals)."""
    if not text:
        return text
    names, _ = _known_pii(str(db_path))
    text = EMAIL_RE.sub(lambda m: mask_email(m.group(0)), text)
    for name in names:
        if name in text:
            text = text.replace(name, mask_name(name))
    return text


def mask_answer(data: dict, db_path, mask: bool = True) -> dict:
    """Return a copy of an answer dict with personal data masked. Used before returning and logging."""
    out = dict(data)
    if not mask:
        return out  # the CEO sees full names and emails
    out["summary"] = mask_text(out.get("summary"), db_path)
    out["question"] = EMAIL_RE.sub(lambda m: mask_email(m.group(0)), out.get("question") or "")
    out["sql"] = EMAIL_RE.sub(lambda m: mask_email(m.group(0)), out.get("sql") or "") or out.get("sql")
    if out.get("rows"):
        out["rows"] = mask_rows(out.get("columns") or [], out["rows"], db_path)
    return out
