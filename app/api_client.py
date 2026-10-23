"""Thin HTTP client the Streamlit pages use. The UI never imports the pipeline directly."""
import os

import requests

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
TIMEOUT_S = 90  # embedding + generation + summary can take a while on the free tier


class ApiError(RuntimeError):
    pass


def _auth(token: str | None) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _check(resp: requests.Response) -> None:
    if resp.status_code == 401:
        raise ApiError("Wrong password, or your session expired. Sign in again.")
    if resp.status_code == 503:
        raise ApiError("The API has no role passwords set. Add APP_PASSWORD_CEO and the others to .env, then restart the API.")
    if resp.status_code >= 400:
        raise ApiError(f"The API returned {resp.status_code}: {resp.text[:300]}")


def ask(question: str, token: str | None = None) -> dict:
    try:
        resp = requests.post(f"{API_URL}/query", json={"question": question},
                             headers=_auth(token), timeout=TIMEOUT_S)
    except requests.RequestException as exc:
        raise ApiError(f"Could not reach the API at {API_URL}. Is uvicorn running? ({exc})") from exc
    _check(resp)
    return resp.json()


def check_password(token: str) -> dict:
    """Raises ApiError unless the password is accepted. Returns {'role': ..., 'label': ...}."""
    try:
        resp = requests.get(f"{API_URL}/whoami", headers=_auth(token), timeout=10)
    except requests.RequestException as exc:
        raise ApiError(f"Could not reach the API at {API_URL}. Is uvicorn running? ({exc})") from exc
    _check(resp)
    return resp.json()


def health() -> dict | None:
    try:
        resp = requests.get(f"{API_URL}/health", timeout=5)
        return resp.json() if resp.ok else None
    except (requests.RequestException, ValueError):
        return None


def schema(token: str | None = None) -> dict:
    try:
        resp = requests.get(f"{API_URL}/schema", headers=_auth(token), timeout=5)
    except requests.RequestException as exc:
        raise ApiError(f"Could not load the schema from {API_URL}. ({exc})") from exc
    _check(resp)
    try:
        return resp.json()
    except ValueError as exc:
        raise ApiError(f"Could not read the schema from {API_URL}. ({exc})") from exc
