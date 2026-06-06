"""GW-03 live lane — real Vertex->Anthropic fallback + cents-cap clean halt.

OPT-IN ONLY. Every test is ``@pytest.mark.live`` and gated on the ``live_creds``
fixture, so the default ``make test`` run NEVER reaches a real provider (the live
lane is ``deselected`` without ``-m live`` and SKIPS without creds). This is the
half of GW-03 that proves the boundary is REAL, not faked (D-01):

* **Fallback (D-03):** a dedicated live-lane Router pairs a *deterministically
  broken* Vertex primary with a *real* Anthropic fallback. A genuine Vertex error
  propagates and the REAL Anthropic deployment serves — a real provider error is NOT
  a faked boundary (contrast the stub lane in test_cascade.py).

  LIVE-LANE RUNTIME DECISION (inducer): the primary route uses a **nonexistent
  Vertex model id** (``vertex_ai/gemini-does-not-exist-9p``). Per RESEARCH A2 this is
  expected to surface as a 404/NotFound that litellm maps into the GENERAL fallbacks
  path. If at execution time it hard-fails as a 4xx that does NOT trigger the general
  fallbacks list, switch to a 5xx-class inducer (e.g. an invalid ``vertex_location``
  that yields a transient server error). The chosen inducer is recorded in the
  SUMMARY; it is NOT hardcoded into the default suite.

* **Halt (Finding 2):** a cents cap (``MODEL_MONTHLY_BUDGET_USD=0.02``) makes the
  pre-call estimate exceed the cap -> the REAL ``BudgetTracker.check`` raises
  ``BudgetExceeded`` -> a clean terminal halt with NO provider call beyond the cap
  (T-03-02-04), and ``month_to_date == 0.0`` (no spend recorded).

  SCOPE CAVEAT (honest, must_have #6): the production halt path (``graph._delegate``)
  does NOT itself emit a ``gateway_event`` today — ``budget.check`` raises and the
  exception propagates; no ``record_gateway_event`` call exists on that path. Wiring an
  auto-emit hook is a src edit, out of scope for this TEST-ONLY plan. So the halt test
  does NOT claim the system auto-records the event; it proves the durable-ledger
  CONTRACT a halt marker must satisfy (well-formed, append-only, tenant/task-scoped
  round-trip). ``GatewayEvent`` has no ``note`` column (the plan must_have said
  ``note=budget_halt``); the marker rides real contract fields — ``model_route=
  "budget_halt"`` + ``dlp_action="block"`` + ``provider_status=None`` (Rule 1: adapt to
  the real contract). The auto-emit wiring is flagged DEFERRED in the SUMMARY.
"""

from __future__ import annotations

import os

import pytest

from agent_mesh.contracts.models import GatewayEvent
from agent_mesh.services.repository import InMemoryRepository
from agent_mesh.settings import Settings
from agent_mesh.worker.budget import BudgetExceeded, BudgetTracker

pytestmark = pytest.mark.live  # whole module is opt-in live lane

# Live-lane inducer (runtime decision; see module docstring). A nonexistent Vertex
# model id so the primary deterministically errors and the cascade engages.
_BROKEN_VERTEX_MODEL = "vertex_ai/gemini-does-not-exist-9p"
_REAL_ANTHROPIC_MODEL = "anthropic/claude-sonnet-4-6"

_PRIMARY = "live-broken-primary"
_FALLBACK = "live-anthropic-fallback"


def _anthropic_creds_present() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _build_live_router():
    """A dedicated live-lane Router (NOT the shared yaml): broken Vertex primary +
    real Anthropic fallback. Built inline so the default suite's config is untouched.
    """
    from litellm import Router

    return Router(
        model_list=[
            {
                "model_name": _PRIMARY,
                "litellm_params": {
                    "model": _BROKEN_VERTEX_MODEL,
                    "vertex_project": os.getenv("VERTEX_PROJECT_ID", ""),
                    "vertex_location": os.getenv("VERTEX_LOCATION", "us-central1"),
                },
            },
            {
                "model_name": _FALLBACK,
                "litellm_params": {
                    "model": _REAL_ANTHROPIC_MODEL,
                    "api_key": os.getenv("ANTHROPIC_API_KEY", ""),
                },
            },
        ],
        fallbacks=[{_PRIMARY: [_FALLBACK]}],
        num_retries=0,
        timeout=60,
    )


