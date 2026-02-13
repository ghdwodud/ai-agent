from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionProposal(BaseModel):
    tool_name: Literal["file", "shell", "web"]
    reason: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.MEDIUM


class ActionResult(BaseModel):
    ok: bool
    payload: Optional[dict[str, Any]] = None
    stdout: str = ""
    stderr: str = ""
    artifacts: list[str] = Field(default_factory=list)
    error_type: Optional[str] = None


class DecisionKind(str, Enum):
    ACTION = "action"
    FINAL = "final"


class AgentDecision(BaseModel):
    kind: DecisionKind
    action: Optional[ActionProposal] = None
    final_response: Optional[str] = None


class PolicyStatus(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    NEEDS_EXTRA_CONFIRMATION = "needs_extra_confirmation"


class PolicyDecision(BaseModel):
    status: PolicyStatus
    reason: str

