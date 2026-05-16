"""Policy and supervisor-budget contracts.

The Swarm Supervisor evaluates these on every spawn (five-step gate:
policy / budget / risk / provenance / marginal utility).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from packages.contracts.ids import new_id


class ToolTrustTier(str, Enum):
    read_safe = "read_safe"
    read_sensitive = "read_sensitive"
    write_revocable = "write_revocable"
    write_destructive = "write_destructive"
    external_egress = "external_egress"


class PolicyLimits(BaseModel):
    """Hard ceilings the supervisor will not exceed."""

    model_config = ConfigDict(extra="forbid")

    max_waves: int = 3
    max_child_agents_per_wave: int = 5
    max_recursion_depth: int = 1  # root depth = 0
    max_total_spawns: int = 25
    external_write_tier_limit: ToolTrustTier = ToolTrustTier.write_revocable


class PolicyBudgets(BaseModel):
    """Soft budgets — exhausting any triggers HITL, not abort."""

    model_config = ConfigDict(extra="forbid")

    max_wall_clock_minutes: int = 30
    max_tool_calls: int = 50
    max_model_calls: int = 50
    max_token_budget: int = 500_000
    min_confidence_to_spawn: float = 0.6


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_id: str = Field(default_factory=lambda: new_id("policy"))
    tenant_id: str
    scope: str  # e.g. "routine:foo", "entrypoint:slack", "tenant:*"
    limits: PolicyLimits = Field(default_factory=PolicyLimits)
    budgets: PolicyBudgets = Field(default_factory=PolicyBudgets)
    on_violation: str = "require_hitl"  # or "deny"
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
