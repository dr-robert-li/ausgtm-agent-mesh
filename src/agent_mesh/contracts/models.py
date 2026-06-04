"""Pydantic v2 contract models for the agent mesh.

Design notes:
- Every record carries ``tenant_id`` / ``client_slug`` so the same schema can
  back multiple redeployments without mixing contexts (tenant partitioning).
- Correlation IDs (``task_id``, ``session_id``, ``requester_id``) are threaded
  through every model so traces, gateway logs, tool calls, and approvals can be
  joined for audit.
- Retrieval evidence (``EvidenceChunk``) is intentionally a different model from
  session summaries / task metadata so operational state never mixes with
  retrieval evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agent_mesh.contracts.enums import (
    ApprovalDecision,
    Entrypoint,
    TaskState,
    ToolCallStatus,
    ToolCategory,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid4().hex


class _Base(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid")


class RequesterIdentity(_Base):
    """Normalized requester identity. Slack and MCP contexts are mapped onto
    this shared shape so approvals can be routed back to the originating
    requester regardless of entrypoint."""

    requester_id: str = Field(description="Stable mesh-internal requester id.")
    display_name: str | None = None
    entrypoint: Entrypoint
    slack_user_id: str | None = None
    slack_channel_id: str | None = None
    mcp_subject: str | None = Field(
        default=None, description="MCP auth subject / principal, when entrypoint is MCP."
    )
    email: str | None = None


class TaskRequest(_Base):
    """Inbound request shape accepted by every ingress (Slack, MCP, API).

    Ingress services translate their native payloads into this contract before
    handing off to the shared task service, so capabilities stay mirrored."""

    tenant_id: str
    client_slug: str
    entrypoint: Entrypoint
    requester: RequesterIdentity
    prompt: str = Field(description="Natural-language task instruction.")
    session_id: str | None = Field(
        default=None, description="Existing session to continue; new one created if absent."
    )
    model_route_profile: str = Field(default="mixed-cascade")
    metadata: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(
        default=None,
        description="Optional client-supplied key to dedupe retried submissions.",
    )


class TaskRecord(_Base):
    """Durable task state. Persisted before any long-running execution begins so
    a worker can resume after restart or approval pause."""

    task_id: str = Field(default_factory=_new_id)
    tenant_id: str
    client_slug: str
    entrypoint: Entrypoint
    requester: RequesterIdentity
    session_id: str
    prompt: str
    state: TaskState = TaskState.RECEIVED
    model_route_profile: str = "mixed-cascade"
    result_summary: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class TaskEvent(_Base):
    """Append-only lifecycle event. One row per state transition or notable
    occurrence; the ordered stream is the task's audit trail."""

    event_id: str = Field(default_factory=_new_id)
    task_id: str
    tenant_id: str
    state: TaskState
    note: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)


class ToolCall(_Base):
    """A single tool invocation request and its outcome. Write-category calls
    are gated: they enter ``AWAITING_APPROVAL`` and cannot execute until an
    ``ApprovalRecord`` approves them."""

    tool_call_id: str = Field(default_factory=_new_id)
    task_id: str
    tenant_id: str
    tool_name: str
    category: ToolCategory
    approval_required: bool
    status: ToolCallStatus = ToolCallStatus.REQUESTED
    parameters: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    requester_id: str
    model_route: str | None = None
    approval_record_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class ApprovalRequest(_Base):
    """Approval prompt delivered to a requester (Slack and/or MCP), mirrored to
    Slack where available."""

    approval_request_id: str = Field(default_factory=_new_id)
    task_id: str
    tenant_id: str
    tool_call_id: str | None = None
    requester_id: str
    summary: str = Field(description="Human-readable description of the write action.")
    payload_hash: str = Field(description="Hash of the exact action to be approved.")
    evidence_pointers: list[str] = Field(default_factory=list)
    deliver_to_slack: bool = True
    deliver_to_mcp: bool = True
    created_at: datetime = Field(default_factory=_utcnow)


