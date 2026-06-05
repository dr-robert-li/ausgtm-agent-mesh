"""ORCH-03 interrupt-based HITL: pause -> verified resume -> write gated.

This suite proves the 02-02 contract: a proposed write pauses the run (the worker parks
the task in AWAITING_APPROVAL after the reviewer/write_gate surfaces the proposed write),
the legitimate verified path resumes it to COMPLETED with the write executed, and the
load-bearing SEC-01/SEC-02 invariants hold THROUGH the new ``resume_mesh`` resume flow:

* SEC-01 (T-02-02-01): a forged / self-asserted approver carried in ``Command(resume=...)``
  CANNOT approve — the recorded approver is derived ONLY from the verified token, never
  from the resumed value (which is a bare verified boolean the graph never trusts as
  identity).
* SEC-02a (T-02-02-02): mutating a tool-call payload AFTER approval invalidates the write;
  ``approvals.is_approved()`` re-hash fails and the Tool Gateway ``.execute`` does not run.

The SEC invariants are exercised through the ledger + worker resume path and are
ALWAYS-ON (they do not need the agents stack). A separate agents-gated assertion proves
the real graph genuinely pauses at the ``interrupt()`` and resumes from the durable
checkpoint via ``resume_mesh``.
"""

from __future__ import annotations

import pytest

from agent_mesh.contracts.enums import ApprovalDecision, ToolCallStatus
from agent_mesh.services import approvals
from agent_mesh.services.dispatch import InProcessDispatcher
from agent_mesh.services.task_service import TaskService, request_from_slack
from agent_mesh.worker.runner import Worker

_SECRET = "test-approval-secret"


@pytest.fixture(autouse=True)
def _signing_secret(monkeypatch):
    """The approval gate fails closed: token issue/verify needs a configured secret.
    Mirrors test_approval_security.py's autouse fixture so verify_approval_token works."""
    monkeypatch.setenv("APPROVAL_SIGNING_SECRET", _SECRET)
    yield


def _service_and_worker(repo):
    dispatcher = InProcessDispatcher()
    svc = TaskService(repo=repo, dispatcher=dispatcher)
    worker = Worker(repo=repo)
    return svc, worker


def _pause_on_write(repo):
    """Create a mutating task, run the worker to AWAITING_APPROVAL, and return
    (svc, worker, task, record, worker-issued token). Mirrors test_approval_security."""
    svc, worker = _service_and_worker(repo)
    req = request_from_slack(
        tenant_id="t", client_slug="c", slack_user_id="U1", slack_channel_id="C1",
        text="create a hubspot deal",
    )
    task = svc.create_task(req)
    state = worker.process(task.task_id)
    assert state == "awaiting_approval"
    (record,) = repo.list_approvals(task.task_id, "t")
    stashed = repo.get_task(task.task_id).metadata["approval_tokens"]
    token = stashed[record.approval_record_id]
    return svc, worker, task, record, token


# --------------------------------------------------------------------------
# (1) A mutating prompt pauses the run for approval; a worker-issued token exists.
# --------------------------------------------------------------------------
def test_mutating_prompt_pauses_with_issued_token(repo):
    _svc, _worker, task, record, token = _pause_on_write(repo)
    # The run is paused: a write-class action surfaced and a per-record signed token
    # was issued and stashed durably (the pause + checkpoint mechanism on the worker).
    assert record.decision == ApprovalDecision.PENDING.value
    assert token  # worker-issued, payload-bound token
    assert approvals.verify_approval_token(token, record) == "slack:U1"


# --------------------------------------------------------------------------
# (2) The legitimate verified path resumes to COMPLETED and the write executes.
# --------------------------------------------------------------------------
def test_verified_resume_completes_and_executes_write(repo):
    svc, worker, task, record, _token = _pause_on_write(repo)
    # Approve via the legitimate ledger path (token gate lives at the endpoint; here we
    # record the verified decision via the service, which moves the task to APPROVED and
    # re-dispatches). The approver is the verified requester.
    svc.submit_approval_decision(
        record.approval_record_id, ApprovalDecision.APPROVED, "slack:U1", "slack"
    )
    # Worker resumes: resume_mesh releases the paused graph (no-op on the stub env), then
    # the write executes ONLY here under is_approved().
    state = worker.process(task.task_id)
    assert state == "completed"
    (call,) = [
        c for c in repo.list_tool_calls(task.task_id, "t")
        if c.approval_record_id == record.approval_record_id
    ]
    assert call.status == ToolCallStatus.EXECUTED.value


