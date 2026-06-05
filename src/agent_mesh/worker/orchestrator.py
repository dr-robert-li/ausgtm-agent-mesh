"""LangGraph + Deep Agents orchestration adapter.

This is the seam where the multi-agent mesh is invoked. The default required
stack is LangChain (tool/model abstraction) + LangGraph (durable state graph,
checkpoints, human-in-the-loop pause/resume) + Deep Agents (a *bounded,
supervisor-orchestrated* team of configured subagents with isolated context).

The adapter degrades to a deterministic stub when the LangChain/LangGraph/Deep
Agents stack is not installed, so the execution flow — including the approval
pause/resume — can be exercised in CI and locally without model credentials.

Design notes (kept aligned with the design pattern in CLAUDE.md):

* **Supervisor-orchestrated, not a free-spawning swarm.** A real implementation
  builds a LangGraph state graph with a supervisor node that delegates to a fixed
  roster of configured Deep Agents subagents (planner, researcher/tool-router,
  code-writer, reviewer). The roster is declared, bounded, and observable. There
  is no uncontrolled self-spawning.
* **LangGraph owns durability.** Long-running runs (>60 min) checkpoint their
  state; the approval gate is a LangGraph interrupt that pauses the graph and
  resumes from the checkpoint when a decision is dispatched back.
* **Model access is gateway-routed.** Agents/tools reach models through the
  LiteLLM-compatible gateway (Anthropic direct or Vertex AI), never by calling
  providers directly. See ``agent_mesh.worker.model_gateway``.
* **Observability is Langfuse-centered.** Spans, prompts, token/cost telemetry
  flow into Langfuse via the LangChain callback handler / OpenTelemetry.

The return value shape is identical regardless of backend so the worker, the
approval ledger, and the tests are framework-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_mesh.contracts.models import TaskRecord


@dataclass
class OrchestrationResult:
    summary: str
    proposed_writes: list[dict] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    # Trace correlation back to Langfuse, when the real stack is wired.
    trace_id: str | None = None


def langgraph_available() -> bool:
    """True when the default required stack (LangGraph) is importable.

    Deep Agents builds on LangGraph, so LangGraph is the load-bearing import. The
    stub path is used whenever it (or model credentials) is unavailable."""
    try:
        import langgraph  # noqa: F401

        return True
    except Exception:
        return False


def deep_agents_available() -> bool:
    try:
        import deepagents  # noqa: F401

        return True
    except Exception:
        return False


def run_mesh(task: TaskRecord) -> OrchestrationResult:
    """Run the agent mesh for a task.

    Returns the result summary plus any *proposed* write actions. Proposed
    writes are NOT executed here; the worker gates them through the approval
    ledger before any Tool Gateway execution.
    """
    if langgraph_available():
        return _run_langgraph(task)
    return _run_stub(task)


def _run_stub(task: TaskRecord) -> OrchestrationResult:
    """Deterministic stand-in for the LangGraph + Deep Agents mesh.

    Heuristic: if the prompt mentions a mutating verb, propose a gated write so
    the approval path is exercised end to end."""
    prompt = task.prompt.lower()
    write_triggers = ("create", "update", "send", "publish", "invoice", "commit", "delete")
    proposed: list[dict] = []
    if any(trigger in prompt for trigger in write_triggers):
        proposed.append(
            {
                "tool_name": "hubspot_create_deal",
                "category": "write",
                "parameters": {"deal_name": task.prompt[:80], "stage": "appointmentscheduled"},
            }
        )
    return OrchestrationResult(
        summary=f"[stub] planned response for: {task.prompt[:120]}",
        proposed_writes=proposed,
        evidence=[],
    )


def _run_langgraph(task: TaskRecord) -> OrchestrationResult:  # pragma: no cover - needs stack
    """Placeholder for the real LangGraph + Deep Agents supervisor run.

    Intentionally minimal: wiring real agents requires model credentials and the
    model gateway base URL, which are out of scope for the importable POC. A real
    implementation would:

      1. Build a model via ``agent_mesh.worker.model_gateway.get_chat_model``.
      2. Construct a Deep Agents supervisor with a bounded subagent roster
         (planner, researcher/tool-router, code-writer, reviewer) and the
         Tool Gateway tools.
      3. Compile a LangGraph with a checkpointer (Postgres in prod) and run it
         with the Langfuse CallbackHandler attached.
      4. Surface proposed writes (never auto-executed) back to the worker.

    The shape of the return value is what the worker consumes regardless of
    backend."""
    return _run_stub(task)
