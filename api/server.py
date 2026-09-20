"""HTTP API + static UI for the multi-agent code system.

Run locally:   uv run uvicorn api.server:app --port 8000
Then open:     http://localhost:8000

Environment (all optional):
    ACCESS_CODE          if set, every /api request must send it as X-Access-Code
    CORS_ORIGINS         comma-separated origins allowed to call the API
                         (needed when the UI is hosted on a different domain)
    MAX_ACTIVE_SESSIONS  concurrent runs allowed (default 3)
"""
from __future__ import annotations

import hmac
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api.sessions import SessionStore

load_dotenv()

MAX_TASK_CHARS = 2000
MAX_FEEDBACK_CHARS = 1000
MAX_ROUNDS_CAP = 5
MAX_STEPS_CAP = 5

app = FastAPI(title="Multi-Agent Code System")
store = SessionStore(max_active=int(os.getenv("MAX_ACTIVE_SESSIONS", "3")))

_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Access-Code"],
    )


def require_access(x_access_code: str | None = Header(default=None)) -> None:
    expected = os.getenv("ACCESS_CODE")
    if expected and not hmac.compare_digest(x_access_code or "", expected):
        raise HTTPException(status_code=401, detail="invalid or missing access code")


class NewSession(BaseModel):
    task: str = Field(min_length=1, max_length=MAX_TASK_CHARS)
    critique_max_rounds: int = Field(default=3, ge=1, le=MAX_ROUNDS_CAP)
    supervisor_max_steps: int = Field(default=3, ge=1, le=MAX_STEPS_CAP)


class Decision(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    feedback: str | None = Field(default=None, max_length=MAX_FEEDBACK_CHARS)
    extra_steps: int = Field(default=0, ge=0, le=MAX_STEPS_CAP)


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "access_code_required": bool(os.getenv("ACCESS_CODE")),
        "provider": os.getenv("LLM_PROVIDER", "groq"),
    }


@app.post("/api/sessions", dependencies=[Depends(require_access)])
def create_session(body: NewSession) -> dict:
    try:
        session = store.create(body.task.strip(), body.critique_max_rounds, body.supervisor_max_steps)
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    return {"id": session.id}


@app.get("/api/sessions/{session_id}", dependencies=[Depends(require_access)])
def get_session(session_id: str, since: int = 0) -> dict:
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="unknown session")
    return session.snapshot(max(0, since))


@app.post("/api/sessions/{session_id}/decision", dependencies=[Depends(require_access)])
def decide(session_id: str, body: Decision) -> dict:
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="unknown session")
    if body.decision == "reject" and not (body.feedback or "").strip():
        raise HTTPException(status_code=422, detail="feedback is required when rejecting")
    try:
        session.decide(body.decision, (body.feedback or "").strip() or None, body.extra_steps)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True}


WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