class ApprovalRecord(_Base):
    """Decision on an approval request. POC stores these in ``approval_records``;
    production hardens this into an append-only tamper-evident ledger."""

    approval_record_id: str = Field(default_factory=_new_id)
    approval_request_id: str
    task_id: str
    tenant_id: str
    tool_call_id: str | None = None
    decision: ApprovalDecision = ApprovalDecision.PENDING
    approver_id: str | None = None
    channel: str | None = Field(default=None, description="slack | mcp | api")
    payload_hash: str
    decided_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class EvidenceChunk(_Base):
    """Retrieval document / tool evidence chunk with embedding and freshness
    metadata. Deliberately separate from session summaries and task metadata."""

    evidence_id: str = Field(default_factory=_new_id)
    tenant_id: str
    client_slug: str
    source: str = Field(description="Origin, e.g. 'google_drive', 'tool:hubspot'.")
    source_ref: str | None = Field(default=None, description="Document id / URL / item id.")
    content: str
    embedding: list[float] | None = Field(
        default=None, description="pgvector embedding; populated at ingestion time."
    )
    freshness_at: datetime = Field(default_factory=_utcnow)
    task_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProposedPatch(_Base):
    """A prompt-to-code artifact: a proposed change that is NOT applied until
    approved. Generated in the sandbox, returned for review."""

    patch_id: str = Field(default_factory=_new_id)
    task_id: str
    tenant_id: str
    description: str
    diff: str = Field(description="Unified diff or artifact content.")
    artifact_paths: list[str] = Field(default_factory=list)
    approval_required: bool = True
    created_at: datetime = Field(default_factory=_utcnow)


class AIBOMSnapshot(_Base):
    """AI Bill of Materials: the approved capability bundle for a deployment at a
    point in time. Generated from the deployment + tool pack manifests."""

    snapshot_id: str = Field(default_factory=_new_id)
    tenant_id: str
    client_slug: str
    version: str
    agents: list[dict[str, Any]] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[dict[str, Any]] = Field(default_factory=list)
    prompts: list[dict[str, Any]] = Field(default_factory=list)
    model_routes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)


class BudgetEvent(_Base):
    """One row per model call for cost attribution and month-to-date budget
    enforcement. LiteLLM is the enforcement point; this is the durable ledger."""

    budget_event_id: str = Field(default_factory=_new_id)
    tenant_id: str
    client_slug: str
    budget_owner: str = Field(description="Per-user budget owner id.")
    task_id: str | None = None
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=_utcnow)


class GatewayEvent(_Base):
    """Correlates a Cloudflare AI Gateway request with a LiteLLM request and the
    originating task for audit. Cloudflare owns logging/DLP; this row is the
    join key kept in our durable store."""

    gateway_event_id: str = Field(default_factory=_new_id)
    tenant_id: str
    client_slug: str
    task_id: str | None = None
    cf_aig_request_id: str | None = None
    litellm_request_id: str | None = None
    provider: str | None = None
    model_route: str | None = None
    provider_status: int | None = None
    dlp_action: str | None = Field(default=None, description="e.g. 'allow', 'block', 'flag'.")
    created_at: datetime = Field(default_factory=_utcnow)


# Registry used by the JSON Schema exporter and by tests.
CONTRACT_MODELS: dict[str, type[BaseModel]] = {
    "RequesterIdentity": RequesterIdentity,
    "TaskRequest": TaskRequest,
    "TaskRecord": TaskRecord,
    "TaskEvent": TaskEvent,
    "ToolCall": ToolCall,
    "ApprovalRequest": ApprovalRequest,
    "ApprovalRecord": ApprovalRecord,
    "EvidenceChunk": EvidenceChunk,
    "ProposedPatch": ProposedPatch,
    "AIBOMSnapshot": AIBOMSnapshot,
    "BudgetEvent": BudgetEvent,
    "GatewayEvent": GatewayEvent,
}
