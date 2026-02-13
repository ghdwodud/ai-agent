from __future__ import annotations

import os
import secrets
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from webapp.run_manager import RunManager, RunRequest

load_dotenv()

app = FastAPI(title="Remote Agent API", version="0.1.0")
manager = RunManager()
STATIC_DIR = Path(__file__).parent / "static"
SESSION_COOKIE = "agent_session"
SESSION_TTL_SECONDS = 60 * 60 * 12
_sessions: dict[str, dict[str, Any]] = {}


class ApproveRequest(BaseModel):
    request_id: str = Field(min_length=1)
    decision: str = Field(description="y|n|ad")


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


def _is_local_authenticated(request: Request) -> bool:
    token = request.cookies.get(SESSION_COOKIE, "").strip()
    if not token:
        return False
    session = _sessions.get(token)
    if not session:
        return False
    if session.get("exp", 0) < int(time.time()):
        _sessions.pop(token, None)
        return False
    return True


def require_auth(
    request: Request,
    authorization: str | None = Header(default=None),
    cf_access_user_email: str | None = Header(default=None, alias="CF-Access-Authenticated-User-Email"),
    cf_access_jwt_assertion: str | None = Header(default=None, alias="CF-Access-Jwt-Assertion"),
) -> None:
    auth_mode = os.getenv("AGENT_AUTH_MODE", "local_login").strip().lower()
    if auth_mode == "none":
        return
    if auth_mode == "local_login":
        if _is_local_authenticated(request):
            return
        raise HTTPException(status_code=401, detail="Login required.")

    allowed_emails = {
        e.strip().lower()
        for e in os.getenv("AGENT_ALLOWED_EMAILS", "").split(",")
        if e.strip()
    }

    # If Cloudflare Access is enabled for this hostname, these headers are injected.
    if cf_access_user_email or cf_access_jwt_assertion:
        if allowed_emails:
            email = (cf_access_user_email or "").strip().lower()
            if not email or email not in allowed_emails:
                raise HTTPException(status_code=403, detail="Email is not allowed.")
        return

    if auth_mode == "cloudflare_only":
        raise HTTPException(status_code=401, detail="Cloudflare Access authentication required.")

    expected = os.getenv("AGENT_WEB_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=401,
            detail="No Cloudflare Access header and AGENT_WEB_TOKEN is not configured.",
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization.split(" ", 1)[1].strip()
    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid token.")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root_ui(request: Request) -> Response:
    if not _is_local_authenticated(request):
        return RedirectResponse(url="/login", status_code=307)
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/login")
def login_ui() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "login.html"))


@app.post("/api/login")
def login(req: LoginRequest, response: Response) -> dict[str, Any]:
    expected_user = os.getenv("ADMIN_USERNAME", "").strip()
    expected_pw = os.getenv("ADMIN_PASSWORD", "").strip()
    if not expected_user or not expected_pw:
        raise HTTPException(status_code=500, detail="ADMIN_USERNAME/ADMIN_PASSWORD are not configured.")
    if req.username != expected_user or req.password != expected_pw:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    token = secrets.token_urlsafe(32)
    _sessions[token] = {"user": req.username, "exp": int(time.time()) + SESSION_TTL_SECONDS}
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
    )
    return {"ok": True, "user": req.username}


@app.post("/api/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    token = request.cookies.get(SESSION_COOKIE, "").strip()
    if token:
        _sessions.pop(token, None)
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.get("/static/{asset_path:path}")
def static_asset(asset_path: str, _: None = Depends(require_auth)) -> FileResponse:
    safe_path = (STATIC_DIR / asset_path).resolve()
    static_root = STATIC_DIR.resolve()
    try:
        safe_path.relative_to(static_root)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found.")
    if not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="Not found.")
    return FileResponse(str(safe_path))


@app.post("/runs", dependencies=[Depends(require_auth)])
def create_run(req: RunRequest) -> dict[str, Any]:
    state = manager.create_run(req)
    return {"run_id": state.run_id, "status": state.status}


@app.get("/runs/{run_id}", dependencies=[Depends(require_auth)])
def get_run(run_id: str) -> dict[str, Any]:
    snap = manager.snapshot(run_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return snap


@app.get("/runs/{run_id}/events", dependencies=[Depends(require_auth)])
def get_events(run_id: str) -> dict[str, Any]:
    events = manager.events(run_id)
    if events is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return {"items": events}


@app.post("/runs/{run_id}/approve", dependencies=[Depends(require_auth)])
def approve(run_id: str, req: ApproveRequest) -> dict[str, Any]:
    decision = req.decision.strip().lower()
    if decision not in {"y", "n", "ad", "yes", "no"}:
        raise HTTPException(status_code=400, detail="decision must be one of y/n/ad/yes/no.")
    ok = manager.approve(run_id=run_id, request_id=req.request_id, decision=decision)
    if not ok:
        raise HTTPException(status_code=409, detail="No matching pending approval.")
    return {"ok": True}
