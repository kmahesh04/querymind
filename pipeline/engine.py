"""The whole pipeline in one function: answer_query(question) -> QueryAnswer.

Flow: classify -> link -> retrieve examples -> generate SQL -> validate -> execute -> explain.
A rejected query is retried once with the rejection reason. Everything else fails closed with a message.
"""
import os
import re
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pipeline.access import ALL_TABLES, allowed_tables, authorizer_for
from pipeline.classify import classify
from pipeline.examples import EMBED_CACHE, build_retriever, load_examples
from pipeline.execute import ExecutionError, QueryTimeout, run_readonly
from pipeline.explain import model_summary, template_summary
from pipeline.generate import SqlRejected, generate_sql
from pipeline.linker import link
from pipeline.validate_sql import check_sql

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("SHOP_DB", ROOT / "data" / "shop.db"))
MAX_ATTEMPTS = 2

REFUSALS = {
    "unsafe": "This assistant only reads data. It cannot change, add or delete records.",
    "out_of_scope": "I can only answer questions about the store's orders, customers, products, "
                    "shipments, payments, returns, reviews and categories.",
}

_retrievers: dict[str, object] = {}


def _get_retriever(embed=None):
    """One retriever per kind, built once per process. Vector if an embedder is given, else TF-IDF."""
    key = "vector" if embed is not None else "tfidf"
    if key not in _retrievers:
        cacheable = getattr(embed, "cacheable", False)
        _retrievers[key] = build_retriever(
            load_examples(),
            embed,
            cache_path=EMBED_CACHE if cacheable else None,
            model_tag=getattr(embed, "model_tag", ""),
        )
    return _retrievers[key]


@dataclass
class QueryAnswer:
    question: str
    status: str                      # answered | refused | failed
    route: str = "data_query"
    summary: str = ""
    summary_source: str = ""         # model | template | ""
    sql: str | None = None           # the SQL the model wrote (before the safety wrapper)
    executed_sql: str | None = None  # what actually ran (validated and row-capped)
    assumption: str = ""
    linked_tables: list[str] = field(default_factory=list)
    retriever: str = ""              # vector | tfidf
    examples_used: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    truncated: bool = False
    attempts: int = 0
    elapsed_ms: int = 0
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def reference_date(db_path=DB_PATH) -> str:
    """Relative dates ('last 30 days') count back from the latest order in the data, not the real clock.
    The data ends at 2026-09-30, so 'last month' means September 2026 for a demo database."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return conn.execute("SELECT MAX(order_date) FROM orders").fetchone()[0]
    finally:
        conn.close()


def _touches(sql: str, tables: set) -> bool:
    """True if the SQL mentions any of the given table names."""
    return any(re.search(rf"\b{re.escape(t)}\b", sql, re.IGNORECASE) for t in tables)


def answer_query(question: str, llm=None, db_path=DB_PATH, explain_with_model: bool | None = None,
                 embed=None, role: str | None = None) -> QueryAnswer:
    """role limits what the model sees and what the database will return. None means no role limits."""
    start = time.monotonic()
    answer = QueryAnswer(question=question, status="answered")

    def done() -> QueryAnswer:
        answer.elapsed_ms = int((time.monotonic() - start) * 1000)
        return answer

    try:
        route = classify(question, llm)
    except Exception as exc:
        answer.status, answer.error = "failed", f"Could not classify the question: {exc}"
        return done()
    answer.route = route.label
    if route.label != "data_query":
        answer.status = "refused"
        answer.summary = REFUSALS[route.label]
        answer.summary_source = "template"
        return done()

    if llm is None:
        answer.status = "failed"
        answer.error = "No model key is set. Add GROK_API_KEY or GEMINI_API_KEY to .env to enable SQL generation."
        return done()

    allowed = set(allowed_tables(role)) if role else set(ALL_TABLES)
    forbidden = set(ALL_TABLES) - allowed
    authorizer = authorizer_for(role)
    answer.linked_tables = [t for t in link(question) if t in allowed] or sorted(allowed)

    retriever = _get_retriever(embed)
    try:
        examples = retriever.top(question, k=12)
    except Exception:
        retriever = _get_retriever(None)  # embedding failed at query time: keyword retrieval instead
        examples = retriever.top(question, k=12)
    # Drop examples that use tables this role cannot read, so the model does not copy them.
    examples = [e for e in examples if not _touches(e["sql"], forbidden)][:4]
    answer.retriever = retriever.kind
    answer.examples_used = [e["question"] for e in examples]
    ref_date = reference_date(db_path)

    feedback, result, assumption = None, None, ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        answer.attempts = attempt
        try:
            raw_sql, assumption = generate_sql(question, answer.linked_tables, examples, ref_date, llm, feedback)
        except SqlRejected as exc:
            feedback = str(exc)
            continue
        except Exception as exc:
            answer.status, answer.error = "failed", f"The model could not be reached. Try again. ({exc})"
            return done()
        answer.sql = raw_sql
        try:
            safe_sql = check_sql(raw_sql, db_path, authorizer)
            answer.executed_sql = safe_sql
            result = run_readonly(safe_sql, db_path, authorizer=authorizer)
            break
        except SqlRejected as exc:
            feedback = str(exc)
        except QueryTimeout as exc:
            answer.status, answer.error = "failed", str(exc)
            return done()
        except ExecutionError as exc:
            feedback = f"the query failed when run: {exc}"

    if result is None:
        answer.status = "failed"
        answer.error = f"Could not produce a valid query. Last problem: {feedback}"
        return done()

    answer.assumption = assumption
    answer.columns, answer.rows, answer.truncated = result.columns, result.rows, result.truncated
    answer.summary = template_summary(result, assumption)
    answer.summary_source = "template"

    if explain_with_model is None:
        explain_with_model = os.getenv("EXPLAIN_WITH_MODEL", "1") == "1"
    if explain_with_model and result.rows:
        try:
            text = model_summary(question, result, llm)
        except Exception:
            text = None  # the template summary is always available
        if text:
            answer.summary = f"{text} {('Assumption: ' + assumption) if assumption else ''}".strip()
            answer.summary_source = "model"
    return done()
