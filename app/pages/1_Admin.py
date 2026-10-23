"""QueryMind admin page: query log, example bank, schema, and service health.

Reads the query log and example bank directly from disk (this is a local admin page).
"""
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.api_client import ApiError, health, schema  # noqa: E402
from pipeline.examples import EXAMPLES_FILE, load_examples  # noqa: E402

LOG_FILE = ROOT / "data" / "query_log.jsonl"

st.set_page_config(page_title="QueryMind admin", page_icon="🛠️", layout="wide")

# The query log holds every role's questions and results, so only the CEO role may open this page.
if not st.session_state.get("authed"):
    st.warning("Sign in on the main QueryMind page first, then come back to Admin.")
    st.stop()
if st.session_state.get("role") != "ceo":
    st.warning("The admin page is for the CEO role only.")
    st.stop()

st.title("Admin")

tab_logs, tab_examples, tab_schema, tab_health = st.tabs(["Query log", "Example bank", "Schema", "Health"])


def load_log() -> pd.DataFrame:
    if not LOG_FILE.exists():
        return pd.DataFrame()
    rows = []
    for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return pd.DataFrame(rows)


with tab_logs:
    log = load_log()
    if log.empty:
        st.info("No queries logged yet. Ask a question on the main page first.")
    else:
        total = len(log)
        answered = int((log["status"] == "answered").sum())
        refused = int((log["status"] == "refused").sum())
        failed = int((log["status"] == "failed").sum())
        model_summaries = int((log.get("summary_source") == "model").sum())
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Queries", total)
        c2.metric("Answered", answered)
        c3.metric("Refused (blocked)", refused)
        c4.metric("Failed", failed)
        c5.metric("AI summaries", model_summaries)

        left, right = st.columns(2)
        with left:
            st.subheader("Status")
            st.bar_chart(log["status"].value_counts())
        with right:
            st.subheader("Retriever used")
            if "retriever" in log:
                st.bar_chart(log["retriever"].replace("", "none").value_counts())

        st.subheader("Recent queries")
        cols = [c for c in ["at", "question", "status", "route", "attempts", "elapsed_ms", "error"] if c in log]
        st.dataframe(log[cols].iloc[::-1], use_container_width=True, hide_index=True)

        with st.expander("Refused and failed queries"):
            problems = log[log["status"].isin(["refused", "failed"])]
            st.dataframe(problems[[c for c in ["question", "status", "route", "error"] if c in problems]],
                         use_container_width=True, hide_index=True)

with tab_examples:
    examples = load_examples()
    st.write(f"{len(examples)} examples in `{EXAMPLES_FILE.relative_to(ROOT)}`. Used as few-shot context for SQL generation.")
    st.dataframe(pd.DataFrame(examples), use_container_width=True, hide_index=True)

with tab_schema:
    try:
        tables = schema(st.session_state.get("token"))
    except ApiError as exc:
        st.error(str(exc))
        tables = {}
    for name, info in tables.items():
        with st.expander(f"{name}: {info['description']}"):
            st.table(pd.DataFrame(
                [{"column": c, "meaning": m} for c, m in info["columns"].items()]
            ))

with tab_health:
    status = health()
    if status is None:
        st.error("The API is not reachable.")
    else:
        st.success("API is up.")
        st.write(f"Database: `{status['database']}`")
        st.write(f"Model key set: **{status['model_key_set']}**")
