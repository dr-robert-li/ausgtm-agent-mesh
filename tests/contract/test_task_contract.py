"""Task contract round-trip + extras-forbidden sanity."""

from __future__ import annotations

import pytest
from packages.contracts.task import (
    ProvenanceKind,
    ProvenanceRef,
    Task,
    TaskEntrypoint,
    TaskProvenance,
)
from pydantic import ValidationError


def _minimal_task() -> Task:
    return Task(
        tenant_id="tenant_test",
        entrypoint=TaskEntrypoint.slack,
        actor="U12345",
        goal="say hello",
        provenance=TaskProvenance(created_by="apps.slack"),
    )


def test_task_carries_v013_refs() -> None:
    """Workflow state holds refs, not payloads."""
    t = Task(
        tenant_id="tenant_test",
        entrypoint=TaskEntrypoint.slack,
        actor="U12345",
        goal="x",
        intake_id="intake_01HZX0000000000000000000",
        correlation_id="corr_01HZX0000000000000000000",
        claim_evidence_map_ref="cem_01HZX0000000000000000000",
        provenance=TaskProvenance(
            created_by="apps.slack",
            refs=[
                ProvenanceRef(
                    kind=ProvenanceKind.intake,
                    ref="intake_01HZX0000000000000000000",
                ),
            ],
        ),
    )
    again = Task.model_validate(t.model_dump(mode="json"))
    assert again.intake_id == t.intake_id
    assert again.correlation_id == t.correlation_id
    assert again.claim_evidence_map_ref == t.claim_evidence_map_ref
    assert again.provenance.refs[0].kind is ProvenanceKind.intake


def test_task_roundtrip() -> None:
    t = _minimal_task()
    again = Task.model_validate(t.model_dump(mode="json"))
    assert again.task_id == t.task_id
    assert again.goal == "say hello"


def test_task_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Task.model_validate(
            {
                "tenant_id": "tenant_test",
                "entrypoint": "slack",
                "actor": "U12345",
                "goal": "x",
                "provenance": {"created_by": "test"},
                "not_a_real_field": True,
            }
        )
