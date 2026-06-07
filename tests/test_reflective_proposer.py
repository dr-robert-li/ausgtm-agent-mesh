"""Default-lane (creds-free) tests for the offline reflective proposer (SI-03 / SI-01a).

The proposer is a SEPARATED OFFLINE meta-agent: it mines durable, tenant-scoped
execution traces and emits an INERT ``SelfImprovementProposal`` (status=DRAFT)
through the existing ``self_improvement.reflect_on_task`` seam. It never applies,
promotes, or mutates live state, and it never reads the held-out pool.

These tests prove four invariants without any network or credentials (they use the
``stub_reflector`` fixture from conftest):

* inertness (T-06-08): a DRAFT proposal is created and no PromotionRecord exists;
* tenant-scoping (T-06-09): a tenant-B trace is never mined for a tenant-A proposal;
* held-out isolation (T-06-03b / SI-01a): the proposer's train/dev item-ids and the
  eval harness held-out item-ids are disjoint;
* bounded loop (T-06-10 / SI-03): a never-passing candidate halts at the configured cap.
"""

import pytest

from agent_mesh.contracts.enums import Entrypoint, ProposalStatus, ToolCategory
from agent_mesh.contracts.models import TaskRecord, ToolCall
from agent_mesh.services import eval_harness
from agent_mesh.services import reflective_proposer as rp


def _task(repo, *, tenant_id: str = "tenant-a") -> TaskRecord:
    task = TaskRecord(
        tenant_id=tenant_id,
        client_slug="c",
        entrypoint=Entrypoint.API,
        requester={"requester_id": "u1", "entrypoint": "api"},
        session_id="s1",
        prompt="summarize the kickoff notes",
    )
    return repo.create_task(task)


def _tool_call(task: TaskRecord, *, tenant_id: str, name: str = "search") -> ToolCall:
    return ToolCall(
        task_id=task.task_id,
        tenant_id=tenant_id,
        tool_name=name,
        category=ToolCategory.READ,
        approval_required=False,
        requester_id="u1",
        is_read=True,
    )


def test_proposer_emits_inert_draft(repo, stub_reflector):
    task = _task(repo)
    repo.upsert_tool_call(_tool_call(task, tenant_id=task.tenant_id))

    proposal = rp.propose_from_traces(repo, task, stub_reflector.reflect)

    # Inertness (T-06-08, D-08): a DRAFT proposal, patch-hash bound at creation,
    # and NO promotion of any kind.
    assert proposal.status == ProposalStatus.DRAFT
    assert proposal.task_id == task.task_id
    assert proposal.patch_hash  # bound at creation by reflect_on_task
    assert repo.get_proposal(proposal.proposal_id) is not None
    # No PromotionRecord exists for this proposal (nothing promoted).
    assert repo.get_promotion(proposal.proposal_id) is None
    # The reflector was handed the mined evidence by keyword.
    assert stub_reflector.calls, "reflect_fn was never called with mined evidence"


def test_trace_mining_is_tenant_scoped(repo, stub_reflector):
    task = _task(repo, tenant_id="tenant-a")
    # A legitimate same-tenant trace for this task.
    own = repo.upsert_tool_call(_tool_call(task, tenant_id="tenant-a", name="own"))
    # A trace with the SAME task_id but a DIFFERENT tenant must NOT be mined
    # (DUR-02): same-task-id/different-tenant is what exercises the tenant filter.
    repo.upsert_tool_call(_tool_call(task, tenant_id="tenant-b", name="leaked"))

    rp.propose_from_traces(repo, task, stub_reflector.reflect)

    mined = stub_reflector.calls[-1]["evidence"]
    mined_ids = {c.tool_call_id for c in mined}
    assert own.tool_call_id in mined_ids
    assert all(c.tenant_id == "tenant-a" for c in mined)
    assert "leaked" not in {c.tool_name for c in mined}


def test_holdout_isolation():
    # SI-01a (T-06-03b): the proposer's train/dev item-ids and the eval harness
    # held-out item-ids must be DISJOINT — the held-out set is never an
    # optimization signal (anti-reward-hack, D-02).
    train_ids = rp.train_item_ids()
    holdout_ids = eval_harness.held_out_item_ids()
    assert train_ids, "proposer must expose a non-empty train/dev id surface"
    assert not (train_ids & holdout_ids)
    # And the explicit guard raises when they DO intersect.
    with pytest.raises(rp.HeldOutLeakError):
        rp.assert_holdout_isolation({"x", "holdout-001"}, {"holdout-001"})
    # Disjoint sets pass silently.
    rp.assert_holdout_isolation({"train-001"}, {"holdout-001"})


def test_loop_caps_iterations(repo, stub_reflector):
    # SI-03 (T-06-10): a never-passing candidate must halt at exactly the
    # configured cap — never unbounded. We inject an always-fail gate so the loop
    # cannot exit early (the default real gate always passes by construction).
    task = _task(repo)
    repo.upsert_tool_call(_tool_call(task, tenant_id=task.tenant_id))

    calls = {"n": 0}

    def always_fail_gate(_proposal):
        calls["n"] += 1
        return False

    result = rp.improve_loop(
        repo,
        task,
        stub_reflector.reflect,
        gate_fn=always_fail_gate,
        max_iterations=rp.DEFAULT_MAX_ITERATIONS,
    )

    assert calls["n"] == rp.DEFAULT_MAX_ITERATIONS
    assert result.iterations == rp.DEFAULT_MAX_ITERATIONS
    assert result.passed is False
