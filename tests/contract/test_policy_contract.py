"""Policy contract — defaults and the new evidence_fetch_budget."""

from __future__ import annotations

from packages.contracts.policy import (
    EvidenceFetchBudget,
    Policy,
    PolicyBudgets,
    PolicyLimits,
)


def test_policy_roundtrip_with_defaults() -> None:
    p = Policy(tenant_id="tenant_test", scope="tenant:*")
    again = Policy.model_validate(p.model_dump(mode="json"))
    assert again.limits.max_waves == 3
    assert again.limits.max_child_agents_per_wave == 5
    assert again.limits.max_recursion_depth == 1


def test_evidence_fetch_budget_default_present_on_policy() -> None:
    """v0.1.3: budgets include an autonomy budget for KL reads/refetches."""
    p = Policy(tenant_id="tenant_test", scope="tenant:*")
    assert isinstance(p.budgets.evidence_fetch_budget, EvidenceFetchBudget)
    assert p.budgets.evidence_fetch_budget.max_reads > 0
    assert p.budgets.evidence_fetch_budget.max_refetches >= 0
    assert p.budgets.evidence_fetch_budget.max_stale_acceptance >= 0


def test_evidence_fetch_budget_overrides() -> None:
    budgets = PolicyBudgets(
        evidence_fetch_budget=EvidenceFetchBudget(
            max_reads=10,
            max_refetches=2,
            max_stale_acceptance=0,
        )
    )
    p = Policy(
        tenant_id="tenant_test",
        scope="routine:weekly_revops",
        limits=PolicyLimits(),
        budgets=budgets,
    )
    again = Policy.model_validate(p.model_dump(mode="json"))
    assert again.budgets.evidence_fetch_budget.max_reads == 10
    assert again.budgets.evidence_fetch_budget.max_stale_acceptance == 0
