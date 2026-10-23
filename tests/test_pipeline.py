"""Tests for the QueryMind pipeline. No network, no API key, no third-party packages.

Run:  python3 tests/test_pipeline.py
(or:  python3 -m pytest tests/   if pytest is installed)
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.classify import classify  # noqa: E402
from pipeline.engine import answer_query, reference_date  # noqa: E402
import re  # noqa: E402
import tempfile  # noqa: E402
import zlib  # noqa: E402

from pipeline.examples import TfidfRetriever, VectorRetriever, build_retriever, load_examples  # noqa: E402
from pipeline.execute import ExecutionError, run_readonly  # noqa: E402
from pipeline.explain import numbers_grounded, template_summary  # noqa: E402
from pipeline.linker import link  # noqa: E402
from pipeline.schema_info import TABLES  # noqa: E402
from pipeline.util import parse_json  # noqa: E402
from pipeline.validate_sql import MAX_ROWS, SqlRejected, check_sql  # noqa: E402
from pipeline.execute import QueryResult  # noqa: E402

DB = ROOT / "data" / "shop.db"


def _ok(sql: str) -> str:
    return check_sql(sql, DB)


def _rejects(sql: str) -> str:
    try:
        check_sql(sql, DB)
    except SqlRejected as exc:
        return str(exc)
    raise AssertionError(f"should have been rejected: {sql}")


# ---- classification -------------------------------------------------------

def test_write_requests_are_unsafe_without_calling_model():
    def boom(*a, **k):
        raise AssertionError("model must not be called for write requests")
    assert classify("Delete all cancelled orders", boom).label == "unsafe"
    assert classify("please drop the customers table", boom).label == "unsafe"


def test_model_can_mark_small_talk_out_of_scope():
    fake = lambda s, p, j: '{"label": "out_of_scope", "reason": "not about the store"}'
    assert classify("write me a poem", fake).label == "out_of_scope"


def test_without_model_data_questions_pass():
    assert classify("How many orders are there?", None).label == "data_query"


# ---- linking --------------------------------------------------------------

def test_linker_picks_orders_and_neighbours_for_revenue():
    tables = link("What is the revenue from delivered orders?")
    assert "orders" in tables and "customers" in tables and "order_items" in tables


def test_linker_falls_back_when_nothing_matches():
    assert set(link("hello there")) >= {"orders", "customers", "products"}


def test_schema_dictionary_matches_database():
    conn = sqlite3.connect(DB)
    existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert set(TABLES) <= existing, f"missing in db: {set(TABLES) - existing}"


# ---- examples -------------------------------------------------------------

def test_at_least_30_examples_and_all_run_on_the_database():
    examples = load_examples()
    assert len(examples) >= 30, len(examples)
    conn = sqlite3.connect(DB)
    try:
        for e in examples:
            try:
                conn.execute(e["sql"]).fetchall()
            except sqlite3.Error as exc:
                raise AssertionError(f"example does not run: {e['question']} ({exc})")
    finally:
        conn.close()


def test_tfidf_retriever_finds_the_relevant_example():
    retriever = TfidfRetriever(load_examples())
    top = retriever.top("how many returns for each reason", k=3)
    assert any("reason" in e["question"].lower() for e in top)


def _fake_embed(texts, task_type):
    """Deterministic bag-of-words embedding so the vector path can be tested with no network."""
    out = []
    for t in texts:
        v = [0.0] * 128
        for w in re.findall(r"[a-z]+", t.lower()):
            v[zlib.crc32(w.encode()) % 128] += 1.0
        out.append(v)
    return out


def test_vector_retriever_ranks_relevant_example_first():
    retriever = VectorRetriever(load_examples(), _fake_embed)
    top = retriever.top("how many returns for each reason", k=3)
    assert any("reason" in e["question"].lower() for e in top)


def test_vector_cache_is_written_and_reused():
    examples = load_examples()
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "cache.json"
        VectorRetriever(examples, _fake_embed, cache_path=cache, model_tag="t")
        assert cache.exists()
        calls = {"n": 0}

        def counting(texts, task):
            calls["n"] += 1
            return _fake_embed(texts, task)
        VectorRetriever(examples, counting, cache_path=cache, model_tag="t")
        assert calls["n"] == 0, "second build should read the cache, not call the embedder"


def test_retriever_falls_back_to_tfidf_when_embedding_fails():
    def broken(texts, task):
        raise RuntimeError("quota exceeded")
    assert build_retriever(load_examples(), broken).kind == "tfidf"


# ---- validation -----------------------------------------------------------

def test_valid_select_gets_row_cap():
    sql = _ok("SELECT order_id FROM orders")
    assert sql.endswith(f"LIMIT {MAX_ROWS + 1}")


def test_cte_is_allowed():
    _ok("WITH x AS (SELECT customer_id FROM orders) SELECT COUNT(*) FROM x")


def test_rejects_multiple_statements():
    assert "one statement" in _rejects("SELECT 1; DROP TABLE orders")


def test_semicolon_inside_string_is_fine():
    _ok("SELECT * FROM customers WHERE full_name = 'a;b'")


def test_rejects_non_select():
    assert "SELECT" in _rejects("UPDATE orders SET status = 'x'")


def test_rejects_forbidden_keyword_inside_select():
    assert "DELETE" in _rejects("SELECT * FROM orders WHERE 1=1 AND 'x' = 'x' OR (SELECT 1) = 1 AND 0 = (DELETE)")


def test_rejects_unknown_table():
    assert "unknown table" in _rejects("SELECT * FROM users")


def test_rejects_unknown_column_via_sqlite_plan():
    assert "SQLite error" in _rejects("SELECT no_such_column FROM orders")


def test_empty_query_rejected():
    assert "empty" in _rejects("   ")


# ---- execution ------------------------------------------------------------

def test_readonly_connection_refuses_writes_even_if_validator_is_bypassed():
    try:
        run_readonly("UPDATE orders SET status = 'x' WHERE order_id = 1", DB)
    except ExecutionError:
        return
    raise AssertionError("write went through a read-only connection")


def test_executor_returns_rows():
    result = run_readonly(_ok("SELECT COUNT(*) AS n FROM orders"), DB)
    assert result.columns == ["n"] and result.rows[0][0] > 0


# ---- explanation ----------------------------------------------------------

def test_template_summary_single_value():
    r = QueryResult(columns=["revenue"], rows=[[12345.5]])
    assert template_summary(r) == "The answer is 12,345.5."


def test_template_summary_keeps_assumption():
    r = QueryResult(columns=["n"], rows=[[3]])
    assert template_summary(r, "Assumed September 2026.").endswith("Assumption: Assumed September 2026.")


def test_model_summary_with_invented_number_is_rejected():
    r = QueryResult(columns=["n"], rows=[[3]])
    assert not numbers_grounded("There were 40 orders.", r)
    assert numbers_grounded("There were 3 orders.", r)


# ---- end to end -----------------------------------------------------------

def test_end_to_end_with_fake_model():
    def fake(system, prompt, json_mode):
        if "classify" in system.lower() or "Classify" in prompt:
            return '{"label": "data_query", "reason": ""}'
        if "Use ONLY numbers" in system:
            return "There are 5000 orders in total."
        return json.dumps({"sql": "SELECT COUNT(*) AS total_orders FROM orders",
                           "assumption": ""})
    answer = answer_query("How many orders are there in total?", llm=fake, db_path=DB)
    assert answer.status == "answered", answer.error
    assert answer.rows[0][0] == 5000
    assert answer.summary_source == "model"
    assert answer.executed_sql.endswith(f"LIMIT {MAX_ROWS + 1}")


def test_end_to_end_retries_once_after_rejection():
    calls = {"n": 0}

    def fake(system, prompt, json_mode):
        if "Classify" in prompt:
            return '{"label": "data_query"}'
        if "Use ONLY numbers" in system:
            return ""
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps({"sql": "SELECT * FROM users", "assumption": ""})
        assert "rejected" in prompt, "retry prompt should carry the rejection reason"
        return json.dumps({"sql": "SELECT COUNT(*) AS n FROM customers", "assumption": ""})

    answer = answer_query("How many customers are there?", llm=fake, db_path=DB, explain_with_model=False)
    assert answer.status == "answered" and answer.attempts == 2


def test_end_to_end_reports_vector_retrieval():
    def fake(system, prompt, json_mode):
        if "Classify" in prompt:
            return '{"label": "data_query"}'
        if "Use ONLY numbers" in system:
            return ""
        return json.dumps({"sql": "SELECT COUNT(*) AS n FROM orders", "assumption": ""})
    answer = answer_query("How many orders?", llm=fake, db_path=DB, explain_with_model=False,
                          embed=_fake_embed)
    assert answer.status == "answered", answer.error
    assert answer.retriever == "vector"


def test_unsafe_question_never_reaches_sql_generation():
    def fake(*a, **k):
        raise AssertionError("should not be called")
    answer = answer_query("drop the orders table", llm=fake, db_path=DB)
    assert answer.status == "refused" and answer.route == "unsafe"


def test_no_key_fails_clearly():
    answer = answer_query("How many orders are there?", llm=None, db_path=DB)
    assert answer.status == "failed" and "API_KEY" in answer.error


def test_reference_date_is_latest_order():
    assert reference_date(DB) == "2026-09-30"


def test_parse_json_handles_fences_and_junk():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json("not json") == {}


if __name__ == "__main__":
    funcs = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    failed = 0
    for fn in funcs:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:  # report every failure, not just the first
            failed += 1
            print(f"FAIL {fn.__name__}: {exc!r}")
    print(f"\n{len(funcs) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
