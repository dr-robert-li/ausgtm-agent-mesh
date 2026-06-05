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


class ProposalType(str, Enum):
    """Kinds of self-improvement a reflection agent may propose.

    Every type is a *proposal* only: it is stored, evaluated, and approved before
    any promotion. None of these mutate active system state at runtime in the POC.
    """

    PROMPT_PATCH = "prompt_patch"
    TOOL_SCHEMA_PATCH = "tool_schema_patch"
    ROUTING_RULE_PATCH = "routing_rule_patch"
    EVAL_CASE = "eval_case"
    RUNBOOK_DOC_PATCH = "runbook_doc_patch"
    BUDGET_POLICY_PATCH = "budget_policy_patch"
    FIELD_MAPPING_PATCH = "field_mapping_patch"
    SANDBOX_POLICY_PATCH = "sandbox_policy_patch"


class ProposalRiskLevel(str, Enum):
    """Risk classification for a self-improvement proposal.

    Every proposal requires approval before promotion; risk level drives how much
    scrutiny and which reviewer tier is required. HIGH and CRITICAL can never
    auto-promote regardless of evaluation outcome."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Risk levels that may never be promoted automatically, even after a passing
# evaluation — they always require an explicit human approval decision.
NON_AUTO_PROMOTE_RISK = frozenset({ProposalRiskLevel.HIGH, ProposalRiskLevel.CRITICAL})


class ProposalStatus(str, Enum):
    """Lifecycle of a self-improvement proposal.

    DRAFT -> PENDING_EVALUATION -> (EVALUATION_PASSED | EVALUATION_FAILED)
          -> AWAITING_APPROVAL -> (APPROVED -> PROMOTED | REJECTED)
    A proposal may also be ROLLED_BACK after promotion."""

    DRAFT = "draft"
    PENDING_EVALUATION = "pending_evaluation"
    EVALUATION_PASSED = "evaluation_passed"
    EVALUATION_FAILED = "evaluation_failed"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"
