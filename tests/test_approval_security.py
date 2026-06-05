"""SEC-01 / SEC-02 approval-gate security suite.

Closes CONCERNS.md Critical #1: ``/v1/approvals`` (and the MCP ``submit_approval``
tool) previously recorded a self-asserted ``approver_id`` with no signature. The
gate now requires an HMAC-signed, payload-bound, per-record approval token,
verified FAIL-CLOSED at both ingress points, with the recorded approver derived
from the token (never the request body).

This file differs from the rest of the suite in one way: it SETS
``APPROVAL_SIGNING_SECRET`` for the positive cases, because the gate fails closed.
``test_missing_secret_rejects`` explicitly unsets it.
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
    """Most tests here need a configured secret (the gate fails closed).
    Individual tests override/unset as needed."""
    monkeypatch.setenv("APPROVAL_SIGNING_SECRET", _SECRET)
    yield


def _service_and_worker(repo):
    dispatcher = InProcessDispatcher()
    svc = TaskService(repo=repo, dispatcher=dispatcher)
    worker = Worker(repo=repo)
    return svc, worker


def _pause_on_write(repo):
    """Create a write task, run the worker to AWAITING_APPROVAL, and return the
    (svc, worker, task, record, worker-issued token)."""
    svc, worker = _service_and_worker(repo)
    req = request_from_slack(
        tenant_id="t", client_slug="c", slack_user_id="U1", slack_channel_id="C1",
        text="create a hubspot deal",
    )
    task = svc.create_task(req)
    state = worker.process(task.task_id)
    assert state == "awaiting_approval"
    (record,) = repo.list_approvals(task.task_id, "t")
    # Read back the WORKER-ISSUED token (not hand-minted) from task metadata.
    stashed = repo.get_task(task.task_id).metadata["approval_tokens"]
    token = stashed[record.approval_record_id]
    return svc, worker, task, record, token


def _client():
    from fastapi.testclient import TestClient

    from agent_mesh.api import app as app_module

    return TestClient(app_module.app), app_module


# --------------------------------------------------------------------------
# Task 1: token unit behaviors (issue / verify, fail-closed)
# --------------------------------------------------------------------------

def test_token_valid_round_trip(repo):
    _svc, _worker, _task, record, token = _pause_on_write(repo)
    approver = approvals.verify_approval_token(token, record)
    assert approver == "slack:U1"  # the requester bound at open time


def test_token_missing_secret_returns_none(repo, monkeypatch):
    _svc, _worker, _task, record, token = _pause_on_write(repo)
    monkeypatch.delenv("APPROVAL_SIGNING_SECRET", raising=False)
    assert approvals.verify_approval_token(token, record) is None  # FAIL CLOSED


def test_token_tampered_signature_returns_none(repo):
    _svc, _worker, _task, record, token = _pause_on_write(repo)
    # Flip the last char of the signature.
    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert approvals.verify_approval_token(tampered, record) is None


def test_token_expired_returns_none(repo):
    _svc, _worker, _task, record, _token = _pause_on_write(repo)
    expired = approvals.issue_approval_token(record, "slack:U1", ttl_s=-10)
    assert approvals.verify_approval_token(expired, record) is None


def test_token_cross_record_returns_none(repo):
    """A token issued for record A must not verify against record B (SEC-02b)."""
    _svc, _worker, _task_a, record_a, token_a = _pause_on_write(repo)
    # Second task -> second approval record.
    svc, worker = _service_and_worker(repo)
    req = request_from_slack(
        tenant_id="t", client_slug="c", slack_user_id="U1", slack_channel_id="C1",
        text="send the invoice",
    )
    task_b = svc.create_task(req)
    worker.process(task_b.task_id)
    (record_b,) = repo.list_approvals(task_b.task_id, "t")
    assert record_b.approval_record_id != record_a.approval_record_id
    assert approvals.verify_approval_token(token_a, record_b) is None


# --------------------------------------------------------------------------
# Task 2/3: HTTP endpoint enforcement
# --------------------------------------------------------------------------

def test_valid_token_accepted(repo):
    svc, worker, task, record, token = _pause_on_write(repo)
    client, app_module = _client()
    app_module._service = svc  # bind the test repo/service into the app
    resp = client.post(
        "/v1/approvals",
        json={
            "approval_record_id": record.approval_record_id,
            "decision": "approved",
            "approval_token": token,
        },
    )
    assert resp.status_code == 200
    refreshed = repo.get_approval(record.approval_record_id)
    assert refreshed.decision == ApprovalDecision.APPROVED.value
    assert refreshed.approver_id == "slack:U1"


def test_forged_approver_id_rejected(repo):
    svc, worker, task, record, token = _pause_on_write(repo)
    client, app_module = _client()
    app_module._service = svc

    # (a) No/invalid token + spoofed approver_id -> 401, ledger unchanged.
    resp = client.post(
        "/v1/approvals",
        json={
            "approval_record_id": record.approval_record_id,
            "decision": "approved",
            "approver_id": "attacker",
        },
    )
    assert resp.status_code == 401
    assert repo.get_approval(record.approval_record_id).decision == ApprovalDecision.PENDING.value

    # (b) Valid token + spoofed body approver_id -> recorded approver is the
    # TOKEN's requester, the body value is ignored.
    resp = client.post(
        "/v1/approvals",
        json={
            "approval_record_id": record.approval_record_id,
            "decision": "approved",
            "approver_id": "attacker",
            "approval_token": token,
        },
    )
    assert resp.status_code == 200
    assert repo.get_approval(record.approval_record_id).approver_id == "slack:U1"


def test_missing_secret_rejects(repo, monkeypatch):
    svc, worker, task, record, token = _pause_on_write(repo)
    monkeypatch.delenv("APPROVAL_SIGNING_SECRET", raising=False)
    client, app_module = _client()
    app_module._service = svc
    resp = client.post(
        "/v1/approvals",
        json={
            "approval_record_id": record.approval_record_id,
            "decision": "approved",
            "approval_token": token,
        },
    )
    assert resp.status_code == 401  # fail closed
    assert repo.get_approval(record.approval_record_id).decision == ApprovalDecision.PENDING.value


def test_tampered_token_rejected(repo):
    svc, worker, task, record, token = _pause_on_write(repo)
    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
    client, app_module = _client()
    app_module._service = svc
    resp = client.post(
        "/v1/approvals",
        json={
            "approval_record_id": record.approval_record_id,
            "decision": "approved",
            "approval_token": tampered,
        },
    )
    assert resp.status_code == 401


def test_expired_token_rejected(repo):
    svc, worker, task, record, _token = _pause_on_write(repo)
    expired = approvals.issue_approval_token(record, "slack:U1", ttl_s=-10)
    client, app_module = _client()
    app_module._service = svc
    resp = client.post(
        "/v1/approvals",
        json={
            "approval_record_id": record.approval_record_id,
            "decision": "approved",
            "approval_token": expired,
        },
    )
    assert resp.status_code == 401


def test_mutated_payload_invalidates_approval(repo):
    """SEC-02a: mutating a ToolCall payload after approval blocks the write.

    This reuses the worker resume path (depends on 01-01's repaired
    _pending_calls / list_tool_calls). No token needed — the gate under test is
    is_approved's payload re-hash, exercised via the service approve + resume."""
    svc, worker, task, record, _token = _pause_on_write(repo)
    # Approve directly via the service (token gate lives at the endpoint).
    svc.submit_approval_decision(
        record.approval_record_id, ApprovalDecision.APPROVED, "slack:U1", "slack"
    )
    # Mutate the gated tool call's parameters AFTER approval.
    (call,) = [
        c for c in repo.list_tool_calls(task.task_id, "t")
        if c.approval_record_id == record.approval_record_id
    ]
    mutated = call.model_copy(update={"parameters": {"deal_name": "ATTACKER-MUTATED"}})
    repo.upsert_tool_call(mutated)

    worker.process(task.task_id)

    (after,) = [
        c for c in repo.list_tool_calls(task.task_id, "t")
        if c.approval_record_id == record.approval_record_id
    ]
    assert after.status != ToolCallStatus.EXECUTED.value  # write did NOT execute


