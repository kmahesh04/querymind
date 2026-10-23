"""Step 3: find the few-shot examples most similar to the question.

Primary: vector search. Each example question is embedded once (Gemini embeddings, free tier),
the embeddings are cached on disk, and each new question costs one embedding call.

Fallback: TF-IDF cosine similarity, used when no key is set or the embedding call fails.
"""
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_FILE = ROOT / "data" / "examples.json"
EMBED_CACHE = ROOT / "data" / "examples_embeddings.json"

# embed(texts, task_type) -> one vector per text
EmbedFn = Callable[[list[str], str], list[list[float]]]


def load_examples(path: Path = EXAMPLES_FILE) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class VectorRetriever:
    kind = "vector"

    def __init__(self, examples: list[dict], embed: EmbedFn, cache_path: Path | None = None,
                 model_tag: str = ""):
        self.examples = examples
        self.embed = embed
        self.vectors = self._load_or_build(cache_path, model_tag)

    def _load_or_build(self, cache_path: Path | None, model_tag: str) -> list[list[float]]:
        questions = [e["question"] for e in self.examples]
        key = hashlib.sha256((model_tag + "\n" + "\n".join(questions)).encode("utf-8")).hexdigest()
        if cache_path is not None and cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                if cached.get("key") == key and len(cached.get("vectors", [])) == len(questions):
                    return cached["vectors"]
            except (OSError, ValueError):
                pass  # unreadable cache: rebuild it
        vectors = self.embed(questions, "RETRIEVAL_DOCUMENT")
        if cache_path is not None:
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps({"key": key, "vectors": vectors}), encoding="utf-8")
            except OSError:
                pass  # caching is an optimisation only
        return vectors

    def top(self, question: str, k: int = 4) -> list[dict]:
        query_vec = self.embed([question], "RETRIEVAL_QUERY")[0]
        scored = sorted(
            ((_cosine(query_vec, vec), i) for i, vec in enumerate(self.vectors)),
            key=lambda x: (-x[0], x[1]),
        )
        return [self.examples[i] for _, i in scored[:k]]


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class TfidfRetriever:
    kind = "tfidf"

    def __init__(self, examples: list[dict]):
        self.examples = examples
        docs = [Counter(_tokens(e["question"])) for e in examples]
        n = len(docs)
        df: Counter = Counter()
        for d in docs:
            df.update(d.keys())
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
        self.vectors = [self._vec(d) for d in docs]

    def _vec(self, counts: Counter) -> dict[str, float]:
        vec = {t: c * self.idf.get(t, 1.0) for t, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def top(self, question: str, k: int = 4) -> list[dict]:
        q = self._vec(Counter(_tokens(question)))
        scored = []
        for i, vec in enumerate(self.vectors):
            score = sum(w * vec.get(t, 0.0) for t, w in q.items())
            scored.append((score, i))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [self.examples[i] for score, i in scored[:k] if score > 0]


def build_retriever(examples: list[dict], embed: EmbedFn | None,
                    cache_path: Path | None = None, model_tag: str = ""):
    """Vector retriever if an embed function is given and works; otherwise TF-IDF."""
    if embed is None:
        return TfidfRetriever(examples)
    try:
        return VectorRetriever(examples, embed, cache_path=cache_path, model_tag=model_tag)
    except Exception:
        return TfidfRetriever(examples)
