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

import contextlib
import logging
import os
from dataclasses import dataclass, field

from agent_mesh import observability as obs
from agent_mesh.contracts.models import TaskRecord

# Test-injectable checkpointer hook. When set (by a test), ``_select_checkpointer``
# returns it verbatim instead of building a PostgresSaver from DATABASE_URL. This is the
# documented seam the SqliteSaver-file restart-sim tests use; production never sets it.
_CHECKPOINTER_OVERRIDE = None

# Process-lived PostgresSaver cache, keyed by DSN. ``from_conn_string`` opens a real
# connection; building one per run/resume would leak a connection per task. We build once
# per DSN, reuse it across every ``run_mesh``/``resume_mesh``, and close it via
# ``close_checkpointer()`` at worker shutdown. ``_pg_saver_cm`` retains the context
# manager so its ``__exit__`` closes the underlying connection cleanly.
_PG_SAVER = None
_PG_SAVER_CM = None
_PG_SAVER_DSN: str | None = None


def set_checkpointer_override(checkpointer) -> None:
    """Inject a checkpointer (e.g. a file-backed SqliteSaver) for tests.

    Pass ``None`` to clear. NEVER a purely in-memory saver — it loses exactly what a
    restart loses, which is the property ORCH-02 must prove."""
    global _CHECKPOINTER_OVERRIDE
    _CHECKPOINTER_OVERRIDE = checkpointer


def close_checkpointer() -> None:
    """Close the cached PostgresSaver connection (worker shutdown / test teardown).

    Idempotent. Exits the retained ``from_conn_string`` context manager so the underlying
    connection is released, then clears the cache so a subsequent call rebuilds it."""
    global _PG_SAVER, _PG_SAVER_CM, _PG_SAVER_DSN
    if _PG_SAVER_CM is not None:
        try:
            _PG_SAVER_CM.__exit__(None, None, None)
        finally:
            _PG_SAVER = None
            _PG_SAVER_CM = None
            _PG_SAVER_DSN = None


