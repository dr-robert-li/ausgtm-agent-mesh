"""SQL-backed repository tests (DUR-01 durability + DUR-02 tenant scoping).

ALL tests are guarded by the ``sql_repo``/``pg_dsn`` fixtures, which
``pytest.skip`` when ``TEST_DATABASE_URL`` is unset — so the default ``make test``
run (no database) stays green and free of external dependencies.

When ``TEST_DATABASE_URL`` is set (to a pgvector-enabled Postgres), these prove:
  * round-trip: task fields AND task_metadata survive a re-read (Pitfall 5);
  * restart-survival: all four DUR-01 state families (tasks + task_events,
    sessions, approvals/tool-calls) survive a pool drop + reopen on the same DSN;
  * cross-tenant: a read scoped to another tenant returns [] (DUR-02);
  * resume-executes-write: the worker pause -> approve -> resume path executes
    the approved write against RepositorySQL (closes Pitfall 3 — the silent-drop
    bug the whole phase exists to prevent), proven against SQL, not the fake.
"""

from __future__ import annotations

from agent_mesh.contracts.enums import (
    ApprovalDecision,
    Entrypoint,
    TaskState,
    ToolCallStatus,
    ToolCategory,
)
from agent_mesh.contracts.models import (
    ApprovalRecord,
    RequesterIdentity,
    TaskRecord,
    ToolCall,
)
from agent_mesh.services import approvals
from agent_mesh.services.dispatch import InProcessDispatcher
from agent_mesh.services.repository import RepositorySQL
from agent_mesh.services.task_service import TaskService, request_from_slack
from agent_mesh.worker.runner import Worker


def _task(tenant_id: str = "t1", *, metadata: dict | None = None) -> TaskRecord:
    return TaskRecord(
        tenant_id=tenant_id,
        client_slug="c",
        entrypoint=Entrypoint.SLACK,
        requester=RequesterIdentity(
            requester_id="slack:U1",
            entrypoint=Entrypoint.SLACK,
            slack_user_id="U1",
            slack_channel_id="C1",
        ),
        session_id="sess-1",
        prompt="do a thing",
        metadata=metadata or {},
    )


def test_round_trip_preserves_fields_and_metadata(sql_repo: RepositorySQL):
    task = _task(metadata={"k": "v", "n": 3})
    sql_repo.create_task(task)

    got = sql_repo.get_task(task.task_id)
    assert got is not None
    assert got.task_id == task.task_id
    assert got.tenant_id == "t1"
    assert got.prompt == "do a thing"
    assert got.session_id == "sess-1"
    # Pitfall 5: metadata must round-trip via task_metadata, not be dropped.
    assert got.metadata == {"k": "v", "n": 3}


def test_restart_survival_all_four_state_families(pg_dsn: str):
    # (a) task + a transition (writes a task row + a task_events audit row)
    repo = RepositorySQL(pg_dsn)
    task = _task()
    repo.create_task(task)
    repo.transition_task(task.task_id, TaskState.QUEUED, note="enqueued")

    # (c) at least one approval_record AND one tool_call row
    call = ToolCall(
        task_id=task.task_id,
        tenant_id="t1",
        tool_name="hubspot.create_deal",
        category=ToolCategory.WRITE,
        approval_required=True,
        status=ToolCallStatus.AWAITING_APPROVAL,
        parameters={"name": "kickoff"},
        requester_id="slack:U1",
    )
    repo.upsert_tool_call(call)
    record = ApprovalRecord(
        approval_request_id="req-1",
        task_id=task.task_id,
        tenant_id="t1",
        tool_call_id=call.tool_call_id,
        payload_hash=approvals.payload_hash(call.parameters),
    )
    repo.upsert_approval(record)

    # Drop the pool, then open a brand-new RepositorySQL on the same DSN.
    repo.close()
    reopened = RepositorySQL(pg_dsn)
    try:
        # (a) task row survives
        got = reopened.get_task(task.task_id)
        assert got is not None and got.state == TaskState.QUEUED.value
        # (a) task_events audit row survives
        events = reopened.list_events(task.task_id, "t1")
        assert any(e.state == TaskState.QUEUED.value for e in events)
        # (b) session row survives (written by create_task's session upsert)
        with reopened._pool.connection() as conn:
            session_row = conn.execute(
                "SELECT session_id, active_task_id FROM sessions WHERE session_id = %s",
                (task.session_id,),
            ).fetchone()
        assert session_row is not None
        assert session_row[1] == task.task_id
        # (c) tool_call AND approval rows survive
        assert reopened.get_tool_call(call.tool_call_id) is not None
        assert reopened.get_approval(record.approval_record_id) is not None
    finally:
        reopened.close()


