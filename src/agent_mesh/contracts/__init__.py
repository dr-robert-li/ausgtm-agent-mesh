"""Canonical contracts for the agent mesh.

These Pydantic models are the single source of truth for the task lifecycle,
approvals, tool calls, evidence, AI-BOM snapshots, and budget events. JSON
Schema is exported from these models (see ``export_schemas``) so that
non-Python consumers (the Cloudflare Worker, MCP clients, dashboards) share the
same contract without duplicating definitions.
"""

from agent_mesh.contracts.enums import (
    ApprovalDecision,
    Entrypoint,
    TaskState,
    ToolCallStatus,
    ToolCategory,
)
from agent_mesh.contracts.models import (
    AIBOMSnapshot,
    ApprovalRecord,
    ApprovalRequest,
    BudgetEvent,
    EvidenceChunk,
    GatewayEvent,
    ProposedPatch,
    RequesterIdentity,
    TaskEvent,
    TaskRecord,
    TaskRequest,
    ToolCall,
)

__all__ = [
    "ApprovalDecision",
    "Entrypoint",
    "TaskState",
    "ToolCallStatus",
    "ToolCategory",
    "AIBOMSnapshot",
    "ApprovalRecord",
    "ApprovalRequest",
    "BudgetEvent",
    "EvidenceChunk",
    "GatewayEvent",
    "ProposedPatch",
    "RequesterIdentity",
    "TaskEvent",
    "TaskRequest",
    "TaskRecord",
    "ToolCall",
]
