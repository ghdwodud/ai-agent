from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from webapp.run_manager import RunManager, RunRequest

load_dotenv()

app = FastAPI(title="Remote Agent API", version="0.1.0")
manager = RunManager()
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ApproveRequest(BaseModel):
    request_id: str = Field(min_length=1)
    decision: str = Field(description="y|n|ad")


def require_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("AGENT_WEB_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=500, detail="AGENT_WEB_TOKEN is not configured.")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization.split(" ", 1)[1].strip()
    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid token.")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root_ui() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.post("/runs", dependencies=[Depends(require_token)])
def create_run(req: RunRequest) -> dict[str, Any]:
    state = manager.create_run(req)
    return {"run_id": state.run_id, "status": state.status}


@app.get("/runs/{run_id}", dependencies=[Depends(require_token)])
def get_run(run_id: str) -> dict[str, Any]:
    snap = manager.snapshot(run_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return snap


@app.get("/runs/{run_id}/events", dependencies=[Depends(require_token)])
def get_events(run_id: str) -> dict[str, Any]:
    events = manager.events(run_id)
    if events is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return {"items": events}


@app.post("/runs/{run_id}/approve", dependencies=[Depends(require_token)])
def approve(run_id: str, req: ApproveRequest) -> dict[str, Any]:
    decision = req.decision.strip().lower()
    if decision not in {"y", "n", "ad", "yes", "no"}:
        raise HTTPException(status_code=400, detail="decision must be one of y/n/ad/yes/no.")
    ok = manager.approve(run_id=run_id, request_id=req.request_id, decision=decision)
    if not ok:
        raise HTTPException(status_code=409, detail="No matching pending approval.")
    return {"ok": True}
