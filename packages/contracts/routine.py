"""Routine + Release manifest contract.

Routines are reusable plans. Candidate routines are proposed automatically
from observed task traces; they live as `candidate` until an async review
either promotes them to `active` or archives them. Hard delete is a separate,
audited operation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from packages.contracts.ids import new_id


class RoutineStatus(str, Enum):
    candidate = "candidate"  # proposed, awaiting review
    active = "active"        # approved + in use
    deprecated = "deprecated"  # superseded, still callable
    archived = "archived"    # not callable; precursor to hard delete


class Routine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    routine_id: str = Field(default_factory=lambda: new_id("routine"))
    name: str
    version: str  # SemVer
    status: RoutineStatus = RoutineStatus.candidate
    description: str
    plan_template: dict[str, Any]  # opaque to contracts; planner-defined shape
    tool_plan: list[str] = Field(default_factory=list)
    required_trust_tier: str | None = None
    proposed_by: str | None = None
    approved_by: str | None = None
    archived_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
