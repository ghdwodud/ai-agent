from __future__ import annotations

import os
from typing import Any

import requests
from pydantic import BaseModel, Field

from agent.types import ActionResult


class WebArgs(BaseModel):
    query: str = Field(min_length=1)
    max_results: int = 5


class WebTool:
    def __init__(self, max_results: int = 5) -> None:
        self.max_results = max_results
        self.tavily_key = os.getenv("TAVILY_API_KEY", "").strip()

    def run(self, args: dict[str, Any]) -> ActionResult:
        parsed = WebArgs.model_validate(args)
        max_results = max(1, min(parsed.max_results, 10))
        if self.tavily_key:
            return self._search_tavily(parsed.query, max_results)
        return self._search_duckduckgo(parsed.query, max_results)

    def _search_tavily(self, query: str, max_results: int) -> ActionResult:
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.tavily_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                },
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            for item in data.get("results", [])[:max_results]:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": item.get("content", "")[:400],
                    }
                )
            return ActionResult(ok=True, payload={"provider": "tavily", "results": results})
        except Exception as exc:
            return ActionResult(ok=False, error_type="web_error", stderr=str(exc))

    def _search_duckduckgo(self, query: str, max_results: int) -> ActionResult:
        try:
            resp = requests.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_html": "1",
                    "skip_disambig": "1",
                },
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            for topic in data.get("RelatedTopics", []):
                if isinstance(topic, dict) and topic.get("FirstURL"):
                    results.append(
                        {
                            "title": topic.get("Text", "")[:120],
                            "url": topic.get("FirstURL", ""),
                            "content": topic.get("Text", "")[:400],
                        }
                    )
                if len(results) >= max_results:
                    break
            if not results and data.get("AbstractURL"):
                results.append(
                    {
                        "title": data.get("Heading", ""),
                        "url": data.get("AbstractURL", ""),
                        "content": data.get("AbstractText", "")[:400],
                    }
                )
            return ActionResult(ok=True, payload={"provider": "duckduckgo", "results": results})
        except Exception as exc:
            return ActionResult(ok=False, error_type="web_error", stderr=str(exc))

