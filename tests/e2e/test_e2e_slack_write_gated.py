"""E2E-01 default-lane proof — the headline platform sentence, creds-free.

ROADMAP SC-1: a Slack request flows ingress -> task -> worker write-gate pause ->
token-gated approval -> resume -> completion, asserted **through the real FastAPI
app surface** (D-03), with NO credentials (D-01/D-02). The provider write is
exercised as the deterministic in-process stub here; the real reversible write is
proven by the opt-in live variant (``test_e2e_slack_write_gated_live.py``, D-07).

Why through HTTP and not ``worker.process`` directly (smoke.py does the latter):
this test must prove the *actual ingress + approval-callback HTTP surface* carries
the chain, not an in-memory shortcut. Two HTTP legs are driven:
``POST /slack/events`` (fast-ack task creation) and ``POST /v1/approvals`` (the
token-gated decision callback). The worker legs are driven directly because
``/slack/events`` is a fast-ack that does NOT auto-run the worker.

THE keystone (SP-1 / must_haves key_link): ``app.py`` builds ``_service =
TaskService()`` at IMPORT time with its OWN repository. A TestClient call hits that
module global, NOT this test's repo/svc — so after building the client we REBIND
``app_module._service = svc``. Without the rebind the repo assertions read a
different store than the HTTP request mutated (green-on-a-lie).

NO live marker on this module — it is part of the default ``make test`` suite.
"""

from __future__ import annotations

import json

import pytest

from agent_mesh.contracts.enums import ApprovalDecision
from agent_mesh.services.dispatch import InProcessDispatcher
from agent_mesh.services.task_service import TaskService
from agent_mesh.worker.runner import Worker

_SECRET = "test-approval-secret"


@pytest.fixture(autouse=True)
def _e2e_env(monkeypatch):
    """The token gate fails closed, so APPROVAL_SIGNING_SECRET must be set for the
    ``/v1/approvals`` leg (mirror test_approval_security.py:27-32). SLACK_SIGNING_SECRET
    is explicitly UNSET so the default-lane Slack signature check bypasses
    (slack_verify.py:26-29 returns True with no secret) — deleting it rather than
    relying on "leave it unset" guards against a polluted dev env that exports it."""
    monkeypatch.setenv("APPROVAL_SIGNING_SECRET", _SECRET)
    monkeypatch.delenv("SLACK_SIGNING_SECRET", raising=False)
    yield


def _client():
    """TestClient over the real FastAPI app + the app module for the _service rebind."""
    from fastapi.testclient import TestClient

    from agent_mesh.api import app as app_module

    return TestClient(app_module.app), app_module


def _slack_event_body(text: str) -> dict:
    """A minimal Slack Events API message payload (app.py:85-94 reads event.type/text)."""
    return {
        "type": "event_callback",
        "event": {
            "type": "message",
            "user": "U1",
            "channel": "C1",
            "text": text,
        },
    }


def test_e2e_slack_request_write_gated_to_completion(repo):
    """Slack -> task -> write-gate pause -> token-gated approval -> resume -> completed,
    driven through the real FastAPI app (POST /slack/events + POST /v1/approvals)."""
    # Build the test's service/worker on the conftest ``repo`` fixture (fresh
    # InMemoryRepository), then REBIND it into the app so the HTTP surface mutates
    # THIS repo (SP-1, the must_haves key_link).
    svc = TaskService(repo=repo, dispatcher=InProcessDispatcher())
    worker = Worker(repo=repo)
    client, app_module = _client()
    app_module._service = svc  # MANDATORY rebind — HTTP must hit the test's repo

    # --- Leg 1: Slack ingress (HTTP). "create ..." is a write-trigger verb
    # (orchestrator._run_stub write_triggers) -> the worker will gate a write. ---
    resp = client.post(
        "/slack/events",
        content=json.dumps(_slack_event_body("create a hubspot deal for kickoff")),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200  # fast ack

    # Resolve the task the ingress created. ``/slack/events`` returns an empty
    # 200 ack (no task_id in the body) and the repo Protocol has no ``list_tasks``;
    # the test owns a fresh single-task repo, so read the lone task back from it.
    # ``assert len == 1`` makes a future second-task regression fail loudly rather
    # than silently grabbing the wrong record.
    assert len(repo._tasks) == 1, "expected exactly one task created by /slack/events"
    task = next(iter(repo._tasks.values()))
    task_id = task.task_id
    # The ingress used app._settings.tenant_id (captured at import), NOT "t" — read
    # the tenant off the created record so approval lookups never miss (Rule 3).
    tenant = task.tenant_id

    # --- Leg 2: worker runs to the write-gate pause. ---
    assert worker.process(task_id) == "awaiting_approval"
    (record,) = repo.list_approvals(task_id, tenant)

    # Read back the WORKER-ISSUED token (not hand-minted) from task metadata
    # (test_approval_security.py:54-56). The /v1/approvals endpoint derives the
    # approver from this token (SEC-01).
    stashed = repo.get_task(task_id).metadata["approval_tokens"]
    token = stashed[record.approval_record_id]

    # --- Leg 3: approval decision callback (HTTP). ---
    decision_resp = client.post(
        "/v1/approvals",
        json={
            "approval_record_id": record.approval_record_id,
            "decision": "approved",
            "approval_token": token,
        },
    )
    assert decision_resp.status_code == 200
    refreshed = repo.get_approval(record.approval_record_id)
    assert refreshed.decision == ApprovalDecision.APPROVED.value
    assert refreshed.approver_id == "slack:U1"  # token-derived requester, not the body

    # --- Leg 4: worker resumes and completes. ---
    assert worker.process(task_id) == "completed"

    # The gated write did NOT hit a real provider: Worker(repo=repo) has no tool
    # gateway, so _execute returns the deterministic stub (runner.py:214-220).
    (gated_call,) = [
        c for c in repo.list_tool_calls(task_id, tenant)
        if c.approval_record_id == record.approval_record_id
    ]
    assert gated_call.result is not None
    assert gated_call.result.get("stub") is True  # default-lane stub, no real write
