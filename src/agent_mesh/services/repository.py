"""Persistence abstraction.

The POC ships an in-memory repository so the whole mesh is importable and
testable without a database. A Postgres-backed implementation slots in behind
the same ``Repository`` protocol; the migrations in ``migrations/`` define the
target schema. ``get_repository`` chooses based on ``DATABASE_URL``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from threading import RLock
from typing import Protocol

from agent_mesh.contracts.enums import TaskState
from agent_mesh.contracts.lifecycle import assert_transition
from agent_mesh.contracts.models import (
    ApprovalRecord,
    TaskEvent,
    TaskRecord,
    ToolCall,
)


class Repository(Protocol):
    def create_task(self, task: TaskRecord) -> TaskRecord: ...
    def get_task(self, task_id: str) -> TaskRecord | None: ...
    def transition_task(
        self, task_id: str, target: TaskState, note: str | None = None
    ) -> TaskRecord: ...
    def append_event(self, event: TaskEvent) -> TaskEvent: ...
    def list_events(self, task_id: str) -> list[TaskEvent]: ...
    def upsert_tool_call(self, call: ToolCall) -> ToolCall: ...
    def get_tool_call(self, tool_call_id: str) -> ToolCall | None: ...
    def upsert_approval(self, record: ApprovalRecord) -> ApprovalRecord: ...
    def get_approval(self, approval_record_id: str) -> ApprovalRecord | None: ...


class InMemoryRepository:
    """Thread-safe in-memory store for local dev and tests."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._tasks: dict[str, TaskRecord] = {}
        self._events: list[TaskEvent] = []
        self._tool_calls: dict[str, ToolCall] = {}
        self._approvals: dict[str, ApprovalRecord] = {}

    def create_task(self, task: TaskRecord) -> TaskRecord:
        with self._lock:
            self._tasks[task.task_id] = task
            return task

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._tasks.get(task_id)

    def transition_task(
        self, task_id: str, target: TaskState, note: str | None = None
    ) -> TaskRecord:
        with self._lock:
            task = self._tasks[task_id]
            assert_transition(task.state, target)
            # Re-create with new state; models use enum values so coerce to value.
            updated = task.model_copy(
                update={
                    "state": target.value,
                    "updated_at": datetime.now(UTC),
                }
            )
            self._tasks[task_id] = updated
            self._events.append(
                TaskEvent(task_id=task_id, tenant_id=task.tenant_id, state=target, note=note)
            )
            return updated

    def append_event(self, event: TaskEvent) -> TaskEvent:
        with self._lock:
            self._events.append(event)
            return event

    def list_events(self, task_id: str) -> list[TaskEvent]:
        with self._lock:
            return [e for e in self._events if e.task_id == task_id]

    def upsert_tool_call(self, call: ToolCall) -> ToolCall:
        with self._lock:
            self._tool_calls[call.tool_call_id] = call
            return call

    def get_tool_call(self, tool_call_id: str) -> ToolCall | None:
        with self._lock:
            return self._tool_calls.get(tool_call_id)

    def upsert_approval(self, record: ApprovalRecord) -> ApprovalRecord:
        with self._lock:
            self._approvals[record.approval_record_id] = record
            return record

    def get_approval(self, approval_record_id: str) -> ApprovalRecord | None:
        with self._lock:
            return self._approvals.get(approval_record_id)


_SINGLETON: InMemoryRepository | None = None


def get_repository() -> Repository:
    """Return the active repository.

    A ``DATABASE_URL`` would select a Postgres-backed implementation in a fuller
    build; the POC uses a process-wide in-memory singleton so ingress and the
    in-process worker share state during local smoke checks.
    """
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = InMemoryRepository()
    return _SINGLETON
