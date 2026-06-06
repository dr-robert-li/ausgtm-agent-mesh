"""ORCH-01 coverage: a real LangGraph StateGraph delegates planner ->
researcher/tool-router -> code-writer -> reviewer over a bounded, declared 4-member
Deep Agents roster, while the deterministic stub remains the no-stack fallback.

Two layers (mirrors the research Validation Architecture):

* ``test_stub_fallback`` — always-on, no agents stack required. Asserts the public
  ``run_mesh`` entry returns an ``OrchestrationResult`` and that a mutating-verb prompt
  yields a gated proposed write. The contract holds on BOTH the real-graph path (when
  the ``.[agents]`` stack is installed) and the deterministic stub path.
* ``test_real_graph_delegation`` / ``test_roster_is_bounded_at_four`` — agents-gated via
  the conftest ``agents_stack`` fixture; skip cleanly when the stack is absent. They
  prove the four nodes genuinely execute (role-distinct state) and the declared roster
  is exactly four with the auto general-purpose subagent excluded (T-02-01-E).
"""

from __future__ import annotations

from agent_mesh.contracts.enums import Entrypoint
from agent_mesh.contracts.models import TaskRecord
from agent_mesh.worker import orchestrator


def _task(repo, prompt: str) -> TaskRecord:
    task = TaskRecord(
        tenant_id="t",
        client_slug="c",
        entrypoint=Entrypoint.API,
        requester={"requester_id": "u1", "entrypoint": "api"},
        session_id="s1",
        prompt=prompt,
    )
    return repo.create_task(task)


def test_stub_fallback(repo):
    """Always-on: ``run_mesh`` returns an OrchestrationResult; a mutating prompt yields
    a gated proposed write. Holds with or without the agents stack installed."""
    # Non-mutating prompt: a result with a summary, no proposed writes.
    read_task = _task(repo, "summarize the quarterly report")
    read_result = orchestrator.run_mesh(read_task)
    assert isinstance(read_result, orchestrator.OrchestrationResult)
    assert read_result.summary
    assert read_result.proposed_writes == []
    # OBS-01 (Phase 3) closes the prior P2 gap: trace_id is now SET per task from
    # the per-task OTel root span (32-hex) when the OTel SDK is importable.
    assert read_result.trace_id is not None
    assert len(read_result.trace_id) == 32

    # Mutating prompt: the approval path is exercised — exactly one gated write.
    write_task = _task(repo, "create a new HubSpot deal for ACME Corp")
    write_result = orchestrator.run_mesh(write_task)
    assert isinstance(write_result, orchestrator.OrchestrationResult)
    assert len(write_result.proposed_writes) == 1
    assert write_result.proposed_writes[0]["category"] == "write"


def test_stub_path_directly_returns_result(repo):
    """The deterministic stub path itself (independent of which backend ``run_mesh``
    selects) returns the contract shape, so the no-stack fallback is proven even when
    this environment HAS the agents stack."""
    task = _task(repo, "delete the stale draft")
    result = orchestrator._run_stub(task)
    assert isinstance(result, orchestrator.OrchestrationResult)
    assert len(result.proposed_writes) == 1
    assert result.proposed_writes[0]["category"] == "write"


def test_real_graph_delegation(repo, agents_stack):
    """Agents-gated: ``run_mesh`` routes through the real 4-node StateGraph. The four
    nodes execute and populate role-distinct state, and the OrchestrationResult carries
    the reviewer summary plus the gated write."""
    from agent_mesh.worker.graph import build_graph

    # The four nodes genuinely run and each writes its own role-distinct field.
    compiled = build_graph().compile()  # no durable-state saver in this plan
    state = compiled.invoke({"prompt": "create a new HubSpot deal for ACME Corp"})
    for key in ("plan", "research", "code", "review"):
        assert key in state and state[key], f"node {key!r} did not populate state"
    # Role-distinct: each field carries its own role tag, not a shared pass-through.
    assert state["plan"] != state["research"] != state["code"] != state["review"]

    # run_mesh on the real path (langgraph_available() is True here) returns the
    # reviewer-derived summary and surfaces the gated write.
    assert orchestrator.langgraph_available()
    task = _task(repo, "create a new HubSpot deal for ACME Corp")
    result = orchestrator.run_mesh(task)
    assert isinstance(result, orchestrator.OrchestrationResult)
    assert result.summary
    assert len(result.proposed_writes) == 1
    assert result.proposed_writes[0]["category"] == "write"


def test_roster_is_bounded_at_four(agents_stack):
    """Agents-gated: the declared roster is exactly four and the auto general-purpose
    subagent is excluded (T-02-01-E bounded-roster mitigation)."""
    from agent_mesh.worker import roster

    assert roster.roster_size() == 4
    names = roster.effective_roster_names()
    assert names == frozenset({"planner", "researcher", "code_writer", "reviewer"})
    assert roster.GENERAL_PURPOSE_NAME not in names

    # build_roster() must not raise: it disables general-purpose and asserts the bound.
    built = roster.build_roster()
    assert built is not None
