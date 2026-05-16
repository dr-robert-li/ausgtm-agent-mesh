"""Pydantic contracts for the Agentic Mesh POC.

These models mirror the reference architecture
(https://github.com/dr-robert-li/agentic-mesh-reference-arch, v0.1.2).

Conventions:
  - All models use `extra="forbid"`. Unknown fields are bugs.
  - IDs use the `{prefix}_{ULID}` form from the reference arch.
  - Timestamps are timezone-aware UTC.
"""

from packages.contracts.evaluation import EvaluationRecord
from packages.contracts.hitl import HITLDecision
from packages.contracts.ids import new_id
from packages.contracts.policy import Policy, PolicyBudgets, PolicyLimits
from packages.contracts.routine import Routine, RoutineStatus
from packages.contracts.spawn_ledger import SpawnLedger, SpawnDisposition
from packages.contracts.task import Task, TaskEntrypoint, TaskState

__all__ = [
    "EvaluationRecord",
    "HITLDecision",
    "Policy",
    "PolicyBudgets",
    "PolicyLimits",
    "Routine",
    "RoutineStatus",
    "SpawnDisposition",
    "SpawnLedger",
    "Task",
    "TaskEntrypoint",
    "TaskState",
    "new_id",
]
