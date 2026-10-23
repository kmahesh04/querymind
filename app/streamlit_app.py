"""QueryMind query page. Run from the querymind folder:

    streamlit run app/streamlit_app.py

Needs the API running:  uvicorn api.main:app --reload
The page only talks to the API over HTTP (app/api_client.py).
"""
import html
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api_client import ApiError, ask, check_password, health, schema  # noqa: E402

SAMPLES = [
    "How many orders were shipped to Austin?",
    "Revenue by product category",
    "Which 5 products sold the most units?",
    "Average delivery time in days for each carrier",
    "Which customers have never placed an order?",
]
NAV = ["Generate SQL", "How it works"]

st.set_page_config(page_title="QueryMind", page_icon="🔎", layout="wide")

st.markdown(
    """
<style>
  .stApp { background: linear-gradient(180deg, #15112F 0%, #241A56 60%, #33206E 100%); color: #EDE9FE; }
  [data-testid="stSidebar"] { background: #18143B; border-right: 1px solid #3F348C; }
  [data-testid="stHeader"] { background: transparent; }
  .qm-logo { font-size: 1.6rem; font-weight: 800; letter-spacing: 0.01em; color: #FFFFFF; }
  .qm-logo span { color: #E879F9; }
  .qm-muted { color: #C4BDEB; font-size: 0.9rem; }
  [data-testid="stCaptionContainer"], [data-testid="stSidebar"] label, [data-testid="stSidebar"] p { color: #D5D7EA !important; }
  [data-testid="stSidebar"] [role="radiogroup"] label p { color: #F1F1F7 !important; }
  textarea { background: #1C1A44 !important; color: #EDE9FE !important; border: 1px solid #5A4BC9 !important; }
  div.stButton > button[kind="primary"] {
    background: linear-gradient(90deg, #7C3AED, #A855F7); color: #FFFFFF; border: none; font-weight: 600; width: 100%;
  }
  div.stButton > button[kind="primary"]:hover { filter: brightness(1.08); color: #FFFFFF; }
  div.stButton > button[kind="secondary"] { background: #1E1B4B; color: #EDE9FE; border: 1px solid #5A4BC9; }
  .qm-sql-title { font-size: 1.05rem; font-weight: 600; margin-top: 1.2rem; color: #FACC15; }
  .qm-sql-card { background: #FFFFFF; border-radius: 14px; padding: 14px;
    box-shadow: 0 4px 18px rgba(0, 0, 0, 0.35); margin-bottom: 0.8rem; }
  .qm-sql-code { background: #151238; color: #EDE9FE; border-radius: 10px; padding: 14px 16px;
    font-family: "Courier New", Consolas, monospace; font-size: 0.95rem; white-space: pre-wrap; }
  .qm-table-wrap { overflow-x: auto; border-radius: 10px; border: 1px solid #3F348C; margin: 0.5rem 0 1rem; }
  .qm-table { width: 100%; border-collapse: collapse; background: #FFFFFF; color: #151238; font-size: 0.92rem; }
  .qm-table th { background: #EDE9FE; color: #151238; text-align: left; padding: 8px 12px; font-weight: 700; }
  .qm-table td { padding: 7px 12px; border-top: 1px solid #DDD6FE; color: #151238; }
</style>
""",
    unsafe_allow_html=True,
)


def _login_gate() -> None:
    """Shows a password form until the API accepts the shared password. Stops the page otherwise."""
    if st.session_state.get("authed"):
        return
    st.markdown("## Sign in")
    st.markdown('<div class="qm-muted">Enter the shared password to ask questions.</div>', unsafe_allow_html=True)
    with st.form("login_form"):
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        try:
            info = check_password(password)
        except ApiError as exc:
            st.error(str(exc))
        else:
            st.session_state.authed = True
            st.session_state.token = password
            st.session_state.role = info["role"]
            st.session_state.role_label = info["label"]
            st.rerun()
    st.stop()


def _sign_out() -> None:
    st.session_state.authed = False
    st.session_state.token = None
    st.session_state.role = None
    st.session_state.role_label = None
    st.session_state.pop("last", None)


def _use_sample(text: str) -> None:
    st.session_state["question_box"] = text


def _run_question(question: str) -> None:
    with st.spinner("Writing SQL, running it and explaining the result..."):
        try:
            st.session_state["last"] = ask(question, st.session_state.get("token"))
        except ApiError as exc:
            st.session_state["last"] = None
            st.error(str(exc))


def _schema_panel(tables: list[str]) -> None:
    try:
        data = schema(st.session_state.get("token"))
    except ApiError as exc:
        st.warning(str(exc))
        return
    for name in tables:
        info = data.get(name)
        if not info:
            continue
        st.markdown(f"**{name}**: {info['description']}")
        cols = pd.DataFrame(
            [{"column": c, "meaning": d} for c, d in info["columns"].items()]
        )
        st.dataframe(cols, use_container_width=True, hide_index=True)