def test_approval_not_replayable_across_tasks(repo):
    """SEC-02b: task A's token presented for task B's record -> 401."""
    _svc_a, _w_a, _task_a, record_a, token_a = _pause_on_write(repo)
    svc_b, worker_b = _service_and_worker(repo)
    req = request_from_slack(
        tenant_id="t", client_slug="c", slack_user_id="U1", slack_channel_id="C1",
        text="send the invoice",
    )
    task_b = svc_b.create_task(req)
    worker_b.process(task_b.task_id)
    (record_b,) = repo.list_approvals(task_b.task_id, "t")

    client, app_module = _client()
    app_module._service = svc_b
    resp = client.post(
        "/v1/approvals",
        json={
            "approval_record_id": record_b.approval_record_id,
            "decision": "approved",
            "approval_token": token_a,  # A's token against B's record
        },
    )
    assert resp.status_code == 401
    assert repo.get_approval(record_b.approval_record_id).decision == ApprovalDecision.PENDING.value


# --------------------------------------------------------------------------
# Task 2/3: MCP parity
# --------------------------------------------------------------------------

def test_mcp_submit_approval_requires_token(repo):
    from agent_mesh.api.mcp_server import submit_approval_decision_with_token

    svc, worker, task, record, token = _pause_on_write(repo)

    # Forged/no token -> rejected, ledger unchanged.
    rejected = submit_approval_decision_with_token(
        svc,
        approval_record_id=record.approval_record_id,
        decision="approved",
        approval_token="",
    )
    assert rejected.get("error")
    assert repo.get_approval(record.approval_record_id).decision == ApprovalDecision.PENDING.value

    # Valid token -> recorded approver is the token's requester.
    ok = submit_approval_decision_with_token(
        svc,
        approval_record_id=record.approval_record_id,
        decision="approved",
        approval_token=token,
    )
    assert ok.get("approval_record_id") == record.approval_record_id
    assert repo.get_approval(record.approval_record_id).approver_id == "slack:U1"