def _select_checkpointer():
    """Pick the durable LangGraph checkpointer (DUR-02 / ORCH-02).

    * A test-injected override (file-backed SqliteSaver) wins, mirroring
      ``RepositorySQL``'s test-DSN seam.
    * Otherwise, when ``DATABASE_URL`` is set (prod), build a ``PostgresSaver`` from it
      ONCE (cached by DSN, reused across run/resume to avoid a per-task connection leak),
      call ``.setup()`` (idempotent; library-owned sibling schema, NOT a hand-written app
      migration), and return it. Close it via :func:`close_checkpointer` at shutdown.
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

    global _PG_SAVER, _PG_SAVER_CM, _PG_SAVER_DSN
    if _PG_SAVER is not None and _PG_SAVER_DSN == database_url:
        return _PG_SAVER
    # DSN changed (or first build): release any stale saver before rebuilding.
    if _PG_SAVER_CM is not None:
        close_checkpointer()

    # Lazy import mirrors RepositorySQL.__init__: the optional Postgres backend is only
    # imported when a real DSN is present, so the in-memory POC stays importable.
    from langgraph.checkpoint.postgres import PostgresSaver

    # ``from_conn_string`` returns a context manager; retain it so ``close_checkpointer``
    # can ``__exit__`` it, and enter it so the connection stays open for the worker's life.
    cm = PostgresSaver.from_conn_string(database_url)
    saver = cm.__enter__()
    saver.setup()  # idempotent, library-owned sibling schema
    _PG_SAVER = saver
    _PG_SAVER_CM = cm
    _PG_SAVER_DSN = database_url
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


def _task_trace_metadata(task: TaskRecord, *, agent_role: str | None = None) -> dict:
    """Build the shared request-metadata dict for this task's spans (OBS-01).

    Pulls the correlation keys off the durable ``TaskRecord`` so every span the
    worker emits carries tenant_id/client_slug/task_id/session_id/requester_id/
    entrypoint — the keys that correlate model/tool/approval events under one
    trace and keep reads tenant-scoped (T-03-03-03)."""
    return obs.trace_metadata(
        tenant_id=task.tenant_id,
        client_slug=task.client_slug,
        task_id=task.task_id,
        session_id=task.session_id,
        requester_id=task.requester.requester_id,
        entrypoint=str(getattr(task.entrypoint, "value", task.entrypoint)),
        agent_role=agent_role,
        model_route_profile=task.model_route_profile,
        approval_state=str(getattr(task.state, "value", task.state)),
    )


@contextlib.contextmanager
def _task_root_span(task: TaskRecord, span_name: str):
    """Open the per-task OTel root span and yield its 32-hex trace id (OBS-01).

    Restores the inbound W3C ``traceparent`` (stored at the real ingress and copied
    onto ``TaskRecord.metadata``) as the OTel parent context, so the worker's spans
    JOIN the trace started at ingress across the Pub/Sub boundary. When no
    traceparent is present (or OTel is unavailable), a FRESH root trace is started
    (no crash). The ``trace_metadata()`` keys are set as span attributes.

    Yields the trace id (or ``None`` when OTel is unavailable) so callers populate
    ``OrchestrationResult.trace_id`` from the SAME span the run roots under."""
    tracer = obs.get_tracer()
    if tracer is None:
        yield None
        return
    parent = obs.extract_otel_context(task.metadata.get("traceparent"))
    with tracer.start_as_current_span(span_name, context=parent) as span:
        obs.set_span_metadata(span, _task_trace_metadata(task))
        yield obs.span_trace_id(span)


def run_mesh(task: TaskRecord) -> OrchestrationResult:
    """Run the agent mesh for a task.

    Returns the result summary plus any *proposed* write actions. Proposed
    writes are NOT executed here; the worker gates them through the approval
    ledger before any Tool Gateway execution.

    Wrapped in the per-task root span (OBS-01): the inbound traceparent is restored
    so the worker's spans join the ingress trace, and ``trace_id`` is set on the
    result from that span (both the stub and real-graph paths)."""
    with _task_root_span(task, "mesh.run") as trace_id:
        if langgraph_available():
            result = _run_langgraph(task)
        else:
            result = _run_stub(task)
        result.trace_id = trace_id
        return result


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

    OBS-01: when the langfuse v4 ``CallbackHandler`` is available, attach it via
    ``config={"callbacks": [handler]}`` so node/model spans nest under the per-task
    trace and token/cost telemetry lands in Langfuse. The handler is None-safe: with
    langfuse uninstalled/unconfigured ``get_langchain_callback`` returns ``None`` and
    no callback is attached (default suite stays green, no remote tracing).
    """
    config: dict = {"configurable": {"thread_id": task.task_id}}
    handler = obs.get_langchain_callback()
    if handler is not None:  # pragma: no cover - needs langfuse + keys
        config["callbacks"] = [handler]
    return config


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
    worker's completion logic holds. The per-task root span (OBS-01) wraps every
    return path so ``trace_id`` is set on the result regardless of which branch
    (stub / no-checkpoint / durable-resume) is taken.
    """
    with _task_root_span(task, "mesh.resume") as trace_id:
        if not langgraph_available():
            # Stub path: nothing paused via a graph interrupt; terminal no-op.
            return OrchestrationResult(
                summary=f"[stub] resumed after approval: {task.prompt[:120]}",
                proposed_writes=[],
                evidence=[],
                trace_id=trace_id,
            )

        # The stack is present, but a graph resume is only possible when the run was
        # durably checkpointed. ``Command(resume=...)`` REQUIRES a checkpointer; with
        # none configured (no DATABASE_URL, no test override) the run paused via the
        # worker's AWAITING_APPROVAL stash, not a durable graph interrupt, so there is
        # nothing to graph-resume. This is a VALUE check on the selected checkpointer —
        # NOT a blanket try/except that swallows the stack-path resume (which the Task-1
        # acceptance criterion forbids). The write still executes in
        # runner._resume_after_approval under is_approved(); ORCH-03's durable resume is
        # proven by the agents-gated checkpointer test that injects a real saver.
        checkpointer = _select_checkpointer()
        if checkpointer is None:
            return OrchestrationResult(
                summary=(
                    "[mesh] resumed after approval (no durable checkpoint): "
                    f"{task.prompt[:120]}"
                ),
                proposed_writes=[],
                evidence=[],
                trace_id=trace_id,
            )

        from langgraph.types import Command

        from agent_mesh.worker.graph import build_graph

        compiled = build_graph().compile(checkpointer=checkpointer)
        # ``decision`` is the verified boolean only — never an approver_id (SEC-01).
        final_state = compiled.invoke(Command(resume=decision), _graph_config(task))

        return OrchestrationResult(
            summary=final_state.get("review")
            or f"[mesh] resumed and completed: {task.prompt[:120]}",
            proposed_writes=[],
            evidence=[],
            trace_id=trace_id,
        )
