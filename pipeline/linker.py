"""Step 2: pick the tables the SQL needs, so the prompt stays small and focused.

Keyword match on the question, then one hop of foreign-key neighbours so joins are possible.
"""
import re

from pipeline.schema_info import FOREIGN_KEYS, TABLES

FALLBACK = ["orders", "customers", "products"]


def link(question: str) -> list[str]:
    words = set(re.findall(r"[a-z]+", question.lower()))
    chosen = {t for t, info in TABLES.items() if words & info["keywords"]}
    if not chosen:
        chosen = set(FALLBACK)

    expanded = set(chosen)
    for child, parent in FOREIGN_KEYS:
        if child in chosen:
            expanded.add(parent)
        if parent in chosen:
            expanded.add(child)
    return sorted(expanded)
