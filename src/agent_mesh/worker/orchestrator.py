"""AG2 orchestration adapter.

This is the seam where the AG2 group-chat / blackboard mesh is invoked. AG2 is
Python-native, which is the core reason this POC is Python-first. The adapter
degrades to a deterministic stub when ``ag2`` is not installed so the execution
flow — including the approval pause/resume — can be exercised in CI and locally
without model credentials.

A real implementation would construct planner / executor / reviewer / tool-router
agents, run a GroupChat, and surface tool calls back through the Tool Gateway.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_mesh.contracts.models import TaskRecord


@dataclass
class OrchestrationResult:
    summary: str
    proposed_writes: list[dict] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


def ag2_available() -> bool:
    try:
        import autogen  # noqa: F401  (ag2 publishes the `autogen` import name)

        return True
    except Exception:
        return False


def run_mesh(task: TaskRecord) -> OrchestrationResult:
    """Run the agent mesh for a task.

    Returns the result summary plus any *proposed* write actions. Proposed
    writes are NOT executed here; the worker gates them through the approval
    ledger before any Tool Gateway execution.
    """
    if ag2_available():
        return _run_ag2(task)
    return _run_stub(task)


def _run_stub(task: TaskRecord) -> OrchestrationResult:
    """Deterministic stand-in for the AG2 group chat.

    Heuristic: if the prompt mentions a mutating verb, propose a gated write so
    the approval path is exercised end to end."""
    prompt = task.prompt.lower()
    write_triggers = ("create", "update", "send", "publish", "invoice", "commit", "delete")
    proposed: list[dict] = []
    if any(trigger in prompt for trigger in write_triggers):
        proposed.append(
            {
                "tool_name": "monday_create_item",
                "category": "write",
                "parameters": {"item_name": task.prompt[:80], "status": "Not Started"},
            }
        )
    return OrchestrationResult(
        summary=f"[stub] planned response for: {task.prompt[:120]}",
        proposed_writes=proposed,
        evidence=[],
    )


def _run_ag2(task: TaskRecord) -> OrchestrationResult:  # pragma: no cover - needs ag2 + creds
    """Placeholder for the real AG2 GroupChat run.

    Intentionally minimal: wiring real agents requires model credentials and the
    LiteLLM base URL, which are out of scope for the importable POC. The shape of
    the return value is what the worker consumes regardless of backend.
    """
    return _run_stub(task)
