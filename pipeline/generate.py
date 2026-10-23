"""Step 4: ask Gemini to write one SQLite SELECT from the linked schema and retrieved examples."""
from pipeline.schema_info import TABLES
from pipeline.util import parse_json
from pipeline.validate_sql import SqlRejected  # one class for every rejection, so the engine catches all of them


SYSTEM = """You write SQLite SELECT queries for an e-commerce database.

Rules:
- Reply with JSON only: {"sql": "<one SELECT statement>", "assumption": "<one short sentence or empty>"}.
- Write exactly one SELECT (a WITH clause is allowed). Never write data-changing SQL.
- Use only the tables and columns listed in the schema.
- Dates are ISO text 'YYYY-MM-DD'. Use strftime() and date() for periods.
- Relative periods ("last month", "last 30 days") are counted back from the reference date given.
- "Shipped to X" or "delivered to X" means orders.shipping_city. "Customers in X" or "X customers" means customers.city (home city).
- Exclude cancelled orders from revenue, spend and order value unless the question asks otherwise.
- Use the assumption field to state any interpretation you chose, for example the period or city column used.
"""


def schema_text(tables: list[str]) -> str:
    lines = []
    for name in tables:
        info = TABLES[name]
        lines.append(f"TABLE {name}: {info['description']}")
        for col, note in info["columns"].items():
            lines.append(f"  - {col}: {note}")
    return "\n".join(lines)


def build_prompt(question: str, tables: list[str], examples: list[dict], reference_date: str,
                 feedback: str | None) -> str:
    parts = [f"Reference date (today for relative periods): {reference_date}", "", "SCHEMA", schema_text(tables)]
    if examples:
        parts += ["", "EXAMPLES"]
        for e in examples:
            parts.append(f"Q: {e['question']}\nSQL: {e['sql']}")
    if feedback:
        parts += ["", f"Your previous SQL was rejected: {feedback}. Fix it and reply again."]
    parts += ["", f"QUESTION: {question}"]
    return "\n".join(parts)


def generate_sql(question: str, tables: list[str], examples: list[dict], reference_date: str,
                 llm, feedback: str | None = None) -> tuple[str, str]:
    raw = llm(SYSTEM, build_prompt(question, tables, examples, reference_date, feedback), True)
    data = parse_json(raw)
    sql = data.get("sql")
    if not isinstance(sql, str) or not sql.strip():
        raise SqlRejected("the reply did not contain a SQL query")
    assumption = data.get("assumption") or ""
    return sql.strip(), str(assumption).strip()