def test_cross_tenant_reads_return_empty(sql_repo: RepositorySQL):
    from agent_mesh.contracts.enums import ProposalRiskLevel, ProposalType
    from agent_mesh.contracts.models import EvaluationResult, SelfImprovementProposal

    task = _task(tenant_id="t1")
    sql_repo.create_task(task)
    sql_repo.transition_task(task.task_id, TaskState.QUEUED, note="enqueued")
    record = ApprovalRecord(
        approval_request_id="req-1",
        task_id=task.task_id,
        tenant_id="t1",
        payload_hash="abc",
    )
    sql_repo.upsert_approval(record)
    call = ToolCall(
        task_id=task.task_id,
        tenant_id="t1",
        tool_name="hubspot.create_deal",
        category=ToolCategory.WRITE,
        approval_required=True,
        status=ToolCallStatus.AWAITING_APPROVAL,
        parameters={"name": "kickoff"},
        requester_id="slack:U1",
    )
    sql_repo.upsert_tool_call(call)
    proposal = SelfImprovementProposal(
        tenant_id="t1",
        client_slug="c",
        proposal_type=ProposalType.PROMPT_PATCH,
        risk_level=ProposalRiskLevel.LOW,
        title="t",
        rationale="r",
        proposed_patch="p",
    )
    sql_repo.upsert_proposal(proposal)
    sql_repo.upsert_evaluation(
        EvaluationResult(proposal_id=proposal.proposal_id, tenant_id="t1", passed=True)
    )

    # Same id, wrong tenant -> empty across all four scoped reads (DUR-02
    # application-layer isolation): events, approvals, tool_calls, evaluations.
    assert sql_repo.list_events(task.task_id, "t2") == []
    assert sql_repo.list_approvals(task.task_id, "t2") == []
    assert sql_repo.list_tool_calls(task.task_id, "t2") == []
    assert sql_repo.list_evaluations(proposal.proposal_id, "t2") == []
    # Correct tenant still sees the rows.
    assert sql_repo.list_events(task.task_id, "t1") != []
    assert sql_repo.list_approvals(task.task_id, "t1") != []
    assert sql_repo.list_tool_calls(task.task_id, "t1") != []
    assert sql_repo.list_evaluations(proposal.proposal_id, "t1") != []


def test_resume_executes_approved_write_against_sql(sql_repo: RepositorySQL):
    # Drive the real pause -> approve -> resume path against RepositorySQL.
    dispatcher = InProcessDispatcher()
    svc = TaskService(repo=sql_repo, dispatcher=dispatcher)
    worker = Worker(repo=sql_repo)

    req = request_from_slack(
        tenant_id="t1",
        client_slug="c",
        slack_user_id="U1",
        slack_channel_id="C1",
        text="create a hubspot deal",
    )
    task = svc.create_task(req)
    assert worker.process(task.task_id) == "awaiting_approval"

    (record,) = sql_repo.list_approvals(task.task_id, "t1")
    svc.submit_approval_decision(
        record.approval_record_id, ApprovalDecision.APPROVED, "slack:U1", "slack"
    )
    assert sql_repo.get_task(task.task_id).state == "approved"

    assert worker.process(task.task_id) == "completed"

    # Pitfall 3: the approved write must have EXECUTED against SQL — if the
    # resume path silently dropped it, the tool_call would still be awaiting.
    calls = sql_repo.list_tool_calls(task.task_id, "t1")
    assert calls, "no tool calls persisted for the task"
    assert all(c.status == ToolCallStatus.EXECUTED.value for c in calls)
