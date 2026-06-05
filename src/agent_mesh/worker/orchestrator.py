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

import logging
import os
from dataclasses import dataclass, field

from agent_mesh.contracts.models import TaskRecord

# Test-injectable checkpointer hook. When set (by a test), ``_select_checkpointer``
# returns it verbatim instead of building a PostgresSaver from DATABASE_URL. This is the
# documented seam the SqliteSaver-file restart-sim tests use; production never sets it.
_CHECKPOINTER_OVERRIDE = None


def set_checkpointer_override(checkpointer) -> None:
    """Inject a checkpointer (e.g. a file-backed SqliteSaver) for tests.

    Pass ``None`` to clear. NEVER a purely in-memory saver — it loses exactly what a
    restart loses, which is the property ORCH-02 must prove."""
    global _CHECKPOINTER_OVERRIDE
    _CHECKPOINTER_OVERRIDE = checkpointer


def _select_checkpointer():
    """Pick the durable LangGraph checkpointer (DUR-02 / ORCH-02).

    * A test-injected override (file-backed SqliteSaver) wins, mirroring
      ``RepositorySQL``'s test-DSN seam.
    * Otherwise, when ``DATABASE_URL`` is set (prod), build a ``PostgresSaver`` from it,
      call ``.setup()`` (idempotent; library-owned sibling schema, NOT a hand-written app
      migration), and return it.
    * Otherwise return ``None``: the graph compiles without a durable saver. The worker's
      AWAITING_APPROVAL stash is the durability boundary on that path; the interrupt-based
      durable resume requires a checkpointer and is exercised under the test seam / prod.

    A purely in-memory saver is intentionally never used anywhere (it would defeat the
    restart proof).
    """
    if _CHECKPOINTER_OVERRIDE is not None:
        return _CHECKPOINTER_OVERRIDE
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None
    # Lazy import mirrors RepositorySQL.__init__: the optional Postgres backend is only
    # imported when a real DSN is present, so the in-memory POC stays importable.
    from langgraph.checkpoint.postgres import PostgresSaver

    saver = PostgresSaver.from_conn_string(database_url)
    # ``from_conn_string`` returns a context manager; enter it so the connection stays
    # open for the lifetime of the process worker. ``.setup()`` is idempotent.
    saver = saver.__enter__()
    saver.setup()
    return saver


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


def _graph_config(task: TaskRecord) -> dict:
    """LangGraph invoke config keyed on the tenant-scoped task id (DUR-02).

    ``thread_id`` is ``task.task_id`` — the task was loaded tenant-scoped by the worker,
    so this is never a bare/arbitrary thread_id. The checkpointer keys on ``thread_id``
    only, so binding it to the task id is what keeps a checkpoint from being resumed
    cross-task (T-02-02-03).
    """
    return {"configurable": {"thread_id": task.task_id}}


def _run_langgraph(task: TaskRecord) -> OrchestrationResult:
    """Run the task through the real LangGraph supervisor ``StateGraph``.

    Builds the graph (planner -> researcher/tool-router -> code-writer -> reviewer ->
    write_gate) from :mod:`agent_mesh.worker.graph`, compiles it WITH the durable
    checkpointer selected by :func:`_select_checkpointer` (PostgresSaver in prod,
    file-backed SqliteSaver under the test seam), and invokes it on the task's
    ``thread_id``. If the run pauses at the ``write_gate`` interrupt, the resulting
    state carries ``__interrupt__``; its value's ``proposed_writes`` are surfaced into
    :class:`OrchestrationResult.proposed_writes` so the worker gates them through the
    approval ledger. Proposed writes are NEVER executed here.

    The roster startup-size log fires once here so ORCH-01's "log roster size at
    startup" holds on the real path; it is best-effort and never blocks a run.
    """
    from agent_mesh.worker.graph import build_graph

    # Emit the bounded-roster startup-size log once on the real path (ORCH-01). Guarded
    # because the Deep Agents harness is only needed for live delegation (Phase 3); a
    # failure to build it must not break topology execution.
    try:
        from agent_mesh.worker.roster import roster_size

        logging.getLogger(__name__).info("roster size %d at startup", roster_size())
    except Exception:  # pragma: no cover - defensive; roster_size is pure
        pass

    compiled = build_graph().compile(checkpointer=_select_checkpointer())
    final_state = compiled.invoke({"prompt": task.prompt}, _graph_config(task))

    # When the write_gate interrupt fired, the run is paused: surface the proposed writes
    # so the worker opens the signed-token approval and parks the task in AWAITING_APPROVAL.
    if "__interrupt__" in final_state:
        proposed_writes = final_state["__interrupt__"][0].value.get("proposed_writes", [])
    else:
        proposed_writes = final_state.get("proposed_writes", [])

    return OrchestrationResult(
        summary=final_state.get("review")
        or f"[mesh] completed: {task.prompt[:120]}",
        proposed_writes=proposed_writes,
        evidence=[],
        # trace_id stays unset — Langfuse correlation is Phase 3.
    )


def resume_mesh(task: TaskRecord, decision) -> OrchestrationResult:
    """Resume a paused mesh run from its durable checkpoint after approval (ORCH-03).

    Mirrors the :func:`run_mesh` stub-fallback gate EXACTLY: it branches on
    :func:`langgraph_available`, never on a blanket ``try/except ImportError``. On the
    stub path the run never paused via a graph ``interrupt()`` (it paused via the
    worker's AWAITING_APPROVAL stash), so there is nothing to graph-resume — return a
    terminal result WITHOUT importing ``langgraph.types.Command`` or touching a
    checkpointer, keeping the always-on resume / SEC suite green.

    On the stack path, dispatch ``Command(resume=decision)`` on the SAME ``thread_id``;
    the ``write_gate`` interrupt returns ``decision`` and the graph runs to terminal.

    SECURITY (RF-1 / T-02-02-01): ``decision`` is an ALREADY-VERIFIED boolean only. The
    write is NOT executed here and NOT executed in any graph node — it executes solely in
    ``runner._resume_after_approval`` under ``approvals.is_approved()``. ``resume`` MUST
    NOT carry, and this function MUST NOT pass, an ``approver_id``: the interrupt is the
    pause mechanism, the signed-token ledger is the decision authority.

    Returns a TERMINAL :class:`OrchestrationResult` (``proposed_writes=[]``) so the
    worker's completion logic holds.
    """
    if not langgraph_available():
        # Stub path: nothing paused via a graph interrupt; terminal no-op.
        return OrchestrationResult(
            summary=f"[stub] resumed after approval: {task.prompt[:120]}",
            proposed_writes=[],
            evidence=[],
        )

    from langgraph.types import Command

    from agent_mesh.worker.graph import build_graph

    compiled = build_graph().compile(checkpointer=_select_checkpointer())
    # ``decision`` is the verified boolean only — never an approver_id (SEC-01).
    final_state = compiled.invoke(Command(resume=decision), _graph_config(task))

    return OrchestrationResult(
        summary=final_state.get("review")
        or f"[mesh] resumed and completed: {task.prompt[:120]}",
        proposed_writes=[],
        evidence=[],
        # trace_id stays unset — Langfuse correlation is Phase 3.
    )
