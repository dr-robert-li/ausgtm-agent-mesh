"""MCP server exposing mirrored task capabilities.

Uses the official Python MCP SDK (``mcp`` package) with the FastMCP helper and
Streamable HTTP transport. The tools defined here mirror the Slack/API surface
by funneling into the same shared ``TaskService``. Pydantic models from the
contract layer are used for structured input/output.

The ``mcp`` dependency is optional (see pyproject ``runtime`` extra); this module
imports lazily and exposes ``build_mcp_server`` so the rest of the package stays
importable in minimal environments.
"""

from __future__ import annotations

from typing import Any

from agent_mesh.services.task_service import TaskService, request_from_mcp
from agent_mesh.settings import get_settings


def submit_approval_decision_with_token(
    service: TaskService,
    *,
    approval_record_id: str,
    decision: str,
    approval_token: str,
) -> dict[str, Any]:
    """Shared, directly-testable approval gate for the MCP path.

    SEC-01: identical fail-closed enforcement to ``/v1/approvals`` — both ingress
    points share ONE gate so the Critical bypass cannot be reopened by closing
    only HTTP (Pitfall 4). The recorded approver is derived from the verified
    token, never self-asserted. Returns an error dict (rather than raising) so
    the MCP tool can surface it structurally to the client.
    """
    from agent_mesh.contracts.enums import ApprovalDecision
    from agent_mesh.services import approvals

    record = service.repo.get_approval(approval_record_id)
    if record is None:
        return {"error": "not found", "approval_record_id": approval_record_id}

    approver_id = approvals.verify_approval_token(approval_token, record)
    if approver_id is None:
        return {"error": "invalid or missing approval token"}

    decided = service.submit_approval_decision(
        approval_record_id=approval_record_id,
        decision=ApprovalDecision(decision),
        approver_id=approver_id,  # token-derived; never self-asserted
        channel="mcp",
    )
    return {
        "approval_record_id": decided.approval_record_id,
        "decision": str(decided.decision),
    }


def build_mcp_server(service: TaskService | None = None):  # pragma: no cover - needs mcp extra
    """Construct a FastMCP server exposing mirrored task tools.

    Returns a ``FastMCP`` instance. Run it with Streamable HTTP, e.g.::

        server = build_mcp_server()
        server.run(transport="streamable-http")

    or mount its ASGI app alongside the FastAPI ingress.
    """
    from mcp.server.fastmcp import FastMCP

    service = service or TaskService()
    settings = get_settings()
    server = FastMCP("agent-mesh")

    @server.tool()
    def create_task(prompt: str, mcp_subject: str = "mcp-user") -> dict[str, Any]:
        """Create an agent-mesh task. Mirrors the Slack/API ingress capability."""
        req = request_from_mcp(
            tenant_id=settings.tenant_id,
            client_slug=settings.client_slug,
            mcp_subject=mcp_subject,
            text=prompt,
            model_route_profile=settings.model_route_profile,
        )
        task = service.create_task(req)
        return {"task_id": task.task_id, "state": str(task.state)}

    @server.tool()
    def get_task(task_id: str) -> dict[str, Any]:
        """Fetch the current state of a task."""
        task = service.get_task(task_id)
        if task is None:
            return {"error": "not found", "task_id": task_id}
        return task.model_dump(mode="json")

    @server.tool()
    def submit_approval(
        approval_record_id: str, decision: str, approval_token: str
    ) -> dict[str, Any]:
        """Submit an approval decision for a gated write action. Approvals are
        recorded in the same shared ledger used by Slack.

        SEC-01: requires the HMAC ``approval_token`` issued when the approval
        opened; the approver is derived from the verified token (the requester is
        the ``mcp:{subject}`` bound at open time). A missing/invalid token is
        rejected — there is no self-asserted approver_id parameter."""
        return submit_approval_decision_with_token(
            service,
            approval_record_id=approval_record_id,
            decision=decision,
            approval_token=approval_token,
        )

    return server
