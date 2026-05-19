"""Intake contract round-trip + S-tier feasibility constraints."""

from __future__ import annotations

import pytest
from packages.contracts.intake import (
    FeasibilityCheck,
    FeasibilityVerdict,
    Intake,
)
from packages.contracts.task import TaskEntrypoint
from pydantic import ValidationError


def _feasibility() -> FeasibilityCheck:
    return FeasibilityCheck(
        verdict=FeasibilityVerdict.feasible,
        reason="goal maps to known tool plan",
        checked_tools=["slack", "monday"],
    )


def test_intake_roundtrip() -> None:
    i = Intake(
        tenant_id="tenant_test",
        entrypoint=TaskEntrypoint.slack,
        actor="U12345",
        goal="post sales weekly to #revops",
        feasibility=_feasibility(),
    )
    again = Intake.model_validate(i.model_dump(mode="json"))
    assert again.intake_id == i.intake_id
    assert again.feasibility.model_tier == "S"


def test_feasibility_locked_to_s_tier_by_default() -> None:
    """Intake feasibility checks are S-tier by contract. M/L is a smell."""
    fc = _feasibility()
    assert fc.model_tier == "S"


def test_ambiguous_can_carry_disambiguating_question() -> None:
    fc = FeasibilityCheck(
        verdict=FeasibilityVerdict.ambiguous,
        reason="goal references two possible boards",
        disambiguating_question="Did you mean the Sales or RevOps board?",
    )
    assert fc.disambiguating_question is not None


def test_intake_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Intake.model_validate(
            {
                "tenant_id": "tenant_test",
                "entrypoint": "slack",
                "actor": "U1",
                "goal": "x",
                "feasibility": {
                    "verdict": "feasible",
                    "reason": "ok",
                    "model_tier": "S",
                },
                "rogue_field": 1,
            }
        )
