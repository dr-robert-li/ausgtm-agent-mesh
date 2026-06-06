"""GW-01: durable budget ledger (D-04/D-05).

The budget enforcer is durable-ledger-backed: ``check()`` reads month-to-date from
the ``budget_ledger`` table (tenant-scoped) and raises ``BudgetExceeded`` before a
model call when the call would exceed the USD $50/month per-user cap or the per-task
cap; ``record()`` persists the actual cost. The in-memory repository mirrors the SQL
behaviour so ``make test`` stays green with no Postgres.

These tests run on the ``InMemoryRepository`` path (no cloud deps).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agent_mesh.contracts.models import BudgetEvent, GatewayEvent
from agent_mesh.services.repository import InMemoryRepository
from agent_mesh.settings import Settings
from agent_mesh.worker.budget import BudgetExceeded, BudgetTracker


def _event(
    *,
    tenant_id: str = "tenant-a",
    budget_owner: str = "user-1",
    task_id: str | None = "task-1",
    cost: float,
) -> BudgetEvent:
    return BudgetEvent(
        tenant_id=tenant_id,
        client_slug="client-a",
        budget_owner=budget_owner,
        task_id=task_id,
        model="high-complexity",
        prompt_tokens=10,
        completion_tokens=20,
        estimated_cost_usd=cost,
    )


# --- repository: durable ledger methods ------------------------------------


def test_record_budget_event_is_append_only_and_returns_event():
    repo = InMemoryRepository()
    ev = _event(cost=1.25)
    out = repo.record_budget_event(ev)
    assert out.budget_event_id == ev.budget_event_id
    # ON CONFLICT DO NOTHING: a re-record of the same id does not double-count.
    repo.record_budget_event(ev)
    mtd = repo.budget_month_to_date(
        "tenant-a", "user-1", datetime.now(UTC) - timedelta(days=1)
    )
    assert mtd == pytest.approx(1.25)


def test_budget_month_to_date_sums_since_and_defaults_zero():
    repo = InMemoryRepository()
    since = datetime.now(UTC) - timedelta(days=1)
    assert repo.budget_month_to_date("tenant-a", "user-1", since) == 0.0
    repo.record_budget_event(_event(cost=2.0))
    repo.record_budget_event(_event(cost=3.0, task_id="task-2"))
    assert repo.budget_month_to_date("tenant-a", "user-1", since) == pytest.approx(5.0)


def test_budget_month_to_date_is_tenant_scoped():
    """DUR-02: a cross-tenant read NEVER returns another tenant's rows."""
    repo = InMemoryRepository()
    since = datetime.now(UTC) - timedelta(days=1)
    repo.record_budget_event(_event(tenant_id="tenant-a", cost=10.0))
    # Same owner id, different tenant — must not leak into tenant-b's total.
    assert repo.budget_month_to_date("tenant-b", "user-1", since) == 0.0
    assert repo.budget_month_to_date("tenant-a", "user-1", since) == pytest.approx(10.0)


def test_gateway_event_record_and_list_tenant_scoped():
    repo = InMemoryRepository()
    ev_a = GatewayEvent(
        tenant_id="tenant-a", client_slug="client-a", task_id="task-1", provider="anthropic"
    )
    ev_b = GatewayEvent(
        tenant_id="tenant-b", client_slug="client-b", task_id="task-1", provider="vertex_ai"
    )
    repo.record_gateway_event(ev_a)
    repo.record_gateway_event(ev_b)
    rows = repo.list_gateway_events("task-1", "tenant-a")
    assert [r.gateway_event_id for r in rows] == [ev_a.gateway_event_id]


# --- BudgetTracker: enforcement --------------------------------------------


def _tracker(repo: InMemoryRepository, *, monthly: float = 50.0, per_task: float | None = None):
    settings = Settings()
    settings.model_monthly_budget_usd = monthly
    settings.model_per_task_cap = per_task if per_task is not None else monthly
    return BudgetTracker(repo, settings)


def test_check_passes_under_cap():
    repo = InMemoryRepository()
    tracker = _tracker(repo)
    # No spend yet; a $5 call is well under the $50 cap.
    tracker.check("user-1", 5.0, tenant_id="tenant-a", task_id="task-1")


def test_check_raises_when_per_user_cap_exceeded():
    repo = InMemoryRepository()
    tracker = _tracker(repo, monthly=10.0)
    repo.record_budget_event(_event(cost=8.0))
    with pytest.raises(BudgetExceeded):
        tracker.check("user-1", 5.0, tenant_id="tenant-a", task_id="task-1")


def test_check_raises_when_per_task_cap_exceeded():
    """Per-task cap is tighter than per-user; the task cap halts first (D-05)."""
    repo = InMemoryRepository()
    tracker = _tracker(repo, monthly=50.0, per_task=2.0)
    repo.record_budget_event(_event(cost=1.5, task_id="task-1"))
    with pytest.raises(BudgetExceeded):
        tracker.check("user-1", 1.0, tenant_id="tenant-a", task_id="task-1")
    # A different task still has its own headroom.
    tracker.check("user-1", 1.0, tenant_id="tenant-a", task_id="task-2")


def test_record_persists_event_with_task_id():
    """D-05 attribution: every ledger row carries task_id."""
    repo = InMemoryRepository()
    tracker = _tracker(repo)
    ev = _event(cost=4.0, task_id="task-9")
    tracker.record(ev)
    rows = repo.budget_month_to_date(
        "tenant-a", "user-1", datetime.now(UTC) - timedelta(days=1)
    )
    assert rows == pytest.approx(4.0)
    # The persisted event retains its task_id.
    persisted = next(iter(repo._budget_events.values()))
    assert persisted.task_id == "task-9"


def test_month_to_date_reads_through_repository():
    repo = InMemoryRepository()
    tracker = _tracker(repo)
    repo.record_budget_event(_event(cost=7.0))
    assert tracker.month_to_date("user-1", tenant_id="tenant-a") == pytest.approx(7.0)
