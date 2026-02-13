from agent.policy import PolicyEngine
from agent.types import ActionProposal


def test_policy_denies_dangerous_shell():
    engine = PolicyEngine(root_dir=".", allowed_shell_commands=["python", "dir", "ls", "rm"])
    proposal = ActionProposal(
        tool_name="shell",
        reason="cleanup",
        args={"command": "rm -rf /"},
        risk_level="high",
    )
    decision = engine.evaluate(proposal)
    assert decision.status == "deny"


def test_policy_denies_out_of_scope_path():
    engine = PolicyEngine(root_dir="C:/repo", allowed_shell_commands=["python"])
    proposal = ActionProposal(
        tool_name="file",
        reason="write file",
        args={"op": "write", "path": "..\\outside.txt", "content": "x"},
        risk_level="medium",
    )
    decision = engine.evaluate(proposal)
    assert decision.status == "deny"

