from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from agent.model_client import ModelClient
from agent.orchestrator import Orchestrator, RunConfig
from agent.policy import PolicyEngine
from agent.session import SessionState
from tools.file_tool import FileTool
from tools.shell_tool import ShellTool
from tools.web_tool import WebTool


def _load_config(path: str) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {}
    return yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Approval-first local CLI agent")
    p.add_argument("--goal", required=True, help="Goal for the agent")
    p.add_argument("--cwd", default=".", help="Working directory scope")
    p.add_argument("--max-steps", type=int, default=None)
    p.add_argument("--max-retries", type=int, default=None)
    p.add_argument("--provider", choices=["openai", "anthropic", "gemini"], default=None)
    p.add_argument("--model", default=None)
    p.add_argument("--approval", choices=["strict", "normal"], default=None)
    p.add_argument("--log-level", default="INFO")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--team-mode", action="store_true")
    return p


def main() -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()
    cfg = _load_config(args.config)

    log_level = getattr(logging, str(args.log_level).upper(), logging.INFO)
    logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("agent")

    cwd = str(Path(args.cwd).resolve())
    if not Path(cwd).exists():
        print(f"Invalid --cwd path: {cwd}")
        return 2

    if not args.goal.strip():
        print("Goal must be non-empty.")
        return 2

    provider = args.provider or os.getenv("MODEL_PROVIDER") or cfg.get("provider", "openai")
    if provider == "openai":
        default_model = "gpt-4.1-mini"
        model_env = os.getenv("OPENAI_MODEL")
    elif provider == "anthropic":
        default_model = "claude-3-5-sonnet-latest"
        model_env = os.getenv("ANTHROPIC_MODEL")
    else:
        default_model = "gemini-2.5-flash"
        model_env = os.getenv("GEMINI_MODEL")
    model = args.model or model_env or cfg.get("model", default_model)
    max_steps = args.max_steps or int(cfg.get("max_steps", 20))
    max_retries = args.max_retries or int(cfg.get("max_retries", 1))
    approval_mode = args.approval or cfg.get("approval_mode", "normal")
    allowed_shell = cfg.get("shell", {}).get("allowed_commands", ["dir", "ls", "python", "pytest"])
    web_max_results = int(cfg.get("web", {}).get("max_results", 5))

    session = SessionState(goal=args.goal, cwd=cwd)
    model_client = ModelClient(model=model, provider=provider)
    policy = PolicyEngine(root_dir=cwd, allowed_shell_commands=allowed_shell)
    file_tool = FileTool(root_dir=cwd)
    shell_tool = ShellTool(cwd=cwd, allowed_commands=allowed_shell)
    web_tool = WebTool(max_results=web_max_results)
    orchestrator = Orchestrator(model_client, policy, file_tool, shell_tool, web_tool, logger)

    run_cfg = RunConfig(
        max_steps=max_steps,
        max_retries=max_retries,
        approval_mode=approval_mode,
        team_mode=args.team_mode,
    )
    final_text = orchestrator.run(session, run_cfg)

    print("\n=== Final Report ===")
    print(final_text)
    print(f"Events logged: {len(session.events)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
