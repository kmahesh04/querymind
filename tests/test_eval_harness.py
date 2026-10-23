"""Checks that the eval scorer itself is right. Offline: no model calls.

Run: python3 tests/test_eval_harness.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.harness import load_gold, results_match, score_case, summarise  # noqa: E402
from pipeline.engine import QueryAnswer  # noqa: E402
from pipeline.execute import run_readonly  # noqa: E402
from pipeline.validate_sql import check_sql  # noqa: E402

DB = ROOT / "data" / "shop.db"
CASES = json.loads((ROOT / "evals" / "eval_set.json").read_text(encoding="utf-8"))


def _answer_from_sql(question: str, sql: str) -> QueryAnswer:
    """Build the answer the pipeline would give if the model wrote this SQL."""
    result = run_readonly(check_sql(sql, DB), DB)
    return QueryAnswer(question=question, status="answered", route="data_query", sql=sql,
                       columns=result.columns, rows=result.rows, truncated=result.truncated,
                       attempts=1, retriever="vector")


def test_eval_set_has_25_cases_with_expected_mix():
    assert len(CASES) == 25
    assert sum(1 for c in CASES if c["expect"] == "answered") == 23
    assert {c["expect_route"] for c in CASES if c["expect"] == "refused"} == {"unsafe", "out_of_scope"}
    ids = [c["id"] for c in CASES]
    assert len(set(ids)) == len(ids)


def test_gold_sql_scores_full_marks_when_submitted_as_the_answer():
    results = []
    for case in CASES:
        if case["expect"] != "answered":
            continue
        gold = load_gold(case, DB)
        answer = _answer_from_sql(case["question"], case["gold_sql"])
        results.append(score_case(case, answer, gold))
    failed = [r["id"] for r in results if not r["passed"]]
    assert not failed, f"gold SQL should always match itself: {failed}"


def test_equivalent_query_written_differently_still_passes():
    case = next(c for c in CASES if c["id"] == "q03")
    other = "SELECT COUNT(*) AS n FROM payments WHERE method = 'upi' AND status = 'failed'"
    result = score_case(case, _answer_from_sql(case["question"], other), load_gold(case, DB))
    assert result["passed"], result["reason"]


def test_ambiguity_wrong_column_fails():
    case = next(c for c in CASES if c["id"] == "q17")  # delivered orders to Denver (shipping city)
    wrong = "SELECT COUNT(*) AS orders FROM orders WHERE status = 'delivered' AND customer_id IN (SELECT customer_id FROM customers WHERE city = 'Denver')"
    result = score_case(case, _answer_from_sql(case["question"], wrong), load_gold(case, DB))
    assert not result["passed"], "using home city instead of shipping city must fail"


def test_wrong_number_fails():
    case = next(c for c in CASES if c["id"] == "q12")
    result = score_case(case, _answer_from_sql(case["question"], "SELECT 999 AS orders"), load_gold(case, DB))
    assert not result["passed"]


def test_refusal_cases_pass_only_with_the_right_route():
    case = next(c for c in CASES if c["id"] == "q24")  # expect unsafe
    ok = QueryAnswer(question=case["question"], status="refused", route="unsafe")
    wrong = QueryAnswer(question=case["question"], status="refused", route="out_of_scope")
    answered = QueryAnswer(question=case["question"], status="answered", route="data_query")
    assert score_case(case, ok, None)["passed"]
    assert not score_case(case, wrong, None)["passed"]
    assert not score_case(case, answered, None)["passed"]


def test_float_rounding_tolerance():
    gold = run_readonly("SELECT 2.499 AS x", DB)
    ok, _ = results_match(gold, ["x"], [[2.5]])
    assert ok


def test_summary_breaks_down_by_type():
    results = [
        {"type": "join", "passed": True, "expect": "answered", "attempts": 1, "elapsed_ms": 10, "retriever": "vector"},
        {"type": "join", "passed": False, "expect": "answered", "attempts": 2, "elapsed_ms": 30, "retriever": "vector"},
        {"type": "unsafe", "passed": True, "expect": "refused", "attempts": 0, "elapsed_ms": 1, "retriever": ""},
    ]
    s = summarise(results)
    assert s["total"] == 3 and s["passed"] == 2
    assert s["by_type"]["join"] == {"total": 2, "passed": 1}
    assert s["retried"] == 1
    assert s["answerable_total"] == 2 and s["answerable_passed"] == 1


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
