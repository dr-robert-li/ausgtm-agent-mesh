"""FastAPI ingress application.

Endpoints:
- ``GET  /healthz``            — liveness/readiness.
- ``POST /v1/tasks``           — canonical API task creation.
- ``GET  /v1/tasks/{id}``      — task status.
- ``POST /slack/events``       — Slack Events API ingress (signature-verified).
- ``POST /v1/approvals``       — approval decision callback (Slack or MCP).
- ``POST /mcp``                — MCP Streamable HTTP entry point (see api.mcp_server).

Slack and the API both translate into the shared ``TaskService`` so capabilities
are mirrored across entrypoints. The MCP server module mounts the same service.
"""

from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException, Request, Response

from agent_mesh.api.slack_verify import verify_slack_signature
from agent_mesh.contracts.enums import ApprovalDecision
from agent_mesh.contracts.models import TaskRequest
from agent_mesh.services.task_service import TaskService, request_from_slack
from agent_mesh.settings import get_settings

app = FastAPI(title="Agent Mesh Ingress", version="0.2.0")
_settings = get_settings()
_service = TaskService()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


@app.post("/v1/tasks")
def create_task(request: TaskRequest) -> dict[str, str]:
    """Canonical API ingress. Slack/MCP funnel into the same TaskService."""
    task = _service.create_task(request)
    return {"task_id": task.task_id, "state": str(task.state)}


@app.get("/v1/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, object]:
    task = _service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task.model_dump(mode="json")


@app.post("/slack/events")
async def slack_events(request: Request) -> Response:
    """Slack Events API ingress with signature verification and fast ack.

    Slack requires a response within 3 seconds; we verify, enqueue, and return
    immediately. The long-running work happens in the worker."""
    body = await request.body()
    if not verify_slack_signature(
        body=body,
        timestamp=request.headers.get("X-Slack-Request-Timestamp"),
        signature=request.headers.get("X-Slack-Signature"),
        tolerance_s=_settings.slack_timestamp_tolerance_s,
    ):
        raise HTTPException(status_code=401, detail="invalid slack signature")

    payload = json.loads(body or b"{}")

    # URL verification handshake.
    if payload.get("type") == "url_verification":
        return Response(content=payload.get("challenge", ""), media_type="text/plain")

    event = payload.get("event", {})
    if event.get("type") in {"app_mention", "message"} and event.get("text"):
        req = request_from_slack(
            tenant_id=_settings.tenant_id,
            client_slug=_settings.client_slug,
            slack_user_id=event.get("user", "unknown"),
            slack_channel_id=event.get("channel", "unknown"),
            text=event["text"],
            model_route_profile=_settings.model_route_profile,
        )
        _service.create_task(req)

    # Fast acknowledgement; processing continues asynchronously.
    return Response(status_code=200)


@app.post("/v1/approvals")
def submit_approval(payload: dict) -> dict[str, str]:
    """Approval decision callback shared by Slack and MCP requesters."""
    try:
        record = _service.submit_approval_decision(
            approval_record_id=payload["approval_record_id"],
            decision=ApprovalDecision(payload["decision"]),
            approver_id=payload["approver_id"],
            channel=payload.get("channel", "api"),
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"missing field: {exc}") from exc
    return {"approval_record_id": record.approval_record_id, "decision": str(record.decision)}
