"""Checks that text generation picks the primary provider and falls back to the other. Offline: no network calls.

Run: python3 tests/test_llm_routing.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import llm  # noqa: E402


class _Env:
    """Set environment variables for one test and restore them after. None removes a variable."""

    def __init__(self, **values):
        self.values = values
        self.saved = {}

    def __enter__(self):
        for k, v in self.values.items():
            self.saved[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _patched(grok, gemini):
    """Replace both provider calls with fakes; return a restore function."""
    original = (llm.grok_llm, llm.gemini_llm)
    llm.grok_llm, llm.gemini_llm = grok, gemini

    def restore():
        llm.grok_llm, llm.gemini_llm = original
    return restore


def _ok(name, calls):
    def call(s, p, j):
        calls.append(name)
        return "{}"
    return call


def _broken(message):
    def call(s, p, j):
        raise RuntimeError(message)
    return call


def test_gemini_is_the_default_and_grok_is_not_called():
    calls = []
    restore = _patched(_ok("grok", calls), _ok("gemini", calls))
    try:
        with _Env(LLM_PROVIDER=None, GROK_API_KEY="k", GEMINI_API_KEY="g"):
            before = llm.USAGE["gemini"]
            assert llm.default_llm("sys", "prompt", True) == "{}"
            assert calls == ["gemini"]
            assert llm.USAGE["gemini"] == before + 1
    finally:
        restore()


def test_grok_is_used_when_it_is_the_primary():
    calls = []
    restore = _patched(_ok("grok", calls), _ok("gemini", calls))
    try:
        with _Env(LLM_PROVIDER="grok", GROK_API_KEY="k", GEMINI_API_KEY="g"):
            llm.default_llm("sys", "prompt", True)
            assert calls == ["grok"]
    finally:
        restore()


def test_grok_takes_over_when_gemini_fails():
    calls = []
    restore = _patched(_ok("grok", calls), _broken("Gemini 404 NOT_FOUND"))
    try:
        with _Env(LLM_PROVIDER=None, GROK_API_KEY="k", GEMINI_API_KEY="g"):
            before = llm.USAGE["fallback"]
            assert llm.default_llm("sys", "prompt", True) == "{}"
            assert calls == ["grok"]
            assert llm.USAGE["fallback"] == before + 1
    finally:
        restore()


def test_both_failure_messages_are_shown():
    restore = _patched(_broken("Grok error 401"), _broken("Gemini 404 NOT_FOUND"))
    try:
        with _Env(LLM_PROVIDER=None, GROK_API_KEY="k", GEMINI_API_KEY="g"):
            try:
                llm.default_llm("sys", "prompt", True)
            except RuntimeError as exc:
                assert "404" in str(exc) and "401" in str(exc), str(exc)
            else:
                raise AssertionError("expected an error when both providers fail")
    finally:
        restore()


def test_only_grok_key_uses_grok():
    calls = []
    restore = _patched(_ok("grok", calls), _ok("gemini", calls))
    try:
        with _Env(LLM_PROVIDER=None, GROK_API_KEY="k", GEMINI_API_KEY=None):
            llm.default_llm("sys", "prompt", True)
            assert calls == ["grok"]
    finally:
        restore()


def test_no_keys_fails_clearly():
    with _Env(LLM_PROVIDER=None, GROK_API_KEY=None, GEMINI_API_KEY=None):
        assert not llm.model_available()
        try:
            llm.default_llm("sys", "prompt", True)
        except RuntimeError as exc:
            assert "API_KEY" in str(exc)
        else:
            raise AssertionError("expected an error with no keys")


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
