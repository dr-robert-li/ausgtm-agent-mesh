"""Shared task service.

This is the single entry point every ingress (Slack, MCP, API) uses to create
and dispatch tasks, guaranteeing mirrored capabilities. It is also where the
worker resumes tasks and where approvals are recorded. Keeping all of this in
one module makes the orchestrator the source of truth regardless of entrypoint.
"""

from __future__ import annotations

from agent_mesh.contracts.enums import ApprovalDecision, TaskState
from agent_mesh.contracts.models import (
    ApprovalRecord,
    RequesterIdentity,
    TaskRecord,
    TaskRequest,
)
from agent_mesh.services import approvals
from agent_mesh.services.dispatch import Dispatcher, get_dispatcher
from agent_mesh.services.repository import Repository, get_repository
from agent_mesh.services.sessions import ensure_session


class TaskService:
    def __init__(
        self,
        repo: Repository | None = None,
        dispatcher: Dispatcher | None = None,
    ) -> None:
        self._repo = repo or get_repository()
        self._dispatcher = dispatcher or get_dispatcher()

    @property
    def repo(self) -> Repository:
        return self._repo

    def create_task(self, request: TaskRequest) -> TaskRecord:
        """Persist the task, then dispatch it for asynchronous execution.

        State is persisted BEFORE dispatch so a worker can always resume from a
        durable record (required for >60-minute runs)."""
        session_id = ensure_session(self._repo, request)
        task = TaskRecord(
            tenant_id=request.tenant_id,
            client_slug=request.client_slug,
            entrypoint=request.entrypoint,
            requester=request.requester,
            session_id=session_id,
            prompt=request.prompt,
            model_route_profile=request.model_route_profile,
            metadata=request.metadata,
        )
        self._repo.create_task(task)
        task = self._repo.transition_task(
            task.task_id, TaskState.QUEUED, note="enqueued by ingress"
        )
        self._dispatcher.publish_task(task.task_id)
        return task

    def get_task(self, task_id: str) -> TaskRecord | None:
        return self._repo.get_task(task_id)

    def submit_approval_decision(
        self,
        approval_record_id: str,
        decision: ApprovalDecision,
        approver_id: str,
        channel: str,
    ) -> ApprovalRecord:
        """Record an approval decision and move the task forward.

        Approvals arrive from the same shared ledger regardless of whether the
        requester decided via Slack or MCP."""
        record = approvals.record_decision(
            self._repo, approval_record_id, decision, approver_id, channel
        )
        task = self._repo.get_task(record.task_id)
        if task is None:
            return record
        if decision == ApprovalDecision.APPROVED:
            self._repo.transition_task(
                task.task_id, TaskState.APPROVED, note=f"approved via {channel}"
            )
            # Re-dispatch so the worker resumes the gated action.
            self._dispatcher.publish_task(task.task_id)
        elif decision == ApprovalDecision.REJECTED:
            self._repo.transition_task(
                task.task_id, TaskState.REJECTED, note=f"rejected via {channel}"
            )
        return record


def request_from_slack(
    *,
    tenant_id: str,
    client_slug: str,
    slack_user_id: str,
    slack_channel_id: str,
    text: str,
    model_route_profile: str = "mixed-cascade",
) -> TaskRequest:
    """Map a Slack message onto the canonical TaskRequest contract."""
    from agent_mesh.contracts.enums import Entrypoint

    return TaskRequest(
        tenant_id=tenant_id,
        client_slug=client_slug,
        entrypoint=Entrypoint.SLACK,
        requester=RequesterIdentity(
            requester_id=f"slack:{slack_user_id}",
            entrypoint=Entrypoint.SLACK,
            slack_user_id=slack_user_id,
            slack_channel_id=slack_channel_id,
        ),
        prompt=text,
        model_route_profile=model_route_profile,
    )


def request_from_mcp(
    *,
    tenant_id: str,
    client_slug: str,
    mcp_subject: str,
    text: str,
    model_route_profile: str = "mixed-cascade",
) -> TaskRequest:
    """Map an MCP tool invocation onto the canonical TaskRequest contract."""
    from agent_mesh.contracts.enums import Entrypoint

    return TaskRequest(
        tenant_id=tenant_id,
        client_slug=client_slug,
        entrypoint=Entrypoint.MCP,
        requester=RequesterIdentity(
            requester_id=f"mcp:{mcp_subject}",
            entrypoint=Entrypoint.MCP,
            mcp_subject=mcp_subject,
        ),
        prompt=text,
        model_route_profile=model_route_profile,
    )
