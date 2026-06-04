"""Task lifecycle state machine.

Centralizes legal transitions so ingress, the task service, and the worker all
agree on what a valid transition is. Kept Temporal-ready: the transition table
maps directly onto durable-workflow signals if Temporal is introduced later.
"""

from __future__ import annotations

from agent_mesh.contracts.enums import TERMINAL_STATES, TaskState

_ALLOWED: dict[TaskState, frozenset[TaskState]] = {
    TaskState.RECEIVED: frozenset({TaskState.QUEUED, TaskState.CANCELLED}),
    TaskState.QUEUED: frozenset({TaskState.PLANNING, TaskState.RUNNING, TaskState.CANCELLED}),
    TaskState.PLANNING: frozenset(
        {TaskState.RUNNING, TaskState.AWAITING_APPROVAL, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.RUNNING: frozenset(
        {
            TaskState.AWAITING_APPROVAL,
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.AWAITING_APPROVAL: frozenset(
        {TaskState.APPROVED, TaskState.REJECTED, TaskState.CANCELLED}
    ),
    TaskState.APPROVED: frozenset({TaskState.RUNNING, TaskState.COMPLETED, TaskState.FAILED}),
    TaskState.REJECTED: frozenset(),
    TaskState.COMPLETED: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.CANCELLED: frozenset(),
}


def _coerce(state: TaskState | str) -> TaskState:
    return state if isinstance(state, TaskState) else TaskState(state)


def can_transition(current: TaskState | str, target: TaskState | str) -> bool:
    """Return True if ``current -> target`` is a legal lifecycle transition."""
    current = _coerce(current)
    target = _coerce(target)
    return target in _ALLOWED.get(current, frozenset())


def is_terminal(state: TaskState | str) -> bool:
    return _coerce(state) in TERMINAL_STATES


class IllegalTransition(ValueError):
    """Raised when an unsupported state transition is attempted."""


def assert_transition(current: TaskState | str, target: TaskState | str) -> None:
    if not can_transition(current, target):
        raise IllegalTransition(
            f"Illegal task transition: {_coerce(current).value} -> {_coerce(target).value}"
        )
