"""Egress-only verification record.

Verification against systems of record happens **only at egress**, never
mid-stream. The LLM proposes the output/action and a claim-evidence map;
eight deterministic guards then enforce the rules in a fixed order. No
LLM is in the verification loop — every guard is schema-checkable.

A blocked egress is a `decision_kind: egress_blocked` Decision-log entry.
If `tier_and_policy` (or any guard with `require_hitl=True`) raises a
HITL requirement, the Task moves to `AWAITING_HITL` with
`hitl.from_state = EGRESS_CHECK` (a sub-phase of `EXECUTING`; no new
Task state is introduced).

Mirrors agentic-mesh-reference-arch v0.1.3 `docs/knowledge-layer.md` §5.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from packages.contracts.ids import new_id


class EgressGuardName(str, Enum):
    """The eight deterministic guards, in their canonical order."""

    schema = "schema"
    claim_evidence_map = "claim_evidence_map"
    evidence_resolvable = "evidence_resolvable"
    freshness = "freshness"
    source_authority = "source_authority"
    tenancy = "tenancy"  # hard refuse on failure
    tier_and_policy = "tier_and_policy"  # may set require_hitl
    budget = "budget"


GUARD_ORDER: tuple[EgressGuardName, ...] = (
    EgressGuardName.schema,
    EgressGuardName.claim_evidence_map,
    EgressGuardName.evidence_resolvable,
    EgressGuardName.freshness,
    EgressGuardName.source_authority,
    EgressGuardName.tenancy,
    EgressGuardName.tier_and_policy,
    EgressGuardName.budget,
)


class EgressGuardVerdict(str, Enum):
    pass_ = "pass"
    blocked = "blocked"
    require_hitl = "require_hitl"


class EgressOverallVerdict(str, Enum):
    pass_ = "pass"
    blocked = "blocked"
    blocked_require_hitl = "blocked_require_hitl"


class EgressGuardResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guard: EgressGuardName
    name: str  # human-readable label, mirrored into Decision-log
    verdict: EgressGuardVerdict
    note: str | None = None


class ProposedEgress(BaseModel):
    """The thing the LLM is asking to push to the world."""

    model_config = ConfigDict(extra="forbid")

    kind: str  # e.g. "slack_message", "monday_item_update", "sheet_append"
    tool_id: str
    tier: str  # ToolTrustTier value
    claim_evidence_map_ref: str  # `cem_…`
    payload_ref: str  # `blob://…` — never the raw payload


class EgressCheckRecord(BaseModel):
    """Append-only record of one egress evaluation."""

    model_config = ConfigDict(extra="forbid")

    egress_check_id: str = Field(default_factory=lambda: new_id("egc"))
    tenant_id: str
    task_id: str
    correlation_id: str | None = None
    release_manifest_id: str | None = None
    wave_index: int = 0
    proposed_egress: ProposedEgress
    guards: list[EgressGuardResult] = Field(default_factory=list)
    overall_verdict: EgressOverallVerdict
    blocking_guard: EgressGuardName | None = None
    decision_log_ref: str | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
