"""Step 1: route each question to data_query, out_of_scope or unsafe.

Two layers, in order:
  1. Rules (deterministic): write verbs are blocked before any model is called.
  2. Model label (optional): a short Gemini call decides data question vs off-topic.
If no model is available, anything that passes the rules is treated as a data question.
The SQL validator is the final safety net either way.
"""
import re
from dataclasses import dataclass

from pipeline.util import parse_json

WRITE_WORDS = re.compile(
    r"\b(delete|drop|truncate|insert|alter|remove|erase|modify|grant|vacuum|attach)\b", re.IGNORECASE
)

LABEL_SYSTEM = (
    "You classify messages for an e-commerce analytics assistant. The assistant can only answer questions "
    "about orders, customers, products, shipments, payments, returns, reviews and categories in its database."
)
LABEL_PROMPT = (
    'Classify the user message as one label:\n'
    '- "data_query": a question the database can answer.\n'
    '- "out_of_scope": anything else (small talk, general knowledge, writing or coding tasks).\n'
    'Reply with JSON only: {"label": "data_query" or "out_of_scope", "reason": "one short sentence"}'
)


@dataclass
class Route:
    label: str  # data_query | out_of_scope | unsafe
    reason: str


def classify(question: str, llm=None) -> Route:
    if WRITE_WORDS.search(question):
        return Route("unsafe", "The request asks to change data. This assistant is read-only.")
    if llm is None:
        return Route("data_query", "No model available: rules only.")
    data = parse_json(llm(LABEL_SYSTEM, f"{LABEL_PROMPT}\n\nMessage: {question}", True))
    label = data.get("label")
    if label == "out_of_scope":
        return Route("out_of_scope", str(data.get("reason", "")))
    # Anything else, including an unclear reply, goes to SQL generation. The validator is the backstop.
    return Route("data_query", str(data.get("reason", "")))
