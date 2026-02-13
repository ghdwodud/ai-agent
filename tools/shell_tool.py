from __future__ import annotations

import shlex
import subprocess
import sys
from typing import Any

from pydantic import BaseModel, Field

from agent.types import ActionResult


class ShellArgs(BaseModel):
    command: str = Field(min_length=1)
    timeout_seconds: int = 30


class ShellTool:
    def __init__(self, cwd: str, allowed_commands: list[str]) -> None:
        self.cwd = cwd
        self.allowed_commands = set(allowed_commands)

    def run(self, args: dict[str, Any]) -> ActionResult:
        try:
            parsed = ShellArgs.model_validate(args)
            parts = shlex.split(parsed.command, posix=False)
            if not parts:
                return ActionResult(ok=False, error_type="invalid_args", stderr="Empty command")
            token = parts[0].lower()
            if token not in self.allowed_commands:
                return ActionResult(
                    ok=False,
                    error_type="policy_denied",
                    stderr=f"Command '{token}' not allowed",
                )
            run_args: list[str]
            if sys.platform.startswith("win"):
                run_args = ["powershell", "-NoProfile", "-Command", parsed.command]
            else:
                run_args = parts
            completed = subprocess.run(
                run_args,
                cwd=self.cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=parsed.timeout_seconds,
                shell=False,
            )
            return ActionResult(
                ok=completed.returncode == 0,
                stdout=completed.stdout[-8000:],
                stderr=completed.stderr[-8000:],
                payload={"returncode": completed.returncode},
            )
        except subprocess.TimeoutExpired:
            return ActionResult(ok=False, error_type="timeout", stderr="Command timed out")
        except Exception as exc:
            return ActionResult(ok=False, error_type="shell_error", stderr=str(exc))
