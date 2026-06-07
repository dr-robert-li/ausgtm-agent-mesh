"""E2E-03 live variant (D-06) — REAL model fallback + REAL cents-cap budget-halt.

OPT-IN ONLY. The whole module is ``@pytest.mark.live`` and every test depends on the
``live_creds`` fixture, so the default ``make test`` run NEVER reaches a real provider
(this module is ``deselected`` without ``-m live`` and SKIPS loudly without creds).

This is the "real seams" half of the E2E-03 combined run proven creds-free in
``test_e2e_failure_modes.py``. It mirrors that test's two stages with genuine
boundaries:

  STAGE A (real fallback, D-06): a dedicated live-lane Router pairs a deterministically
    broken Vertex primary with a REAL Anthropic fallback. A genuine Vertex provider
    error propagates and the REAL Anthropic deployment serves — a real provider error
    is NOT a faked boundary (contrast the stub lane).

  STAGE B (real cents-cap halt, D-08): a FEW-CENTS budget cap ($0.02) is set AND a tiny
    over-cap ledger row is seeded so the REAL pre-call ``BudgetTracker.check`` in the
    PRODUCTION ``Worker.process`` -> ``graph._delegate`` path raises ``BudgetExceeded``
    DETERMINISTICALLY and the run halts for PENNIES, transitioning the task to a governed
    FAILED terminal with an auto-emitted ``budget_halt`` gateway_event. NO provider call
    happens beyond the cap (a leak guard proves it), so the halt leg spends ZERO model
    tokens; only the Stage-A fallback makes a single tiny real Anthropic call.

D-08 SPEND BOUND (T-07-07 mitigation): the cap is a few cents
(``MODEL_MONTHLY_BUDGET_USD`` / per-task cap = $0.02) and the halt fires BEFORE any model
call, so the run never burns toward the $50 cap.

DETERMINISM NOTE (robustness): the production graph enters at ``planner_node``, which
delegates at a HARD-CODED ``high_complexity`` tier (not from ``MODEL_ROUTE_PROFILE``), and
the pre-call estimate is computed via ``litellm.cost_per_token`` whose price map can have
per-model gaps (STATE.md: ``gemini-1.5-flash`` low-complexity route unmapped). Rather than
rely on the natural estimate happening to exceed $0.02, Stage B seeds a small over-cap
``BudgetEvent`` (mirroring the default lane), so the REAL ``budget.check`` halt is robust
to the pricing-map state while Stage A still exercises the REAL provider boundary.

LIVE-LANE INDUCER (Stage A, runtime decision; mirrors test_cascade_live.py): the broken
primary uses a NONEXISTENT Vertex model id so it deterministically errors into litellm's
general fallbacks path. If at execution time it hard-fails as a 4xx that does NOT trigger
the general fallbacks list, switch to a 5xx-class inducer (e.g. an invalid
``vertex_location``); the chosen inducer is recorded in the SUMMARY, never hardcoded into
the default suite.

NOTE (no stale caveat): unlike the older test_cascade_live.py, this test does NOT manually
record the halt gateway_event — it drives the PRODUCTION ``Worker.process`` path, which
auto-emits the ``budget_halt`` event today (proven by test_budget_halt_governed.py). We
assert on the production-emitted event, not a hand-written one.
"""

from __future__ import annotations

import os

import pytest

from agent_mesh.contracts.enums import Entrypoint, TaskState
from agent_mesh.contracts.models import BudgetEvent, TaskRecord
from agent_mesh.services import repository as repo_module
from agent_mesh.services.repository import InMemoryRepository
from agent_mesh.worker import graph as graph_module
from agent_mesh.worker import model_gateway as mg
from agent_mesh.worker.runner import Worker

pytestmark = pytest.mark.live  # whole module is opt-in live lane

# --- Stage A: live-lane fallback inducer (broken Vertex primary -> real Anthropic) ---
_BROKEN_VERTEX_MODEL = "vertex_ai/gemini-does-not-exist-9p"
_REAL_ANTHROPIC_MODEL = "anthropic/claude-sonnet-4-6"
_PRIMARY = "live-broken-primary"
_FALLBACK = "live-anthropic-fallback"

# --- Stage B: cents-cap halt (D-08) ---
_CENTS_CAP = 0.02  # MODEL_MONTHLY_BUDGET_USD=0.02 — pennies, cheapest tier
_TENANT = "t-live"
_CLIENT = "c-live"


def _build_live_router():
    """A dedicated live-lane Router (NOT the shared yaml): broken Vertex primary +
    real Anthropic fallback. Built inline so the default suite's config is untouched."""
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


