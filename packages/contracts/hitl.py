"""HITL decision payload, embedded on Task.hitl."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class HITLDecisionKind(str, Enum):
    approve = "approve"
    reject = "reject"
    modify = "modify"


class HITLDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_at: datetime
    reason: str
    recommended_action: str | None = None
    approver: str | None = None
    decision: HITLDecisionKind | None = None
    decided_at: datetime | None = None
    from_state: str  # the Task state at the time HITL was requested
    notes: str | None = None
