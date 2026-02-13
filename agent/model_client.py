from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests
from openai import OpenAI
from pydantic import ValidationError

from agent.types import AgentDecision

try:
    from anthropic import Anthropic
except Exception:  # pragma: no cover - optional dependency
    Anthropic = None


SYSTEM_PROMPT = """You are a safe task automation agent.
You must respond with JSON only.
Decide one of:
1) {"kind":"action","action":{"tool_name":"file|shell|web","reason":"...","args":{...},"risk_level":"low|medium|high"}}
2) {"kind":"final","final_response":"..."}

Rules:
- Propose exactly one action per step.
- Keep action args concrete and minimal.
- Use risk_level=high for potentially destructive commands.
- Never propose out-of-scope system changes.
"""


class ModelClient:
    def __init__(self, model: str, provider: str = "openai") -> None:
        self.model = model
        self.provider = provider
        if provider == "openai":
            self.client = OpenAI()
        elif provider == "anthropic":
            if Anthropic is None:
                raise RuntimeError("anthropic package is not installed.")
            self.client = Anthropic()
        elif provider == "gemini":
            self.client = None
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def decide(self, goal: str, context_json: str, team_mode: bool = False) -> tuple[AgentDecision, dict[str, Any]]:
        if self.provider == "openai":
            return self._decide_openai(goal, context_json, team_mode)
        if self.provider == "anthropic":
            return self._decide_anthropic(goal, context_json, team_mode)
        return self._decide_gemini(goal, context_json, team_mode)

    def _decide_openai(self, goal: str, context_json: str, team_mode: bool) -> tuple[AgentDecision, dict[str, Any]]:
        start = time.time()
        mode_line = (
            "Use an internal planner/executor/reviewer perspective before finalizing one action."
            if team_mode
            else "Reason directly."
        )
        prompt = (
            f"Goal:\n{goal}\n\n"
            f"Context:\n{context_json}\n\n"
            f"{mode_line}\n"
            "Return strict JSON only."
        )
        response = self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        latency_ms = int((time.time() - start) * 1000)
        text = response.output_text.strip()
        decision = self._parse_decision(text)

        usage = getattr(response, "usage", None)
        metrics = {
            "latency_ms": latency_ms,
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "model": self.model,
            "provider": self.provider,
        }
        return decision, metrics

    def _decide_gemini(self, goal: str, context_json: str, team_mode: bool) -> tuple[AgentDecision, dict[str, Any]]:
        start = time.time()
        mode_line = (
            "Use an internal planner/executor/reviewer perspective before finalizing one action."
            if team_mode
            else "Reason directly."
        )
        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"Goal:\n{goal}\n\n"
            f"Context:\n{context_json}\n\n"
            f"{mode_line}\n"
            "Return strict JSON only."
        )
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            decision = AgentDecision(kind="final", final_response="Missing GEMINI_API_KEY or GOOGLE_API_KEY.")
            return decision, {"latency_ms": 0, "input_tokens": None, "output_tokens": None, "model": self.model, "provider": self.provider}

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        try:
            resp = requests.post(
                url,
                params={"key": api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.2},
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            text = self._extract_gemini_text(data)
            decision = self._parse_decision(text)
            usage = data.get("usageMetadata", {})
            metrics = {
                "latency_ms": int((time.time() - start) * 1000),
                "input_tokens": usage.get("promptTokenCount"),
                "output_tokens": usage.get("candidatesTokenCount"),
                "model": self.model,
                "provider": self.provider,
            }
            return decision, metrics
        except Exception as exc:
            decision = AgentDecision(kind="final", final_response=f"Gemini request error: {exc}")

        metrics = {
            "latency_ms": int((time.time() - start) * 1000),
            "input_tokens": None,
            "output_tokens": None,
            "model": self.model,
            "provider": self.provider,
        }
        return decision, metrics

    @staticmethod
    def _extract_gemini_text(data: dict[str, Any]) -> str:
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
        return "".join(texts).strip()

    def _decide_anthropic(self, goal: str, context_json: str, team_mode: bool) -> tuple[AgentDecision, dict[str, Any]]:
        start = time.time()
        mode_line = (
            "Use an internal planner/executor/reviewer perspective before finalizing one action."
            if team_mode
            else "Reason directly."
        )
        prompt = (
            f"Goal:\n{goal}\n\n"
            f"Context:\n{context_json}\n\n"
            f"{mode_line}\n"
            "Return strict JSON only."
        )
        response = self.client.messages.create(
            model=self.model,
            max_tokens=800,
            temperature=0.2,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = int((time.time() - start) * 1000)
        text = ""
        if response.content and hasattr(response.content[0], "text"):
            text = response.content[0].text.strip()
        decision = self._parse_decision(text)

        usage = getattr(response, "usage", None)
        metrics = {
            "latency_ms": latency_ms,
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "model": self.model,
            "provider": self.provider,
        }
        return decision, metrics

    def _parse_decision(self, raw_text: str) -> AgentDecision:
        text = (raw_text or "").strip()
        if not text:
            return AgentDecision(kind="final", final_response="Model output parse error: empty output")
        candidates = [text]
        fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        candidates.extend(fenced)
        object_match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if object_match:
            candidates.append(object_match.group(0))

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                return AgentDecision.model_validate(parsed)
            except (json.JSONDecodeError, ValidationError):
                continue
        preview = text[:200].replace("\n", " ")
        return AgentDecision(kind="final", final_response=f"Model output parse error. raw={preview}")