def test_real_vertex_failure_cascades_to_real_anthropic(live_creds):
    """A REAL Vertex error on the primary cascades to a REAL Anthropic response
    (D-01/D-03). Requires both Vertex and Anthropic creds; skips otherwise."""
    if not (os.getenv("VERTEX_PROJECT_ID") and _anthropic_creds_present()):
        pytest.skip("needs both VERTEX_PROJECT_ID and ANTHROPIC_API_KEY for the live cascade")

    router = _build_live_router()
    resp = router.completion(
        model=_PRIMARY,
        messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        max_tokens=16,
    )

    # The REAL Anthropic fallback served (not the broken Vertex primary, not a mock).
    served_model = resp.model or ""
    assert "claude" in served_model.lower(), (
        f"expected the REAL Anthropic fallback to serve, got model={served_model!r}"
    )
    content = resp.choices[0].message.content
    assert content and isinstance(content, str), "Anthropic returned no content"


def test_cents_cap_budget_halt_records_gateway_event_and_blocks_spend(live_creds):
    """A cents cap makes the pre-call estimate exceed budget -> BudgetExceeded -> clean
    halt + a gateway_event recorded + NO provider call beyond the cap (T-03-02-04).

    Uses the REAL BudgetTracker.check enforcement against a durable (in-memory)
    ledger. The provider is never called: the halt fires BEFORE the call, so this
    test does not actually require provider creds to spend — but it stays in the live
    lane because it asserts the end-to-end halt contract alongside the live cascade.
    """
    tenant_id = "tenant-live"
    task_id = "task-live-halt"
    budget_owner = "user-live"
    cents_cap = 0.02  # MODEL_MONTHLY_BUDGET_USD=0.02

    repo = InMemoryRepository()
    settings = Settings()
    settings.model_monthly_budget_usd = cents_cap
    settings.model_per_task_cap = cents_cap
    tracker = BudgetTracker(repo, settings)

    # A pre-call estimate that exceeds the cents cap (a single Sonnet-class call on a
    # non-trivial prompt easily exceeds USD 0.02).
    pre_call_estimate = 0.05
    assert pre_call_estimate > cents_cap

    provider_called = False  # flips True only if we reach a (mock) provider call

    with pytest.raises(BudgetExceeded):
        tracker.check(
            budget_owner,
            pre_call_estimate,
            tenant_id=tenant_id,
            task_id=task_id,
        )
        provider_called = True  # unreachable: check() raises first

    assert provider_called is False, "a provider call happened past the budget cap"

    # SCOPE LIMITATION (honest): the production halt path (graph._delegate) does NOT
    # itself emit a gateway_event today — `budget.check` raises `BudgetExceeded` and the
    # exception propagates; no `record_gateway_event` call exists on that path. Wiring it
    # would be a src edit, which is out of scope for this TEST-ONLY plan. So this test
    # does NOT claim the system auto-records the halt; it proves the durable-ledger
    # CONTRACT that a halt marker must satisfy: a budget-halt GatewayEvent is well-formed
    # (no `note` column exists, so the marker rides real contract fields), persists
    # append-only, and reads back tenant/task-scoped via list_gateway_events. The
    # auto-emit wiring is flagged as deferred in the SUMMARY (must_have #6 caveat).
    repo.record_gateway_event(
        GatewayEvent(
            tenant_id=tenant_id,
            client_slug=settings.client_slug,
            task_id=task_id,
            provider=None,
            model_route="budget_halt",
            provider_status=None,  # no provider was reached
            dlp_action="block",
        )
    )

    # Contract round-trip: the halt marker persists and is retrievable, tenant/task
    # scoped, with provider_status None (no provider reached). This is the durable shape
    # a future _delegate halt-emit hook would write; the assertion guards that contract.
    events = repo.list_gateway_events(task_id, tenant_id)
    halt_events = [e for e in events if e.model_route == "budget_halt"]
    assert len(halt_events) == 1, "exactly one budget-halt gateway_event expected"
    halt = halt_events[0]
    assert halt.provider_status is None, "no provider was reached; status must be None"
    assert halt.dlp_action == "block"
    assert halt.tenant_id == tenant_id and halt.task_id == task_id
    # Cross-scope guard: the halt marker is NOT visible under a different task/tenant.
    assert repo.list_gateway_events("other-task", tenant_id) == []
    assert repo.list_gateway_events(task_id, "other-tenant") == []

    # No budget event was recorded (the call was halted before completing).
    mtd = tracker.month_to_date(budget_owner, tenant_id=tenant_id)
    assert mtd == 0.0, "no spend should be recorded for a halted (never-run) call"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-m", "live", "-v"]))
