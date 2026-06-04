"""Enumerations shared across the task contract.

Kept in one module so the lifecycle state machine, the database migrations, and
the JSON Schema export all agree on the same string values.
"""

from __future__ import annotations

from enum import Enum


class Entrypoint(str, Enum):
    """How a task entered the mesh. Slack and MCP are mirrored capabilities."""

    SLACK = "slack"
    MCP = "mcp"
    API = "api"
    INTERNAL = "internal"


class TaskState(str, Enum):
    """Canonical task lifecycle. Kept Temporal-ready: states map cleanly onto
    durable-workflow signals if Temporal is introduced post-POC."""

    RECEIVED = "received"
    QUEUED = "queued"
    PLANNING = "planning"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Terminal states never transition further.
TERMINAL_STATES = frozenset(
    {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED, TaskState.REJECTED}
)


class ToolCategory(str, Enum):
    """Tool risk classification. Anything that mutates external state is a write
    and requires approval; reads do not."""

    READ = "read"
    WRITE = "write"
    EXTERNAL_SEND = "external_send"
    FINANCIAL = "financial"
    PUBLISHING = "publishing"
    CODE = "code"
    ADMIN = "admin"


# Categories that always require an approval gate before execution.
WRITE_CATEGORIES = frozenset(
    {
        ToolCategory.WRITE,
        ToolCategory.EXTERNAL_SEND,
        ToolCategory.FINANCIAL,
        ToolCategory.PUBLISHING,
        ToolCategory.ADMIN,
    }
)


class ToolCallStatus(str, Enum):
    REQUESTED = "requested"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"


class ApprovalDecision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
