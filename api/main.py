"""HTTP API for QueryMind. Run with: uvicorn api.main:app --reload

Routes:
  GET  /health   liveness check (no login)
  GET  /whoami   the role for the password you send
  POST /query    question in, answer + SQL + rows out (role-limited)
  GET  /schema   the tables this role may read (for the schema view and the admin page)

Every route except /health needs 'Authorization: Bearer <password>'. Each role has its own password:
APP_PASSWORD_CEO, APP_PASSWORD_MANAGER and APP_PASSWORD_BA in .env.
"""
import hmac
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from pipeline.access import ROLES, allowed_tables, mask_pii
from pipeline.engine import DB_PATH, answer_query
from pipeline.llm import default_llm, gemini_available, gemini_embed, model_available
from pipeline.privacy import mask_answer
from pipeline.schema_info import TABLES

ROOT = Path(__file__).resolve().parents[1]
LOG_FILE = Path(os.getenv("QUERY_LOG", ROOT / "data" / "query_log.jsonl"))
ROLE_PASSWORDS = {role: os.getenv(f"APP_PASSWORD_{role.upper()}", "") for role in ROLES}

app = FastAPI(title="QueryMind API", version="0.2.0")


def current_role(authorization: str | None = Header(default=None)) -> str:
    """Returns the role that owns the password sent in the Authorization header."""
    if not any(ROLE_PASSWORDS.values()):
        raise HTTPException(status_code=503, detail="No role passwords are set on the API. Add them to .env.")
    token = (authorization or "").removeprefix("Bearer ").strip().encode("utf-8")
    matched = None
    for role, password in ROLE_PASSWORDS.items():
        # Compare every password, so timing does not reveal which one is closest.
        if password and hmac.compare_digest(token, password.encode("utf-8")):
            matched = role
    if matched is None:
        raise HTTPException(status_code=401, detail="Wrong or missing password.")
    return matched


class QueryIn(BaseModel):
    question: str = Field(min_length=3, max_length=300)


def _log(answer_dict: dict) -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        entry = {"at": datetime.now(timezone.utc).isoformat(), **answer_dict}
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass  # logging must never break a query


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "database": str(DB_PATH), "model_key_set": model_available()}


@app.get("/whoami")
def whoami(role: str = Depends(current_role)) -> dict:
    return {"role": role, "label": ROLES[role]["label"]}


@app.post("/query")
def query(body: QueryIn, role: str = Depends(current_role)) -> dict:
    llm = default_llm if model_available() else None
    embed = gemini_embed if gemini_available() else None
    answer = answer_query(body.question, llm=llm, embed=embed, role=role)
    # Personal data is masked before it is returned or logged, unless the role may see it.
    data = mask_answer(asdict(answer), DB_PATH, mask=mask_pii(role))
    data["role"] = role
    _log(data)
    return data


@app.get("/schema")
def schema(role: str = Depends(current_role)) -> dict:
    visible = allowed_tables(role)
    return {name: {"description": t["description"], "columns": t["columns"]}
            for name, t in TABLES.items() if name in visible}
