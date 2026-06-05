"""Worker runner: consume a task id and execute the mesh with approval gating.

Execution model:
1. Move task RECEIVED/QUEUED -> RUNNING.
2. Run the LangGraph + Deep Agents orchestration adapter.
3. For each *proposed write*, create a gated ToolCall + open an approval. The
   task pauses in AWAITING_APPROVAL and the worker returns — the run resumes
   when an approval decision is dispatched back (durable, survives restart).
4. If there are no pending writes, complete the task.

When resumed after approval, write tool calls whose approval is APPROVED (and
whose payload hash still matches) execute through the Tool Gateway; the task then
completes.
"""

from __future__ import annotations

from agent_mesh.contracts.enums import (
    ApprovalDecision,
    TaskState,
    ToolCallStatus,
    ToolCategory,
)
from agent_mesh.contracts.lifecycle import is_terminal
from agent_mesh.contracts.models import ToolCall
from agent_mesh.services import approvals
from agent_mesh.services.repository import Repository, get_repository
from agent_mesh.tools.gateway import ToolGateway
from agent_mesh.worker.orchestrator import run_mesh


class Worker:
    def __init__(
        self,
        repo: Repository | None = None,
        tool_gateway: ToolGateway | None = None,
    ) -> None:
        self._repo = repo or get_repository()
        self._gateway = tool_gateway

    def process(self, task_id: str) -> str:
        """Process or resume a single task. Returns the resulting state value."""
        task = self._repo.get_task(task_id)
        if task is None:
            raise KeyError(f"unknown task {task_id}")
        if is_terminal(task.state):
            return str(task.state)

        # Resume path: a previously gated task has just been approved.
        if task.state == TaskState.APPROVED.value or task.state == TaskState.APPROVED:
            return self._resume_after_approval(task_id)

        # Fresh run.
        self._repo.transition_task(task_id, TaskState.RUNNING, note="worker picked up task")
        result = run_mesh(task)

        if not result.proposed_writes:
            done = self._repo.transition_task(
                task_id, TaskState.COMPLETED, note="no write actions required"
            )
            updated = done.model_copy(update={"result_summary": result.summary})
            self._repo.create_task(updated)  # upsert
            return str(updated.state)

        # Gate each proposed write behind an approval.
        for proposed in result.proposed_writes:
            call = ToolCall(
                task_id=task_id,
                tenant_id=task.tenant_id,
                tool_name=proposed["tool_name"],
                category=ToolCategory(proposed["category"]),
                approval_required=True,
                status=ToolCallStatus.AWAITING_APPROVAL,
                parameters=proposed.get("parameters", {}),
                requester_id=task.requester.requester_id,
            )
            self._repo.upsert_tool_call(call)
            request = approvals.build_approval_request(
                call, summary=f"Approve write: {call.tool_name}", evidence=result.evidence
            )
            record = approvals.open_approval(self._repo, request)
            call = call.model_copy(update={"approval_record_id": record.approval_record_id})
            self._repo.upsert_tool_call(call)

        self._repo.transition_task(
            task_id, TaskState.AWAITING_APPROVAL, note="paused for write approval"
        )
        return str(TaskState.AWAITING_APPROVAL.value)

    def _resume_after_approval(self, task_id: str) -> str:
        task = self._repo.get_task(task_id)
        assert task is not None
        # Execute any approved-and-unmodified write tool calls.
        for call in self._pending_calls(task_id, task.tenant_id):
            if call.approval_record_id is None:
                continue
            record = self._repo.get_approval(call.approval_record_id)
            if record is None:
                continue
            if approvals.is_approved(record, call.parameters):
                result = self._execute(call)
                executed = call.model_copy(
                    update={"status": ToolCallStatus.EXECUTED.value, "result": result}
                )
                self._repo.upsert_tool_call(executed)
            elif (
                record.decision == ApprovalDecision.REJECTED.value
                or record.decision == ApprovalDecision.REJECTED
            ):
                rejected = call.model_copy(update={"status": ToolCallStatus.REJECTED.value})
                self._repo.upsert_tool_call(rejected)

        done = self._repo.transition_task(
            task_id, TaskState.COMPLETED, note="completed after approval"
        )
        return str(done.state)

    def _pending_calls(self, task_id: str, tenant_id: str) -> list[ToolCall]:
        # Fetch tool calls through the protocol (tenant-scoped) so the resume
        # path works identically against the in-memory and SQL repositories.
        return self._repo.list_tool_calls(task_id, tenant_id)

    def _execute(self, call: ToolCall) -> dict:
        if self._gateway is None:
            return {
                "stub": True,
                "note": "no tool gateway configured; write not executed",
                "tool": call.tool_name,
            }
        return self._gateway.execute(call.tool_name, call.parameters)
