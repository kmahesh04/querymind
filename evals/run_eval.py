"""Run the eval set against the live pipeline and write a report.

    python -m evals.run_eval                 # run every question not yet done
    python -m evals.run_eval --limit 5       # only the first 5 questions
    python -m evals.run_eval --reset         # forget saved progress and start again

Progress is saved after every question to evals/results/progress.json. If the free-tier quota runs out,
the run stops cleanly and the next run carries on from where it stopped.

Outputs (written when all questions are done):
    evals/results/results.json
    evals/results/report.md

AI summaries are switched off during the eval to save free-tier quota. The answer text is not scored.
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.harness import load_gold, render_report, score_case, summarise  # noqa: E402
from pipeline.engine import DB_PATH, answer_query  # noqa: E402
from pipeline.llm import USAGE, default_llm, gemini_available, gemini_embed, model_available, model_label  # noqa: E402

EVAL_SET = ROOT / "evals" / "eval_set.json"
RESULTS_DIR = ROOT / "evals" / "results"
PROGRESS = RESULTS_DIR / "progress.json"
PAUSE_S = 2.0  # gentle pacing for the free tier


def _load_progress() -> dict:
    if PROGRESS.exists():
        try:
            return json.loads(PROGRESS.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def _save_progress(done: dict) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(json.dumps(done, indent=2, default=str), encoding="utf-8")


def _is_quota_error(exc: Exception) -> bool:
    text = str(exc)
    return "429" in text or "RESOURCE_EXHAUSTED" in text or "quota" in text.lower()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    if not model_available():
        print("GROK_API_KEY or GEMINI_API_KEY must be set. Add one to .env, then run again.")
        return 1
    if args.reset and PROGRESS.exists():
        PROGRESS.unlink()

    cases = json.loads(EVAL_SET.read_text(encoding="utf-8"))
    if args.limit:
        cases = cases[: args.limit]

    done = _load_progress()
    todo = [c for c in cases if c["id"] not in done]
    print(f"{len(cases) - len(todo)} of {len(cases)} already done. Running {len(todo)}.")

    for case in todo:
        gold = load_gold(case, DB_PATH)
        try:
            answer = answer_query(case["question"], llm=default_llm,
                                  embed=gemini_embed if gemini_available() else None, explain_with_model=False)
        except Exception as exc:  # the eval must keep going past single failures
            if _is_quota_error(exc):
                _save_progress(done)
                print(f"\nFree-tier quota reached at {case['id']}. Saved progress. "
                      f"Run the same command again later to continue.")
                return 2
            from pipeline.engine import QueryAnswer
            answer = QueryAnswer(question=case["question"], status="failed", error=f"exception: {exc}")
        result = score_case(case, answer, gold)
        done[case["id"]] = result
        _save_progress(done)
        mark = "PASS" if result["passed"] else "FAIL"
        print(f"{mark} {case['id']} {case['type']:<13} {result['reason']}")
        time.sleep(PAUSE_S)

    results = [done[c["id"]] for c in cases]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "results.json").write_text(
        json.dumps({"summary": summarise(results), "results": results}, indent=2, default=str),
        encoding="utf-8",
    )
    label = (datetime.now().strftime("%Y-%m-%d %H:%M")
             + f" ({len(cases)} questions, models: {model_label()}; calls answered by Gemini {USAGE['gemini']}, "
             + f"Grok {USAGE['grok']}, fallback {USAGE['fallback']})")
    (RESULTS_DIR / "report.md").write_text(render_report(results, label), encoding="utf-8")

    s = summarise(results)
    print(f"\n{s['passed']}/{s['total']} passed ({s['accuracy']:.0%}). Report: {RESULTS_DIR / 'report.md'}")
    print(f"Calls answered by Gemini: {USAGE['gemini']}, by Grok: {USAGE['grok']}, by fallback: {USAGE['fallback']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
