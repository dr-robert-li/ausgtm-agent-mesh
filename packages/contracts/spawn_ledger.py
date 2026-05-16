"""Append-only SpawnLedger.

Every child Task is preceded by a SpawnLedger row. If the ledger write
fails, the spawn does not happen. Rows are never mutated; status changes
happen on the *child Task*, not on the ledger row. The `disposition` field
captures the supervisor's verdict at decision time.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from packages.contracts.ids import new_id


class SpawnDisposition(str, Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    denied = "denied"
    cancelled = "cancelled"
    superseded = "superseded"


class ModelTier(str, Enum):
    S = "S"
    M = "M"
    L = "L"


class SpawnLedger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spawn_id: str = Field(default_factory=lambda: new_id("spawn"))
    tenant_id: str
    parent_task_id: str
    parent_agent_id: str | None = None
    child_task_id: str
    child_agent_role: str
    reason: str  # human-readable, mirrored into Decision-log
    model_tier: ModelTier
    tools: list[str] = Field(default_factory=list)
    budgets: dict[str, Any] = Field(default_factory=dict)
    risk_tier: str  # e.g. "read_safe", "external_egress"
    wave_index: int
    depth: int
    output_contract: dict[str, Any] | None = None
    disposition: SpawnDisposition = SpawnDisposition.pending
    release_manifest_id: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decided_at: datetime | None = None
