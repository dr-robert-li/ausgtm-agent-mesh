"""SpawnLedger contract round-trip."""

from __future__ import annotations

from packages.contracts.spawn_ledger import ModelTier, SpawnLedger


def test_spawn_ledger_roundtrip() -> None:
    row = SpawnLedger(
        tenant_id="tenant_test",
        parent_task_id="task_PARENT",
        child_task_id="task_CHILD",
        child_agent_role="researcher",
        reason="decompose into research subtask",
        model_tier=ModelTier.M,
        risk_tier="read_safe",
        wave_index=1,
        depth=1,
    )
    again = SpawnLedger.model_validate(row.model_dump(mode="json"))
    assert again.spawn_id == row.spawn_id
    assert again.model_tier is ModelTier.M