def _result_table(columns: list[str], rows: list[list]) -> str:
    """Plain HTML table with explicit colours, so cell text is readable on the dark theme."""
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape('' if v is None else str(v))}</td>" for v in row) + "</tr>"
        for row in rows
    )
    return (
        f'<div class="qm-table-wrap"><table class="qm-table">'
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def _render_result(answer: dict, show_schema: bool) -> None:
    st.markdown('<div class="qm-sql-title">Your AI-generated SQL query</div>', unsafe_allow_html=True)
    if answer.get("sql"):
        st.markdown(
            f'<div class="qm-sql-card"><div class="qm-sql-code">{html.escape(answer["sql"])}</div></div>',
            unsafe_allow_html=True,
        )

    if answer["status"] == "refused":
        st.info(answer["summary"])
        return
    if answer["status"] == "failed":
        st.error(answer.get("error") or "The question could not be answered.")
        return

    badge = "AI summary" if answer["summary_source"] == "model" else "Template summary"
    st.success(f"{answer['summary']}  \n\n*{badge}*")
    if answer["rows"]:
        st.markdown(_result_table(answer["columns"], answer["rows"]), unsafe_allow_html=True)
        if answer["truncated"]:
            st.caption("Showing the first 100 rows.")
    if answer.get("assumption"):
        st.caption(f"Assumption: {answer['assumption']}")

    if show_schema:
        st.markdown("#### Database schema used")
        _schema_panel(answer["linked_tables"])

    with st.expander("Details"):
        st.write(
            f"Tables: {', '.join(answer['linked_tables'])}  \n"
            f"Retriever: {answer['retriever']}  \n"
            f"Attempts: {answer['attempts']}  \n"
            f"Time: {answer['elapsed_ms']} ms"
        )
        if answer.get("examples_used"):
            st.write("Similar examples used:")
            for q in answer["examples_used"]:
                st.write(f"- {q}")


def _generate_view() -> None:
    st.markdown("## Generate SQL")
    st.markdown(
        '<div class="qm-muted">Describe the data you want. QueryMind writes the SQL, checks it, '
        "runs it read-only and explains the result.</div>",
        unsafe_allow_html=True,
    )
    st.write("")

    with st.container(border=True):
        show_schema = st.toggle("Add database schema", key="show_schema")
        st.markdown("**Write here what you want:**")
        st.text_area(
            "Question",
            key="question_box",
            height=110,
            placeholder="e.g. Revenue in September 2026, or How many orders were shipped to Austin?",
            label_visibility="collapsed",
        )
        generate = st.button("Generate SQL", type="primary", key="generate")

    if generate:
        question = st.session_state.get("question_box", "").strip()
        if len(question) < 3:
            st.warning("Write a question of at least three characters.")
        else:
            _run_question(question)

    answer = st.session_state.get("last")
    if answer:
        _render_result(answer, show_schema)


def _how_view() -> None:
    st.markdown("## How it works")
    st.markdown(
        """
1. **Classify.** Write requests (delete, drop, update) are refused before any model is called.
2. **Link the schema.** Keywords pick the tables, plus their foreign-key neighbours.
3. **Retrieve examples.** The 4 most similar question-SQL pairs are found by vector search.
4. **Generate SQL.** Gemini writes one SELECT. If Gemini fails, Grok writes it instead, when a Grok key is set.
5. **Validate.** One SELECT or WITH only, known tables only, SQLite planner check, row cap.
6. **Execute read-only.** The database connection cannot write, with a 3-second timeout.
7. **Explain.** A sentence and the table, with any assumption stated.
"""
    )


_login_gate()

with st.sidebar:
    st.markdown('<div class="qm-logo">Query<span>Mind</span></div>', unsafe_allow_html=True)
    st.caption("Plain English to SQL, read-only.")
    st.caption(f"Signed in as: {st.session_state.get('role_label') or 'unknown'}")
    st.button("Sign out", key="signout", on_click=_sign_out)
    view = st.radio("Navigate", NAV, label_visibility="collapsed")
    st.divider()
    st.markdown('<div class="qm-muted">Try a question</div>', unsafe_allow_html=True)
    for sample in SAMPLES:
        st.button(
            sample,
            key=f"sample_{sample}",
            use_container_width=True,
            on_click=_use_sample,
            args=(sample,),
        )

status = health()
if status is None:
    st.error("The API is not reachable. Start it with: uvicorn api.main:app --reload")
elif not status.get("model_key_set"):
    st.warning("No GROK_API_KEY or GEMINI_API_KEY is set on the API. Questions cannot be answered until one is.")

if view == "Generate SQL":
    _generate_view()
else:
    _how_view()
