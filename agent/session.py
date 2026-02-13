from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass
class SessionState:
    goal: str
    cwd: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content, "ts": _utc_now_iso()})

    def add_event(self, event_type: str, data: dict[str, Any]) -> None:
        self.events.append({"type": event_type, "data": data, "ts": _utc_now_iso()})

    def to_prompt_context(self) -> str:
        return json.dumps(
            {
                "goal": self.goal,
                "cwd": self.cwd,
                "recent_messages": self.messages[-10:],
                "recent_events": self.events[-10:],
            },
            ensure_ascii=True,
            indent=2,
        )