def test_e2e_03_live_real_fallback_then_real_cents_cap_halt(live_creds, monkeypatch):
    """E2E-03 live: a REAL Vertex->Anthropic fallback recovers, THEN a REAL cents-cap
    budget breach halts a production run to a governed FAILED terminal for pennies."""

    # =====================================================================
    # STAGE A — REAL model fallback (D-06): a genuine Vertex error cascades to a
    # REAL Anthropic response (not a mock). Needs both Vertex and Anthropic creds.
    # =====================================================================
    if not (os.getenv("VERTEX_PROJECT_ID") and os.getenv("ANTHROPIC_API_KEY")):
        pytest.skip("needs both VERTEX_PROJECT_ID and ANTHROPIC_API_KEY for the live cascade")

    router = _build_live_router()
    resp = router.completion(
        model=_PRIMARY,
        messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        max_tokens=16,  # bound the live spend to a few tokens
    )
    served_model = resp.model or ""
    assert "claude" in served_model.lower(), (
        f"expected the REAL Anthropic fallback to serve, got model={served_model!r}"
    )
    assert resp.choices[0].message.content, "Anthropic returned no content"

    # =====================================================================
    # STAGE B — REAL cents-cap budget halt (D-08): drive the PRODUCTION
    # Worker.process -> graph._delegate halt path with a few-cents cap. The real
    # BudgetTracker.check raises BEFORE any provider call, so the run halts to FAILED
    # for pennies (zero model tokens spent on this leg). The over-cap ledger row makes
    # the halt deterministic regardless of the litellm price-map state (see docstring).
    # =====================================================================
    monkeypatch.setenv("TENANT_ID", _TENANT)
    monkeypatch.setenv("CLIENT_SLUG", _CLIENT)
    # Few-cents cap (D-08 spend bound, T-07-07): the breach fires for pennies.
    monkeypatch.setenv("MODEL_MONTHLY_BUDGET_USD", str(_CENTS_CAP))
    monkeypatch.setenv("MODEL_PER_TASK_CAP", str(_CENTS_CAP))

    repo = InMemoryRepository()
    monkeypatch.setattr(repo_module, "_SINGLETON", repo)

    task = TaskRecord(
        tenant_id=_TENANT,
        client_slug=_CLIENT,
        entrypoint=Entrypoint.API,
        requester={"requester_id": _TENANT, "entrypoint": "api"},
        session_id="s1",
        prompt="summarize the latest research and email it",
    )
    repo.create_task(task)
    repo.transition_task(task.task_id, TaskState.QUEUED, note="queued")

    # Seed a tiny over-cap ledger row for the budget owner (== settings.tenant_id) so
    # the next real budget.check raises BEFORE any model call — deterministic against the
    # cents cap, robust to litellm price-map gaps (the planner delegates at a hard-coded
    # high_complexity tier; we don't rely on the natural estimate exceeding $0.02).
    repo.record_budget_event(
        BudgetEvent(
            tenant_id=_TENANT,
            client_slug=_CLIENT,
            budget_owner=_TENANT,
            task_id=None,
            model="high-complexity",
            prompt_tokens=1,
            completion_tokens=1,
            estimated_cost_usd=_CENTS_CAP + 0.01,  # just past the few-cents cap
        )
    )

    # Force the real _delegate path. budget.check raises BEFORE get_chat_model — a leak
    # guard proves no real provider call (and therefore no real spend) happens past the cap.
    monkeypatch.setattr(graph_module, "_model_credentials_present", lambda: True)

    leaked = {"called": False}

    def _boom(tier, settings):  # pragma: no cover - must never run past the halt
        leaked["called"] = True
        raise AssertionError("provider construction reached past the cents-cap halt")

    monkeypatch.setattr(mg, "get_chat_model", _boom)

    state = Worker(repo=repo).process(task.task_id)

    # Governed FAILED terminal + exactly one PRODUCTION-emitted budget_halt event.
    assert state == TaskState.FAILED.value
    final = repo.get_task(task.task_id)
    assert final is not None and final.state == TaskState.FAILED.value

    events = repo.list_gateway_events(task.task_id, _TENANT)
    halt = [e for e in events if e.model_route == "budget_halt"]
    assert len(halt) == 1, "exactly one budget_halt gateway_event expected on the halt"
    assert halt[0].tenant_id == _TENANT and halt[0].task_id == task.task_id
    assert halt[0].provider_status is None  # no provider reached

    # No real provider/spend leaked past the cents cap (the _boom guard never ran).
    assert leaked["called"] is False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-m", "live", "-v"]))
