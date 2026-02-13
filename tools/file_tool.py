from __future__ import annotations

import os
import re
from pathlib import Path

from pydantic import BaseModel, Field

from agent.types import ActionResult


class FileArgs(BaseModel):
    op: str = Field(description="read|write|search")
    path: str | None = None
    content: str | None = None
    pattern: str | None = None
    glob: str = "*"


class FileTool:
    def __init__(self, root_dir: str) -> None:
        self.root = Path(root_dir).resolve()

    def run(self, args: dict) -> ActionResult:
        parsed = FileArgs.model_validate(args)
        op = parsed.op.lower()
        if op == "read":
            return self._read(parsed.path)
        if op == "write":
            return self._write(parsed.path, parsed.content or "")
        if op == "search":
            return self._search(parsed.pattern or "", parsed.glob)
        return ActionResult(ok=False, error_type="invalid_args", stderr=f"Unknown file op: {parsed.op}")

    def _resolve(self, rel: str | None) -> Path:
        if not rel:
            raise ValueError("path is required")
        path = Path(os.path.join(str(self.root), rel)).resolve()
        path.relative_to(self.root)
        return path

    def _read(self, rel: str | None) -> ActionResult:
        try:
            path = self._resolve(rel)
            text = path.read_text(encoding="utf-8")
            return ActionResult(ok=True, stdout=text, artifacts=[str(path)])
        except Exception as exc:
            return ActionResult(ok=False, error_type="read_error", stderr=str(exc))

    def _write(self, rel: str | None, content: str) -> ActionResult:
        try:
            path = self._resolve(rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return ActionResult(ok=True, stdout=f"Wrote {len(content)} chars", artifacts=[str(path)])
        except Exception as exc:
            return ActionResult(ok=False, error_type="write_error", stderr=str(exc))

    def _search(self, pattern: str, glob: str) -> ActionResult:
        try:
            if not pattern:
                return ActionResult(ok=False, error_type="invalid_args", stderr="pattern is required")
            regex = re.compile(pattern)
            matches: list[dict[str, str | int]] = []
            for path in self.root.rglob(glob):
                if not path.is_file():
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                for idx, line in enumerate(text.splitlines(), start=1):
                    if regex.search(line):
                        matches.append({"path": str(path), "line": idx, "content": line[:300]})
                        if len(matches) >= 200:
                            break
                if len(matches) >= 200:
                    break
            return ActionResult(ok=True, payload={"matches": matches}, stdout=f"{len(matches)} matches")
        except Exception as exc:
            return ActionResult(ok=False, error_type="search_error", stderr=str(exc))

