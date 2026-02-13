from __future__ import annotations

import logging
import os
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from agent.model_client import ModelClient
from agent.orchestrator import Orchestrator, RunConfig
from agent.policy import PolicyEngine
from agent.session import SessionState
from tools.file_tool import FileTool
from tools.shell_tool import ShellTool
from tools.web_tool import WebTool


def load_config(path: str = "config.yaml") -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {}
    return yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}


class RunRequest(BaseModel):
    goal: str = Field(min_length=1)
    cwd: str = "."
    provider: Optional[str] = None
    model: Optional[str] = None
    max_steps: Optional[int] = None
    max_retries: Optional[int] = None
    approval_mode: Optional[str] = None
    team_mode: bool = False


class PendingApproval(BaseModel):
    request_id: str
    tool_name: str
    reason: str
    args: dict[str, Any]
    stage: str


@dataclass
class RunState:
    run_id: str
    request: RunRequest
    status: str = "running"  # running|waiting_approval|completed|failed
    final_text: str = ""
    error: str = ""
    session: Optional[SessionState] = None
    pending: Optional[PendingApproval] = None
    approval_answer: Optional[str] = None
    events: list[dict[str, Any]] = field(default_factory=list)
    lock: threading.Condition = field(default_factory=threading.Condition)


class RunManager:
    def __init__(self) -> None:
        load_dotenv()
        self.cfg = load_config()
        self.logger = logging.getLogger("web-agent")
        self._runs: dict[str, RunState] = {}
        self._runs_lock = threading.Lock()

    def create_run(self, req: RunRequest) -> RunState:
        run_id = uuid.uuid4().hex
        state = RunState(run_id=run_id, request=req)
        with self._runs_lock:
            self._runs[run_id] = state
        t = threading.Thread(target=self._run_worker, args=(state,), daemon=True)
        t.start()
        return state

    def get_run(self, run_id: str) -> Optional[RunState]:
        with self._runs_lock:
            return self._runs.get(run_id)

    def approve(self, run_id: str, request_id: str, decision: str) -> bool:
        state = self.get_run(run_id)
        if state is None:
            return False
        with state.lock:
            if state.pending is None or state.pending.request_id != request_id:
                return False
            state.approval_answer = decision.strip().lower()
            state.status = "running"
            state.events.append({"type": "approval_received", "decision": state.approval_answer})
            state.lock.notify_all()
            return True

    def snapshot(self, run_id: str) -> Optional[dict[str, Any]]:
        state = self.get_run(run_id)
        if state is None:
            return None
        with state.lock:
            return {
                "run_id": state.run_id,
                "status": state.status,
                "goal": state.request.goal,
                "cwd": state.request.cwd,
                "final_text": state.final_text,
                "error": state.error,
                "pending": state.pending.model_dump() if state.pending else None,
                "event_count": len(state.events),
            }

    def events(self, run_id: str) -> Optional[list[dict[str, Any]]]:
        state = self.get_run(run_id)
        if state is None:
            return None
        with state.lock:
            return list(state.events)

    def _run_worker(self, state: RunState) -> None:
        try:
            cwd = str(Path(state.request.cwd).resolve())
            provider = state.request.provider or os.getenv("MODEL_PROVIDER") or self.cfg.get("provider", "gemini")
            if provider == "openai":
                default_model = "gpt-4.1-mini"
                model_env = os.getenv("OPENAI_MODEL")
            elif provider == "anthropic":
                default_model = "claude-3-5-sonnet-latest"
                model_env = os.getenv("ANTHROPIC_MODEL")
            else:
                default_model = "gemini-2.5-flash"
                model_env = os.getenv("GEMINI_MODEL")
            model = state.request.model or model_env or self.cfg.get("model", default_model)
            max_steps = state.request.max_steps or int(self.cfg.get("max_steps", 20))
            max_retries = state.request.max_retries or int(self.cfg.get("max_retries", 1))
            approval_mode = state.request.approval_mode or self.cfg.get("approval_mode", "normal")
            allowed_shell = self.cfg.get("shell", {}).get("allowed_commands", ["dir", "ls", "python", "pytest"])
            web_max_results = int(self.cfg.get("web", {}).get("max_results", 5))

            session = SessionState(goal=state.request.goal, cwd=cwd)
            with state.lock:
                state.session = session

            orchestrator = Orchestrator(
                model_client=ModelClient(model=model, provider=provider),
                policy=PolicyEngine(root_dir=cwd, allowed_shell_commands=allowed_shell),
                file_tool=FileTool(root_dir=cwd),
                shell_tool=ShellTool(cwd=cwd, allowed_commands=allowed_shell),
                web_tool=WebTool(max_results=web_max_results),
                logger=self.logger,
            )
            run_cfg = RunConfig(
                max_steps=max_steps,
                max_retries=max_retries,
                approval_mode=approval_mode,
                team_mode=state.request.team_mode,
                log_path=f"agent_run_{state.run_id}.jsonl",
            )
            final = orchestrator.run(
                session,
                run_cfg,
                structured_approve_fn=lambda tool, reason, args, stage: self._wait_for_approval(
                    state, tool, reason, args, stage
                ),
            )
            with state.lock:
                state.final_text = final
                state.status = "completed"
                state.events.append({"type": "completed", "final_text": final})
                state.pending = None
        except Exception as exc:
            with state.lock:
                state.status = "failed"
                state.error = str(exc)
                state.events.append({"type": "failed", "error": str(exc)})

    def _wait_for_approval(self, state: RunState, tool: str, reason: str, args: dict[str, Any], stage: str) -> str:
        req = PendingApproval(
            request_id=uuid.uuid4().hex,
            tool_name=tool,
            reason=reason,
            args=args,
            stage=stage,
        )
        with state.lock:
            state.pending = req
            state.approval_answer = None
            state.status = "waiting_approval"
            state.events.append({"type": "approval_requested", "pending": req.model_dump()})
            timeout_seconds = 3600
            ok = state.lock.wait_for(lambda: state.approval_answer is not None, timeout=timeout_seconds)
            if not ok:
                state.events.append({"type": "approval_timeout", "request_id": req.request_id})
                state.pending = None
                state.status = "running"
                return "n"
            answer = state.approval_answer or "n"
            state.pending = None
            return answer

