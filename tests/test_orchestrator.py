import logging
from pathlib import Path

from agent.orchestrator import Orchestrator, RunConfig
from agent.policy import PolicyEngine
from agent.session import SessionState
from agent.types import ActionResult, AgentDecision, ActionProposal
from tools.file_tool import FileTool
from tools.shell_tool import ShellTool
from tools.web_tool import WebTool


class FakeModelClient:
    def __init__(self):
        self.calls = 0

    def decide(self, goal: str, context_json: str, team_mode: bool = False):
        self.calls += 1
        if self.calls == 1:
            return (
                AgentDecision(
                    kind="action",
                    action=ActionProposal(
                        tool_name="shell",
                        reason="list dir",
                        args={"command": "dir"},
                        risk_level="low",
                    ),
                ),
                {"latency_ms": 1},
            )
        return AgentDecision(kind="final", final_response="done"), {"latency_ms": 1}


class DummyShellTool(ShellTool):
    def __init__(self, cwd: str):
        super().__init__(cwd=cwd, allowed_commands=["dir"])
        self.runs = 0

    def run(self, args):
        self.runs += 1
        return ActionResult(ok=True, stdout="ok")


def test_no_execution_without_approval(tmp_path: Path):
    model = FakeModelClient()
    shell = DummyShellTool(cwd=str(tmp_path))
    orchestrator = Orchestrator(
        model_client=model,
        policy=PolicyEngine(root_dir=str(tmp_path), allowed_shell_commands=["dir"]),
        file_tool=FileTool(root_dir=str(tmp_path)),
        shell_tool=shell,
        web_tool=WebTool(max_results=1),
        logger=logging.getLogger("test"),
    )
    session = SessionState(goal="test", cwd=str(tmp_path))
    cfg = RunConfig(max_steps=3, approval_mode="normal")
    answers = iter(["n", "y"])

    final = orchestrator.run(session, cfg, input_fn=lambda _: next(answers))

    assert final == "done"
    assert shell.runs == 0

