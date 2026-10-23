"""Scoring for the QueryMind eval set.

Answerable questions pass when the generated SQL returns the same rows as the gold SQL.
Rows are compared as a multiset (order ignored) after rounding floats to 2 dp, so two correct
queries written differently both pass. Column names are not compared; column count is.

Refused questions (unsafe, out_of_scope) pass when the pipeline refuses with the expected route.
"""
from collections import defaultdict
from pathlib import Path

from pipeline.execute import QueryResult, run_readonly


def _normalise(rows: list[list]) -> list[tuple]:
    out = []
    for row in rows:
        out.append(tuple(round(v, 2) if isinstance(v, float) else v for v in row))
    return sorted(out, key=lambda t: tuple(str(v) for v in t))


def results_match(gold: QueryResult, predicted_columns: list[str], predicted_rows: list[list]) -> tuple[bool, str]:
    if gold.rows and predicted_rows and len(gold.rows[0]) != len(predicted_rows[0]):
        return False, f"column count {len(predicted_rows[0])} != expected {len(gold.rows[0])}"
    if len(gold.rows) != len(predicted_rows):
        return False, f"row count {len(predicted_rows)} != expected {len(gold.rows)}"
    if _normalise(gold.rows) != _normalise(predicted_rows):
        return False, "rows differ from the expected result"
    return True, "rows match"


def load_gold(case: dict, db_path: Path) -> QueryResult | None:
    if not case.get("gold_sql"):
        return None
    return run_readonly(case["gold_sql"], db_path)


def score_case(case: dict, answer, gold: QueryResult | None) -> dict:
    base = {
        "id": case["id"],
        "type": case["type"],
        "question": case["question"],
        "expect": case["expect"],
        "status": answer.status,
        "route": answer.route,
        "generated_sql": answer.sql,
        "gold_sql": case.get("gold_sql"),
        "retriever": answer.retriever,
        "attempts": answer.attempts,
        "elapsed_ms": answer.elapsed_ms,
        "error": answer.error,
    }
    if case["expect"] == "refused":
        passed = answer.status == "refused" and answer.route == case["expect_route"]
        reason = "refused as expected" if passed else (
            f"expected refusal ({case['expect_route']}), got {answer.status}/{answer.route}")
        return {**base, "passed": passed, "reason": reason}

    if answer.status != "answered":
        return {**base, "passed": False, "reason": f"not answered: {answer.error or answer.status}"}
    if gold is None:
        return {**base, "passed": False, "reason": "case has no gold SQL"}
    passed, reason = results_match(gold, answer.columns, answer.rows)
    return {**base, "passed": passed, "reason": reason}


def summarise(results: list[dict]) -> dict:
    by_type: dict[str, dict] = defaultdict(lambda: {"total": 0, "passed": 0})
    for r in results:
        by_type[r["type"]]["total"] += 1
        by_type[r["type"]]["passed"] += int(r["passed"])
    total = len(results)
    passed = sum(int(r["passed"]) for r in results)
    answered = [r for r in results if r["expect"] == "answered"]
    latencies = sorted(r["elapsed_ms"] for r in results) or [0]
    return {
        "total": total,
        "passed": passed,
        "accuracy": passed / total if total else 0.0,
        "answerable_total": len(answered),
        "answerable_passed": sum(int(r["passed"]) for r in answered),
        "retried": sum(1 for r in results if r["attempts"] > 1),
        "by_type": dict(sorted(by_type.items())),
        "median_ms": latencies[len(latencies) // 2],
        "max_ms": latencies[-1],
        "retrievers": {k: sum(1 for r in results if r["retriever"] == k) for k in {r["retriever"] for r in results}},
    }


def render_report(results: list[dict], run_label: str) -> str:
    s = summarise(results)
    lines = [
        f"# QueryMind eval report",
        "",
        f"Run: {run_label}",
        "",
        f"**Overall: {s['passed']} / {s['total']} passed ({s['accuracy']:.0%})**",
        f"Answerable questions: {s['answerable_passed']} / {s['answerable_total']}. "
        f"Refusals correct: {s['passed'] - s['answerable_passed']} / {s['total'] - s['answerable_total']}.",
        f"Queries that needed a retry: {s['retried']}. Median time {s['median_ms']} ms, slowest {s['max_ms']} ms.",
        f"Retrievers used: {', '.join(f'{k} ({v})' for k, v in s['retrievers'].items())}.",
        "",
        "## Results by query type",
        "",
        "| Type | Passed | Total | Accuracy |",
        "|---|---|---|---|",
    ]
    for t, v in s["by_type"].items():
        lines.append(f"| {t} | {v['passed']} | {v['total']} | {v['passed'] / v['total']:.0%} |")

    lines += ["", "## Each question", "", "| ID | Type | Result | Question | Why |", "|---|---|---|---|---|"]
    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        lines.append(f"| {r['id']} | {r['type']} | {mark} | {r['question']} | {r['reason']} |")

    failures = [r for r in results if not r["passed"]]
    if failures:
        lines += ["", "## Failures in detail", ""]
        for r in failures:
            lines += [
                f"### {r['id']}: {r['question']}",
                f"- Reason: {r['reason']}",
                f"- Expected SQL: `{r['gold_sql']}`" if r["gold_sql"] else "- Expected: refusal",
                f"- Generated SQL: `{r['generated_sql']}`" if r["generated_sql"] else "- Generated SQL: none",
                "",
            ]
    return "\n".join(lines) + "\n"
