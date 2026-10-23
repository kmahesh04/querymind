"""Step 7: explain the result in plain English.

Two ways, both always produce text:
  - template_summary: built from the rows and the assumption. Free, deterministic, never wrong about numbers.
  - model_summary: a Gemini sentence or two. Used only if every number in it appears in the result rows.
    If any number is not in the rows, it is discarded and the template is used instead.
"""
import re

from pipeline.execute import QueryResult

NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
SUMMARY_SYSTEM = (
    "You explain database query results to a store manager in one or two plain sentences. "
    "Use ONLY numbers that appear in the rows given. Do not mention SQL, tables or columns by their code names."
)


def _fmt(value) -> str:
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def template_summary(result: QueryResult, assumption: str = "") -> str:
    if not result.rows:
        text = "No matching records were found."
    elif len(result.columns) == 1 and len(result.rows) == 1:
        text = f"The answer is {_fmt(result.rows[0][0])}."
    elif len(result.rows) == 1:
        pairs = ", ".join(f"{c.replace('_', ' ')} {_fmt(v)}" for c, v in zip(result.columns, result.rows[0]))
        text = f"Found one row: {pairs}."
    else:
        text = f"Found {len(result.rows):,} rows."
        if result.truncated:
            text = f"Found more than {len(result.rows):,} rows; showing the first {len(result.rows):,}."
    if assumption:
        text += f" Assumption: {assumption}"
    return text


def _rows_as_text(result: QueryResult, max_rows: int = 20) -> str:
    lines = [", ".join(result.columns)]
    for row in result.rows[:max_rows]:
        lines.append(", ".join(_fmt(v) for v in row))
    return "\n".join(lines)


def _numbers_in(text: str) -> list[float]:
    out = []
    for token in NUMBER.findall(text):
        try:
            out.append(float(token.replace(",", "")))
        except ValueError:
            pass
    return out


def numbers_grounded(summary: str, result: QueryResult) -> bool:
    """True only if every number in the summary matches a number in the rows (within rounding)."""
    allowed = _numbers_in(_rows_as_text(result, max_rows=len(result.rows)))
    for n in _numbers_in(summary):
        if not any(abs(n - a) <= max(0.01, 0.005 * abs(a)) for a in allowed):
            return False
    return True


def model_summary(question: str, result: QueryResult, llm) -> str | None:
    if not result.rows:
        return None
    prompt = f"Question: {question}\n\nRows:\n{_rows_as_text(result)}\n\nAnswer in one or two sentences."
    text = (llm(SUMMARY_SYSTEM, prompt, False) or "").strip()
    if not text or len(text) > 600:
        return None
    return text if numbers_grounded(text, result) else None
