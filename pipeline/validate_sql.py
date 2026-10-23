"""Step 5: deterministic SQL safety checks. No model is involved here.

Checks, in order:
  1. Non-empty, one statement only (no semicolon outside string literals).
  2. Starts with SELECT or WITH.
  3. No data-changing or admin keywords.
  4. Every table in FROM / JOIN is in the data dictionary (or a CTE defined in the query).
  5. SQLite can plan it (EXPLAIN), which catches unknown columns and syntax errors.
Then the query is wrapped so a row cap always applies, even if the model forgot LIMIT.
"""
import re
import sqlite3

from pipeline.schema_info import ALLOWED_TABLES

MAX_ROWS = 100
FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|replace|vacuum|reindex|"
    r"trigger|truncate|grant|savepoint|release)\b",
    re.IGNORECASE,
)


class SqlRejected(ValueError):
    """Raised with a short, user-readable reason."""


def _strip_string_literals(sql: str) -> str:
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def check_sql(sql: str, db_path, authorizer=None) -> str:
    """Return a safe, row-capped SQL string, or raise SqlRejected."""
    text = sql.strip().rstrip(";").strip()
    if not text:
        raise SqlRejected("the query was empty")

    bare = _strip_string_literals(text)
    if ";" in bare:
        raise SqlRejected("only one statement is allowed")
    if not re.match(r"^(select|with)\b", bare, re.IGNORECASE):
        raise SqlRejected("only SELECT queries are allowed")

    forbidden = FORBIDDEN.search(bare)
    if forbidden:
        raise SqlRejected(f"the keyword {forbidden.group(1).upper()} is not allowed")

    cte_names = {name.lower() for name in re.findall(r"(\w+)\s+AS\s*\(", bare, re.IGNORECASE)}
    referenced = {t.lower() for t in re.findall(r"\b(?:from|join)\s+([A-Za-z_]\w*)", bare, re.IGNORECASE)}
    unknown = referenced - {t.lower() for t in ALLOWED_TABLES} - cte_names
    if unknown:
        raise SqlRejected(f"unknown table: {', '.join(sorted(unknown))}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    if authorizer is not None:
        conn.set_authorizer(authorizer)
    try:
        conn.execute(f"EXPLAIN {text}").fetchall()
    except sqlite3.Error as exc:
        raise SqlRejected(f"SQLite error: {exc}") from exc
    finally:
        conn.close()

    # One extra row lets the executor tell "exactly 100 rows" from "more than 100 rows".
    return f"SELECT * FROM ({text}) LIMIT {MAX_ROWS + 1}"
