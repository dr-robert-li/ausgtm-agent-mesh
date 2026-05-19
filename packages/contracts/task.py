"""Task contract.

The Task is the bus of the system. The Orchestrator (Temporal workflow) is
the only mutator of `state`. Slack / MCP / API readers consume Tasks but
do not transition them.

Modeled on agentic-mesh-reference-arch v0.1.3 `docs/task-contract.md`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from packages.contracts.evaluation import EvaluationRecord
from packages.contracts.hitl import HITLDecision
from packages.contracts.ids import new_id


class TaskEntrypoint(str, Enum):
    slack = "slack"
    api = "api"
    mcp = "mcp"
    internal = "internal"


class TaskState(str, Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    AWAITING_HITL = "AWAITING_HITL"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"


class TaskDedup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fingerprint: str | None = None
    fingerprint_fields: list[str] = Field(default_factory=list)
    candidate_task_ids: list[str] = Field(default_factory=list)
    confirmed_duplicate_of: str | None = None
    suppression_expires_at: datetime | None = None


class ProvenanceKind(str, Enum):
    intake = "intake"
    evidence = "evidence"
    egress_check = "egress_check"
    routine = "routine"
    release = "release"
    other = "other"


class ProvenanceRef(BaseModel):
    """One typed pointer to a prior artifact (intake, evidence, egress check)."""

    model_config = ConfigDict(extra="forbid")

    kind: ProvenanceKind
    ref: str  # intake_…, kl:…, cem_…, egc_…, rm_…


class TaskProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created_by: str  # actor id or system component
    source_trace_id: str | None = None
    routine_id: str | None = None
    routine_version: str | None = None
    release_manifest_id: str | None = None
    refs: list[ProvenanceRef] = Field(default_factory=list)
    notes: str | None = None


class Task(BaseModel):
    """Canonical Task. Orchestrator-only mutations of `state`."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(default_factory=lambda: new_id("task"))
    parent_task_id: str | None = None
    root_task_id: str | None = None
    tenant_id: str
    entrypoint: TaskEntrypoint
    actor: str  # slack user id, api caller, mcp client, etc.
    goal: str

    inputs: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None

    # v0.1.3 — entry-plane and evidence-layer pointers. Workflow state
    # carries refs, never raw payloads.
    intake_id: str | None = None
    correlation_id: str | None = None
    claim_evidence_map_ref: str | None = None

    state: TaskState = TaskState.PENDING
    state_reason: str | None = None

    governance_scope: str | None = None
    release_manifest_id: str | None = None
    plan: dict[str, Any] | None = None
    wave_index: int = 0
    routine_id: str | None = None
    routine_version: str | None = None
    tool_plan_id: str | None = None

    result: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    evaluations: list[EvaluationRecord] = Field(default_factory=list)
    hitl: HITLDecision | None = None
    dedup: TaskDedup | None = None
    provenance: TaskProvenance

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
