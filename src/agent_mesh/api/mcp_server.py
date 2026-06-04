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
        approval_record_id: str, decision: str, approver_id: str
    ) -> dict[str, Any]:
        """Submit an approval decision for a gated write action. Approvals are
        recorded in the same shared ledger used by Slack."""
        from agent_mesh.contracts.enums import ApprovalDecision

        record = service.submit_approval_decision(
            approval_record_id=approval_record_id,
            decision=ApprovalDecision(decision),
            approver_id=approver_id,
            channel="mcp",
        )
        return {
            "approval_record_id": record.approval_record_id,
            "decision": str(record.decision),
        }

    return server
