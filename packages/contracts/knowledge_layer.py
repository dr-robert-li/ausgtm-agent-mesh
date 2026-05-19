"""Context and Evidence Knowledge Layer contracts.

The Knowledge Layer is a **tenant-scoped cache + index + evidence-pointer
substrate**. It is *not* a system of record. Authoritative state stays in
the external tools and systems of record (Monday, Drive, Slack, HubSpot,
Stripe, BigQuery, tl;dv, …). KL provides sufficient, governed,
source-aware context for more capable reasoning.

LLMs never write KL entries directly. Writes are append-only and versioned.
Entries carry pointers back to the system of record they were sourced from,
plus a freshness verdict.

Mirrors agentic-mesh-reference-arch v0.1.3 `docs/knowledge-layer.md`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "knowledge-layer/v0.1.3"


class EvidenceKind(str, Enum):
    knowledge_layer_entry = "knowledge_layer_entry"
    tool_response = "tool_response"
    system_of_record = "system_of_record"


class FreshnessVerdict(str, Enum):
    fresh = "fresh"
    stale_acceptable = "stale_acceptable"
    stale_unacceptable = "stale_unacceptable"
    unknown = "unknown"


class Freshness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: FreshnessVerdict
    freshness_ttl_seconds: int | None = None
    expires_at: datetime | None = None


class EvidencePointer(BaseModel):
    """Reference to the system of record this evidence came from.

    The KL never holds the ground truth — only how to refetch it.
    """

    model_config = ConfigDict(extra="forbid")

    kind: EvidenceKind
    tool_id: str  # e.g. "monday", "google_sheets", "tldv"
    lookup_key: str  # tool-specific identifier (board/item, file id, …)
    url: str | None = None


class KnowledgeLayerEntry(BaseModel):
    """One versioned, tenant-scoped cache entry pointing at a system of record.

    Keyed by `(tenant_id, source_system, source_id)` with optional
    `content_hash`. `entry_id` follows the reference arch format
    `kl:{tenant}:{source}/{path}#v{n}`.
    """

    model_config = ConfigDict(extra="forbid")

    entry_id: str  # e.g. "kl:tenant_acme:monday/items/1234567890#v17"
    tenant_id: str
    source_system: str
    source_id: str
    content_hash: str | None = None
    claim: str
    evidence_pointer: EvidencePointer
    fetched_at: datetime
    freshness: Freshness
    is_authoritative_for: list[str] = Field(default_factory=list)
    version: int = 1
    schema_version: str = SCHEMA_VERSION


class Evidence(BaseModel):
    """One piece of evidence backing a Claim in the claim-evidence sidecar."""

    model_config = ConfigDict(extra="forbid")

    kind: EvidenceKind = EvidenceKind.knowledge_layer_entry
    ref: str  # KL entry_id, or tool-response/system-of-record ref
    freshness: Freshness
    fetched_at: datetime
    is_authoritative_for: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    """A single subject/predicate/value claim asserted by the LLM."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    subject: str
    predicate: str
    value: Any
    evidence: list[Evidence] = Field(default_factory=list)


class ClaimEvidenceMap(BaseModel):
    """LLM-produced sidecar binding output claims to evidence pointers.

    Required at egress for any output that asserts external facts. The
    egress guards check this map deterministically — the LLM proposes the
    binding; the guards enforce schema/source/freshness/policy/budget.
    """

    model_config = ConfigDict(extra="forbid")

    claim_evidence_map_ref: str  # `cem_{ULID}`
    tenant_id: str
    task_id: str
    correlation_id: str | None = None
    release_manifest_id: str | None = None
    schema_version: str = SCHEMA_VERSION
    claims: list[Claim] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
