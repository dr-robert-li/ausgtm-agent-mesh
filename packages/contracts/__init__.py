"""Pydantic contracts for the Agentic Mesh POC.

These models mirror the reference architecture
(https://github.com/dr-robert-li/agentic-mesh-reference-arch, v0.1.3).

Conventions:
  - All models use `extra="forbid"`. Unknown fields are bugs.
  - IDs use the `{prefix}_{ULID}` form from the reference arch.
  - Timestamps are timezone-aware UTC.
  - Workflow state carries refs/IDs, never raw context payloads.
"""

from packages.contracts.egress import (
    GUARD_ORDER,
    EgressCheckRecord,
    EgressGuardName,
    EgressGuardResult,
    EgressGuardVerdict,
    EgressOverallVerdict,
    ProposedEgress,
)
from packages.contracts.evaluation import EvaluationRecord
from packages.contracts.hitl import HITLDecision
from packages.contracts.ids import new_id
from packages.contracts.intake import (
    FeasibilityCheck,
    FeasibilityVerdict,
    Intake,
)
from packages.contracts.knowledge_layer import (
    SCHEMA_VERSION as KL_SCHEMA_VERSION,
)
from packages.contracts.knowledge_layer import (
    Claim,
    ClaimEvidenceMap,
    Evidence,
    EvidenceKind,
    EvidencePointer,
    Freshness,
    FreshnessVerdict,
    KnowledgeLayerEntry,
)
from packages.contracts.policy import (
    EvidenceFetchBudget,
    Policy,
    PolicyBudgets,
    PolicyLimits,
)
from packages.contracts.routine import Routine, RoutineStatus
from packages.contracts.spawn_ledger import SpawnDisposition, SpawnLedger
from packages.contracts.task import (
    ProvenanceKind,
    ProvenanceRef,
    Task,
    TaskEntrypoint,
    TaskState,
)

__all__ = [
    "GUARD_ORDER",
    "KL_SCHEMA_VERSION",
    "Claim",
    "ClaimEvidenceMap",
    "EgressCheckRecord",
    "EgressGuardName",
    "EgressGuardResult",
    "EgressGuardVerdict",
    "EgressOverallVerdict",
    "EvaluationRecord",
    "Evidence",
    "EvidenceFetchBudget",
    "EvidenceKind",
    "EvidencePointer",
    "FeasibilityCheck",
    "FeasibilityVerdict",
    "Freshness",
    "FreshnessVerdict",
    "HITLDecision",
    "Intake",
    "KnowledgeLayerEntry",
    "Policy",
    "PolicyBudgets",
    "PolicyLimits",
    "ProposedEgress",
    "ProvenanceKind",
    "ProvenanceRef",
    "Routine",
    "RoutineStatus",
    "SpawnDisposition",
    "SpawnLedger",
    "Task",
    "TaskEntrypoint",
    "TaskState",
    "new_id",
]
