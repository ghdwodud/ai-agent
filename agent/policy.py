from __future__ import annotations

import os
import re
from pathlib import Path

from agent.types import ActionProposal, PolicyDecision, PolicyStatus, RiskLevel

BLOCKED_SHELL_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\bdel\s+/[sq]\b",
    r"\bformat\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bmkfs\b",
]


class PolicyEngine:
    def __init__(self, root_dir: str, allowed_shell_commands: list[str]) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.allowed_shell_commands = set(allowed_shell_commands)

    def evaluate(self, proposal: ActionProposal) -> PolicyDecision:
        if proposal.tool_name == "shell":
            return self._evaluate_shell(proposal)
        if proposal.tool_name == "file":
            return self._evaluate_file(proposal)
        if proposal.tool_name == "web":
            if proposal.risk_level == RiskLevel.HIGH:
                return PolicyDecision(
                    status=PolicyStatus.NEEDS_EXTRA_CONFIRMATION,
                    reason="High-risk web action requires extra confirmation.",
                )
            return PolicyDecision(status=PolicyStatus.ALLOW, reason="Allowed web action.")
        return PolicyDecision(status=PolicyStatus.DENY, reason="Unknown tool.")

    def _evaluate_shell(self, proposal: ActionProposal) -> PolicyDecision:
        command = str(proposal.args.get("command", "")).strip()
        if not command:
            return PolicyDecision(status=PolicyStatus.DENY, reason="Shell command is empty.")

        token = command.split()[0].lower()
        if token not in self.allowed_shell_commands:
            return PolicyDecision(
                status=PolicyStatus.DENY,
                reason=f"Shell command '{token}' is not in allowlist.",
            )

        lowered = command.lower()
        for pattern in BLOCKED_SHELL_PATTERNS:
            if re.search(pattern, lowered):
                return PolicyDecision(
                    status=PolicyStatus.DENY,
                    reason=f"Blocked shell pattern matched: {pattern}",
                )

        if proposal.risk_level == RiskLevel.HIGH:
            return PolicyDecision(
                status=PolicyStatus.NEEDS_EXTRA_CONFIRMATION,
                reason="High-risk shell action requires extra confirmation.",
            )
        return PolicyDecision(status=PolicyStatus.ALLOW, reason="Allowed shell action.")

    def _evaluate_file(self, proposal: ActionProposal) -> PolicyDecision:
        path_value = proposal.args.get("path")
        if not path_value:
            return PolicyDecision(status=PolicyStatus.DENY, reason="File action missing path.")

        path = Path(os.path.join(str(self.root_dir), str(path_value))).resolve()
        if not self._is_under_root(path):
            return PolicyDecision(
                status=PolicyStatus.DENY,
                reason=f"Path out of scope: {path}",
            )

        if proposal.risk_level == RiskLevel.HIGH:
            return PolicyDecision(
                status=PolicyStatus.NEEDS_EXTRA_CONFIRMATION,
                reason="High-risk file action requires extra confirmation.",
            )
        return PolicyDecision(status=PolicyStatus.ALLOW, reason="Allowed file action.")

    def _is_under_root(self, path: Path) -> bool:
        try:
            path.relative_to(self.root_dir)
            return True
        except ValueError:
            return False