# --------------------------------------------------------------------------
# (3) SEC-01 / T-02-02-01: a forged/self-asserted approver via resume is rejected.
#     The recorded approver is the TOKEN-derived id, never a body/resume-supplied one.
# --------------------------------------------------------------------------
def test_resume_carries_no_identity_channel(repo):
    """SEC-01 / T-02-02-01 structural mitigation: the resume path carries NO identity.

    ``runner._resume_after_approval`` calls ``orchestrator.resume_mesh(task, True)`` — the
    ``decision`` is a bare boolean, so there is no channel through which a self-asserted
    approver could ride into the ledger via the resumed value. The recorded approver is
    derived SOLELY from the verified token at decision time. We prove this by approving
    with the legitimate requester and asserting the recorded approver is the token-derived
    id, while the worker (which IS what releases the graph via resume_mesh) never alters it.
    """
    import inspect

    from agent_mesh.worker import orchestrator, runner

    # Structural: resume_mesh's signature takes (task, decision) — there is no approver_id
    # parameter, so identity simply cannot be passed through the resume call.
    params = list(inspect.signature(orchestrator.resume_mesh).parameters)
    assert params == ["task", "decision"]
    # And the runner passes a literal boolean, never an identity, into resume_mesh.
    runner_src = inspect.getsource(runner.Worker._resume_after_approval)
    assert "resume_mesh(task, True)" in runner_src
    assert "approver" not in runner_src.split("resume_mesh", 1)[1].split("\n", 1)[0]

    svc, worker, task, record, token = _pause_on_write(repo)
    # The ONLY trusted approver derivation is verify_approval_token (FAIL CLOSED, SEC-01).
    assert approvals.verify_approval_token(token, record) == "slack:U1"
    # Approve via the legitimate verified path; the worker then resumes via resume_mesh.
    svc.submit_approval_decision(
        record.approval_record_id, ApprovalDecision.APPROVED, "slack:U1", "slack"
    )
    worker.process(task.task_id)
    # resume_mesh(task, True) released the gate carrying only a boolean — the recorded
    # approver remains the token-derived requester, never a resume-supplied identity.
    assert repo.get_approval(record.approval_record_id).approver_id == "slack:U1"


# --------------------------------------------------------------------------
# (4) SEC-02a / T-02-02-02: a mutated payload after approval blocks the write,
#     THROUGH the new resume_mesh resume flow.
# --------------------------------------------------------------------------
def test_mutated_payload_blocks_write_through_resume(repo):
    svc, worker, task, record, _token = _pause_on_write(repo)
    svc.submit_approval_decision(
        record.approval_record_id, ApprovalDecision.APPROVED, "slack:U1", "slack"
    )
    # Mutate the gated call's parameters AFTER approval — invalidates the payload re-hash.
    (call,) = [
        c for c in repo.list_tool_calls(task.task_id, "t")
        if c.approval_record_id == record.approval_record_id
    ]
    mutated = call.model_copy(update={"parameters": {"deal_name": "ATTACKER-MUTATED"}})
    repo.upsert_tool_call(mutated)

    # Resume: resume_mesh releases the (stub no-op) graph, but is_approved() re-hash fails.
    worker.process(task.task_id)

    (after,) = [
        c for c in repo.list_tool_calls(task.task_id, "t")
        if c.approval_record_id == record.approval_record_id
    ]
    assert after.status != ToolCallStatus.EXECUTED.value  # write did NOT execute


# --------------------------------------------------------------------------
# (5) Agents-gated: the REAL graph pauses at interrupt() and resume_mesh resumes it
#     from a durable checkpoint to terminal — proving the interrupt is the pause
#     mechanism (DUR-02 thread_id == tenant-scoped task_id).
# --------------------------------------------------------------------------
def test_real_graph_interrupt_pauses_and_resume_mesh_resumes(repo, agents_stack, tmp_path):
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver

    from agent_mesh.contracts.enums import Entrypoint
    from agent_mesh.contracts.models import TaskRecord
    from agent_mesh.worker import orchestrator

    # File-backed durable checkpointer (NEVER a purely in-memory saver). Inject it via the
    # documented orchestrator seam so run_mesh / resume_mesh compile WITH it.
    db = tmp_path / "cp.sqlite"
    conn = sqlite3.connect(str(db), check_same_thread=False)
    saver = SqliteSaver(conn)
    orchestrator.set_checkpointer_override(saver)
    try:
        task = repo.create_task(
            TaskRecord(
                tenant_id="t", client_slug="c", entrypoint=Entrypoint.API,
                requester={"requester_id": "u1", "entrypoint": "api"},
                session_id="s1", prompt="create a new HubSpot deal for ACME Corp",
            )
        )
        # DUR-02: the run is keyed on thread_id == the tenant-scoped task_id.
        paused = orchestrator.run_mesh(task)
        # The write_gate interrupt fired: the proposed write is surfaced (paused signal).
        assert len(paused.proposed_writes) == 1
        assert paused.proposed_writes[0]["category"] == "write"

        # resume_mesh dispatches Command(resume=True) on the SAME thread_id; the graph
        # resumes from the durable checkpoint and reaches terminal (proposed_writes=[]).
        resumed = orchestrator.resume_mesh(task, True)
        assert resumed.proposed_writes == []
        assert resumed.summary
    finally:
        orchestrator.set_checkpointer_override(None)
        conn.close()
