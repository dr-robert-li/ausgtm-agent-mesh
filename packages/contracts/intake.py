"""Intake contract.

Entry-plane artifact created **before** the Orchestrator creates a Task.
Captures the canonical intake schema and a cheap S-tier feasibility check.
Feasibility is decided once at intake — it is NOT re-run mid-stream and is
not allowed to silently escalate above S-tier. Ambiguous intents must
produce a single disambiguating question, not an expensive cascade.

Mirrors agentic-mesh-reference-arch v0.1.3 `docs/intake.md`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from packages.contracts.ids import new_id
from packages.contracts.task import TaskEntrypoint


class FeasibilityVerdict(str, Enum):
    feasible = "feasible"
    ambiguous = "ambiguous"
    infeasible = "infeasible"


class FeasibilityCheck(BaseModel):
    """Single cheap S-tier classifier pass run at intake time.

    Three checks compose the verdict: schema parse, tool-plan lookup,
    one S-tier classifier call. No silent escalation to M/L.
    """

    model_config = ConfigDict(extra="forbid")

    verdict: FeasibilityVerdict
    reason: str
    model_tier: str = "S"  # locked to S-tier at intake
    checked_tools: list[str] = Field(default_factory=list)
    disambiguating_question: str | None = None


class Intake(BaseModel):
    """Canonical intake record. One per inbound request from the entry plane."""

    model_config = ConfigDict(extra="forbid")

    intake_id: str = Field(default_factory=lambda: new_id("intake"))
    tenant_id: str
    entrypoint: TaskEntrypoint
    actor: str
    goal: str  # verbatim from the caller; do not paraphrase
    inputs: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    proposed_tool_intents: list[str] = Field(default_factory=list)
    feasibility: FeasibilityCheck
    release_manifest_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
