"""Model adapters. The only file that talks to Grok (xAI) and Google (Gemini).

Interfaces used everywhere else:
  llm(system: str, prompt: str, json_mode: bool) -> str      # default_llm below
  embed(texts: list[str], task_type: str) -> list[list[float]]  # gemini_embed

Text generation:
  default_llm uses the provider named in LLM_PROVIDER ("gemini" by default, or "grok").
  If that call fails (quota, network, bad key), it retries the same call on the other provider,
  when its key is set. Set GEMINI_MODEL or GROK_MODEL to choose a model.

Embeddings:
  Grok has no embedding model used here, so example retrieval still uses Gemini
  (gemini-embedding-001). Without a Gemini key, retrieval falls back to TF-IDF.

Rate-limit (429) errors are retried with backoff.
"""
import os
import time

import requests

GROK_BASE_URL = os.getenv("GROK_BASE_URL", "https://api.x.ai/v1").rstrip("/")
DEFAULT_GROK_MODEL = "grok-4"  # check the exact name in the xAI Console; override with GROK_MODEL
DEFAULT_MODEL = "gemini-3.8-flash"  # gemini-2.5-flash is closed to new users
DEFAULT_EMBED_MODEL = "gemini-embedding-001"

# How many calls each provider answered in this process. The eval prints these so the report is honest.
USAGE = {"gemini": 0, "grok": 0, "fallback": 0}


def grok_available() -> bool:
    return bool(os.getenv("GROK_API_KEY"))


def gemini_available() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


def model_available() -> bool:
    return grok_available() or gemini_available()


def model_label() -> str:
    """Short description of the text models in use, for reports."""
    grok = os.getenv("GROK_MODEL", DEFAULT_GROK_MODEL)
    gem = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    names = {"gemini": gem, "grok": grok}
    primary = _primary()
    ordered = [p for p in (primary, "grok" if primary == "gemini" else "gemini") if _has_key(p)]
    if not ordered:
        return "none"
    if len(ordered) == 1:
        return names[ordered[0]]
    return f"{names[ordered[0]]} with {names[ordered[1]]} fallback"


def _primary() -> str:
    return os.getenv("LLM_PROVIDER", "gemini").strip().lower()


def _has_key(provider: str) -> bool:
    return grok_available() if provider == "grok" else gemini_available()


def _with_retry(call):
    delays = [2, 5, 10]
    for attempt in range(len(delays) + 1):
        try:
            return call()
        except Exception as exc:  # requests and google.genai both raise on errors
            rate_limited = "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)
            if not rate_limited or attempt == len(delays):
                raise
            time.sleep(delays[attempt])


# ---- Grok (xAI) -------------------------------------------------------------

def grok_llm(system: str, prompt: str, json_mode: bool = True) -> str:
    """Chat completion on xAI's OpenAI-compatible endpoint. Temperature 0 for repeatable SQL."""
    key = os.getenv("GROK_API_KEY")
    if not key:
        raise RuntimeError("GROK_API_KEY is not set")
    payload = {
        "model": os.getenv("GROK_MODEL", DEFAULT_GROK_MODEL),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    def call() -> str:
        resp = requests.post(
            f"{GROK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        if resp.status_code == 429:
            raise RuntimeError("Grok 429: rate limit or quota reached")
        if resp.status_code >= 400:
            raise RuntimeError(f"Grok error {resp.status_code}: {resp.text[:200]}")
        return resp.json()["choices"][0]["message"]["content"] or ""

    return _with_retry(call)


# ---- Gemini (Google) --------------------------------------------------------

def _gemini_client():
    from google import genai  # imported lazily so tests run without the package
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def gemini_llm(system: str, prompt: str, json_mode: bool = True) -> str:
    from google.genai import types

    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=0,
        response_mime_type="application/json" if json_mode else "text/plain",
    )
    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    client = _gemini_client()
    response = _with_retry(lambda: client.models.generate_content(model=model, contents=prompt, config=config))
    return response.text or ""


# ---- Default text model: Grok first, Gemini as fallback ---------------------

def default_llm(system: str, prompt: str, json_mode: bool = True) -> str:
    """Primary provider from LLM_PROVIDER; the other provider is tried only if the primary fails."""
    _CALLS = {"gemini": gemini_llm, "grok": grok_llm}
    primary = _primary()
    other = "grok" if primary == "gemini" else "gemini"
    if not _has_key(primary) and not _has_key(other):
        raise RuntimeError("No model key is set. Add GEMINI_API_KEY or GROK_API_KEY to .env.")
    if not _has_key(primary):
        USAGE[other] += 1
        return _CALLS[other](system, prompt, json_mode)
    try:
        text = _CALLS[primary](system, prompt, json_mode)
        USAGE[primary] += 1
        return text
    except Exception as first_exc:
        if not _has_key(other):
            raise
        USAGE["fallback"] += 1
        try:
            return _CALLS[other](system, prompt, json_mode)
        except Exception as second_exc:
            # Show both reasons, so one provider's problem is not hidden behind the other's.
            raise RuntimeError(
                f"{primary} failed ({first_exc}); the {other} fallback also failed ({second_exc})."
            ) from second_exc


# ---- Embeddings (Gemini) ----------------------------------------------------

def gemini_embed(texts: list[str], task_type: str = "RETRIEVAL_QUERY") -> list[list[float]]:
    from google.genai import types

    model = os.getenv("GEMINI_EMBED_MODEL", DEFAULT_EMBED_MODEL)
    client = _gemini_client()
    config = types.EmbedContentConfig(task_type=task_type)
    response = _with_retry(lambda: client.models.embed_content(model=model, contents=texts, config=config))
    return [e.values for e in response.embeddings]


# The retriever caches example vectors on disk only for the real Gemini embedder,
# so test fakes can never overwrite real cached vectors.
gemini_embed.cacheable = True
gemini_embed.model_tag = os.getenv("GEMINI_EMBED_MODEL", DEFAULT_EMBED_MODEL)
