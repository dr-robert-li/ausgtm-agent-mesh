from agent_mesh.contracts.enums import ApprovalDecision, ToolCategory
from agent_mesh.services import approvals
from agent_mesh.services.dispatch import InProcessDispatcher
from agent_mesh.services.task_service import TaskService, request_from_mcp, request_from_slack
from agent_mesh.tools.gateway import ToolSpec
from agent_mesh.worker.runner import Worker


def test_write_tool_requires_approval():
    assert approvals.requires_approval(ToolCategory.WRITE)
    assert approvals.requires_approval(ToolCategory.FINANCIAL)
    assert not approvals.requires_approval(ToolCategory.READ)


def test_write_tool_spec_must_declare_approval():
    spec = ToolSpec(
        name="bad_write",
        provider="x",
        category=ToolCategory.WRITE,
        description="",
        approval_required=False,
        credential_secret_name=None,
        resource_bindings={},
    )
    import pytest

    with pytest.raises(ValueError):
        spec.validate()


def test_payload_hash_binds_to_exact_payload():
    h1 = approvals.payload_hash({"a": 1, "b": 2})
    h2 = approvals.payload_hash({"b": 2, "a": 1})  # order-independent
    h3 = approvals.payload_hash({"a": 1, "b": 3})  # different value
    assert h1 == h2
    assert h1 != h3


def _service_and_worker(repo):
    dispatcher = InProcessDispatcher()
    svc = TaskService(repo=repo, dispatcher=dispatcher)
    worker = Worker(repo=repo)
    return svc, worker


def test_write_task_pauses_then_completes_after_approval(repo):
    svc, worker = _service_and_worker(repo)
    req = request_from_slack(
        tenant_id="t", client_slug="c", slack_user_id="U1", slack_channel_id="C1",
        text="create a hubspot deal",
    )
    task = svc.create_task(req)
    state = worker.process(task.task_id)
    assert state == "awaiting_approval"

    # Find the opened approval and approve it.
    (approval_id,) = list(repo._approvals.keys())
    svc.submit_approval_decision(approval_id, ApprovalDecision.APPROVED, "slack:U1", "slack")
    assert repo.get_task(task.task_id).state == "approved"

    final = worker.process(task.task_id)
    assert final == "completed"


def test_read_task_completes_without_approval(repo):
    svc, worker = _service_and_worker(repo)
    req = request_from_mcp(
        tenant_id="t", client_slug="c", mcp_subject="svc", text="summarize notes"
    )
    task = svc.create_task(req)
    final = worker.process(task.task_id)
    assert final == "completed"
    assert len(repo._approvals) == 0


def test_rejected_write_does_not_execute(repo):
    svc, worker = _service_and_worker(repo)
    req = request_from_slack(
        tenant_id="t", client_slug="c", slack_user_id="U1", slack_channel_id="C1",
        text="send the invoice",
    )
    task = svc.create_task(req)
    worker.process(task.task_id)
    (approval_id,) = list(repo._approvals.keys())
    svc.submit_approval_decision(approval_id, ApprovalDecision.REJECTED, "slack:U1", "slack")
    assert repo.get_task(task.task_id).state == "rejected"
