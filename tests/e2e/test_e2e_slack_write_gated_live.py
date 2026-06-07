"""E2E-01 opt-in LIVE variant — real but reversible draft/sandbox write (D-07).

The whole module is ``@pytest.mark.live`` (deselected without ``-m live``) and SKIPS
inline when ``HUBSPOT_PRIVATE_APP_TOKEN`` is unset — so ``make test`` never reaches
HubSpot and never requires the SDK. NOTE: this gates on the HubSpot **provider token**
directly (NOT the shared ``live_creds`` fixture, which gates on model/gateway creds — a
different credential axis, see 07-PATTERNS SP-2 row 1; analog tests/test_hubspot_live.py).

This mirrors the default-lane chain (``test_e2e_slack_write_gated.py``) but plugs the
REAL seam: the worker is built with a real ``ToolGateway.from_manifest(...)`` so the
resumed, approval-gated write executes a REAL deal in the HubSpot dev/test SANDBOX
(``hubspot_create_deal`` -> ``resource_bindings.pipeline_id``, hubspot.py:87-88) rather
than the default-lane stub. The write is real-but-REVERSIBLE: a sandbox deal, never a
production-grade committed mutation (D-07). The credential is resolved only at execution
time inside ``gateway.execute`` (D-02) — never handed to the agent.

The chain remains the platform sentence: Slack request -> task -> worker write-gate
pause -> token-gated approval -> resume -> real sandbox write -> completion.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.live  # whole module is opt-in live lane (SP-3)

_MANIFEST = Path(__file__).resolve().parents[1] / "manifests" / "tool_pack_manifest.yaml"
_SECRET = "test-approval-secret"


def _token_present() -> bool:
    return bool(os.getenv("HUBSPOT_PRIVATE_APP_TOKEN"))


def _client():
    from fastapi.testclient import TestClient

    from agent_mesh.api import app as app_module

    return TestClient(app_module.app), app_module


def _slack_event_body(text: str) -> dict:
    return {
        "type": "event_callback",
        "event": {"type": "message", "user": "U1", "channel": "C1", "text": text},
    }


def test_e2e_slack_write_gated_live_sandbox_deal(repo, monkeypatch):
    """The full Slack -> approval -> resume chain ending in a REAL reversible HubSpot
    SANDBOX deal through the approval gate + sandbox. Skips loudly without the token."""
    if not _token_present():
        pytest.skip(
            "HUBSPOT_PRIVATE_APP_TOKEN unset; live E2E-01 draft/sandbox write skipped"
        )

    from agent_mesh.contracts.enums import ApprovalDecision
    from agent_mesh.services.dispatch import InProcessDispatcher
    from agent_mesh.services.task_service import TaskService
    from agent_mesh.tools.credentials import EnvCredentialResolver
    from agent_mesh.tools.gateway import ToolGateway
    from agent_mesh.worker.runner import Worker

    monkeypatch.setenv("APPROVAL_SIGNING_SECRET", _SECRET)
    monkeypatch.delenv("SLACK_SIGNING_SECRET", raising=False)

    svc = TaskService(repo=repo, dispatcher=InProcessDispatcher())
    # The REAL seam: a worker with a real ToolGateway + env-backed resolver, so the
    # resumed gated write hits HubSpot's sandbox (D-02/D-07), not the stub.
    gateway = ToolGateway.from_manifest(_MANIFEST)
    worker = Worker(repo=repo, tool_gateway=gateway, resolver=EnvCredentialResolver())
    client, app_module = _client()
    app_module._service = svc  # SP-1 rebind so HTTP mutates the test repo

    # --- Slack ingress (HTTP), write-trigger verb. ---
    resp = client.post(
        "/slack/events",
        content=json.dumps(_slack_event_body("create a hubspot deal for kickoff")),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200

    assert len(repo._tasks) == 1, "expected exactly one task created by /slack/events"
    task = next(iter(repo._tasks.values()))
    task_id = task.task_id
    tenant = task.tenant_id

    # --- worker -> write-gate pause. ---
    assert worker.process(task_id) == "awaiting_approval"
    (record,) = repo.list_approvals(task_id, tenant)
    token = repo.get_task(task_id).metadata["approval_tokens"][record.approval_record_id]

    # --- token-gated approval (HTTP). ---
    decision_resp = client.post(
        "/v1/approvals",
        json={
            "approval_record_id": record.approval_record_id,
            "decision": "approved",
            "approval_token": token,
        },
    )
    assert decision_resp.status_code == 200
    assert repo.get_approval(record.approval_record_id).decision == ApprovalDecision.APPROVED.value

    # --- worker resume -> REAL sandbox write -> completion. ---
    assert worker.process(task_id) == "completed"

    (gated_call,) = [
        c for c in repo.list_tool_calls(task_id, tenant)
        if c.approval_record_id == record.approval_record_id
    ]
    result = gated_call.result
    # A REAL sandbox write ran — NOT the deterministic stub.
    assert result is not None
    assert result.get("stub") is not True, f"got stub, expected a real sandbox write: {result!r}"
    # Reversible sandbox artifact: a real deal id, created in the sandbox pipeline
    # (hubspot_create_deal output schema: deal_id/status/pipeline_id) — not a
    # production-grade committed mutation.
    assert result.get("deal_id")
    assert result.get("status") == "created"
