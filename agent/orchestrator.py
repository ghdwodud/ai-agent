from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable, Protocol

from agent.policy import PolicyEngine
from agent.session import SessionState
from agent.types import ActionResult, PolicyStatus, RiskLevel
from tools.file_tool import FileTool
from tools.shell_tool import ShellTool
from tools.web_tool import WebTool

ApproveFn = Callable[[str], str]


class Decider(Protocol):
    def decide(self, goal: str, context_json: str, team_mode: bool = False):
        ...


@dataclass
class RunConfig:
    max_steps: int = 20
    approval_mode: str = "normal"  # strict|normal
    team_mode: bool = False
    log_path: str = "agent_run.jsonl"
    max_retries: int = 1


class Orchestrator:
    def __init__(
        self,
        model_client: Decider,
        policy: PolicyEngine,
        file_tool: FileTool,
        shell_tool: ShellTool,
        web_tool: WebTool,
        logger: logging.Logger,
    ) -> None:
        self.model_client = model_client
        self.policy = policy
        self.file_tool = file_tool
        self.shell_tool = shell_tool
        self.web_tool = web_tool
        self.logger = logger
        self.always_deny_tools: set[str] = set()

    def run(self, session: SessionState, cfg: RunConfig, input_fn: ApproveFn = input) -> str:
        session.add_message("user", session.goal)
        for step in range(1, cfg.max_steps + 1):
            decision, model_metrics = self.model_client.decide(
                goal=session.goal,
                context_json=session.to_prompt_context(),
                team_mode=cfg.team_mode,
            )
            session.add_event("model_metrics", model_metrics)
            self._json_log(cfg.log_path, {"step": step, "type": "model_metrics", "data": model_metrics})

            if decision.kind == "final":
                final_text = decision.final_response or "No final response."
                session.add_message("assistant", final_text)
                self._json_log(cfg.log_path, {"step": step, "type": "final", "text": final_text})
                return final_text

            proposal = decision.action
            if proposal is None:
                msg = "Model returned action kind without action payload."
                session.add_event("error", {"msg": msg})
                return msg

            if proposal.tool_name in self.always_deny_tools:
                deny_msg = f"Tool '{proposal.tool_name}' is always denied for this session."
                session.add_event("approval_denied", {"reason": deny_msg})
                self._json_log(cfg.log_path, {"step": step, "type": "approval_denied", "reason": deny_msg})
                continue

            policy_decision = self.policy.evaluate(proposal)
            session.add_event("policy", policy_decision.model_dump())
            self._json_log(cfg.log_path, {"step": step, "type": "policy", "data": policy_decision.model_dump()})
            if policy_decision.status == PolicyStatus.DENY:
                continue

            if not self._approve(proposal.tool_name, proposal.reason, proposal.args, input_fn):
                session.add_event("approval_denied", {"tool": proposal.tool_name})
                self._json_log(cfg.log_path, {"step": step, "type": "approval_denied", "tool": proposal.tool_name})
                continue

            if (
                policy_decision.status == PolicyStatus.NEEDS_EXTRA_CONFIRMATION
                or proposal.risk_level == RiskLevel.HIGH
                or cfg.approval_mode == "strict"
            ):
                if not self._approve(
                    proposal.tool_name,
                    "Extra confirmation required for high-risk/strict mode.",
                    proposal.args,
                    input_fn,
                ):
                    session.add_event("approval_denied_extra", {"tool": proposal.tool_name})
                    self._json_log(
                        cfg.log_path,
                        {"step": step, "type": "approval_denied_extra", "tool": proposal.tool_name},
                    )
                    continue

            result = self._execute_with_retries(proposal.tool_name, proposal.args, cfg.max_retries)
            session.add_event("tool_result", {"tool": proposal.tool_name, "result": result.model_dump()})
            self._json_log(
                cfg.log_path,
                {
                    "step": step,
                    "type": "tool_result",
                    "tool": proposal.tool_name,
                    "result": result.model_dump(),
                },
            )

        msg = f"Stopped: reached max_steps={cfg.max_steps}."
        session.add_event("stopped", {"reason": msg})
        return msg

    def _execute_with_retries(self, tool_name: str, args: dict, max_retries: int) -> ActionResult:
        last = self._execute_tool(tool_name, args)
        retries = 0
        while (not last.ok) and retries < max_retries and self._is_retryable(last.error_type):
            retries += 1
            last = self._execute_tool(tool_name, args)
        return last

    def _execute_tool(self, tool_name: str, args: dict) -> ActionResult:
        try:
            if tool_name == "file":
                return self.file_tool.run(args)
            if tool_name == "shell":
                return self.shell_tool.run(args)
            if tool_name == "web":
                return self.web_tool.run(args)
            return ActionResult(ok=False, error_type="unknown_tool", stderr=tool_name)
        except Exception as exc:
            self.logger.exception("Tool execution failed")
            return ActionResult(ok=False, error_type="exception", stderr=str(exc))

    def _approve(self, tool_name: str, reason: str, args: dict, input_fn: ApproveFn) -> bool:
        prompt = (
            f"\nProposed action\n"
            f"- tool: {tool_name}\n"
            f"- reason: {reason}\n"
            f"- args: {json.dumps(args, ensure_ascii=True)}\n"
            "Approve? [y]es / [n]o / [ad] always deny this tool: "
        )
        ans = input_fn(prompt).strip().lower()
        if ans == "ad":
            self.always_deny_tools.add(tool_name)
            return False
        return ans in {"y", "yes"}

    def _json_log(self, path: str, row: dict) -> None:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=True) + "\n")
        except Exception:
            self.logger.warning("Failed to write log row")

    @staticmethod
    def _is_retryable(error_type: str | None) -> bool:
        return error_type in {"timeout", "web_error", "shell_error", "exception"}
