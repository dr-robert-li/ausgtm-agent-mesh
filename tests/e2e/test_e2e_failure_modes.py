"""E2E-03 (ROADMAP SC-3) default lane — ONE combined run proving, in order:

    model fallback  ->  in-cascade retry-recovery  ->  budget-limit halt  ->  FAILED

composing the already-hardened Phase-3 seams (GW-03 cascade + the governed budget
halt) with NO new fault-injection harness (D-05). Staged asserts within a single
test; the contract is "exercised together in order".

RETRY-LEG RESOLUTION (resolves open design decision 1 — the deterministic "job
retry" element has no standalone analog):

  * fallback + retry-recovery = ONE seam: the litellm cascade. ``mock_testing_fallbacks=
    True`` forces the primary deployment to raise ``InternalServerError`` *before* any
    real completion runs, and the Router cascades to the configured fallback, which
    serves deterministically via ``mock_response``. THAT recovery IS the mid-run
    retry-then-recover (option b — no new harness; honors D-05).
  * the literal Pub/Sub job-redelivery notion (``--max-delivery-attempts=5`` +
    ``--dead-letter-topic``) is asserted as deploy-config consistency in DEP-01
    (plan 07-04), NOT via a new fault harness here. Both readings together cover the
    named three-part SC-3 criterion; neither is silently dropped.

CREDS-FREE: Stage A skips loudly if the litellm runtime extra is absent (the
``build_router`` import gate, mirroring tests/test_cascade.py:42-48). Stage B forces
the production budget-halt path with an over-cap ledger row + a monkeypatched
``_model_credentials_present`` so the real ``_delegate`` runs and ``budget.check``
raises BEFORE any provider is constructed — a ``get_chat_model`` leak-guard proves it.

SINGLETON DISCIPLINE (anti-split-brain, T-07-09): Stage B pins ONE
``InMemoryRepository`` as the process singleton (``repo_module._SINGLETON``) and pins
``TENANT_ID``/``CLIENT_SLUG`` so the task tenant, the breach-ledger row, the budget
owner, and the gateway_event scope are ALL the same tenant. The bare ``repo`` conftest
fixture is deliberately NOT used for the halt leg (it would not be the singleton the
production path resolves) — we replicate the ``governed_env`` pattern inline.

NO ``live`` marker on this module: the whole file is default-lane and creds-free.
"""

from __future__ import annotations

import pytest

from agent_mesh.contracts.enums import Entrypoint, TaskState
from agent_mesh.contracts.models import BudgetEvent, TaskRecord
from agent_mesh.services import repository as repo_module
from agent_mesh.services.repository import InMemoryRepository
from agent_mesh.worker import graph as graph_module
from agent_mesh.worker import model_gateway as mg
from agent_mesh.worker.runner import Worker

# --- Stage A constants (the fallback/retry-recovery seam, from the yaml cascade) ---
_PRIMARY_DEPLOYMENT = "low-complexity"   # vertex_ai/gemini-1.5-flash
_FALLBACK_MODEL = "gemini-1.5-pro"       # medium-complexity (the configured fallback)
_PRIMARY_MODEL = "gemini-1.5-flash"
_MOCK_CONTENT = "[fallback served]"

# --- Stage B constants (the governed budget-halt seam) ---
_TENANT = "t"
_CLIENT = "c"


def _build_router():
    """Build the real Router from ``config/model_gateway.config.yaml``; skip cleanly
    if the litellm runtime extra is absent (copy of tests/test_cascade.py:42-48).
    Stage A gates the whole combined run on this — the AC accepts a loud full skip."""
    from agent_mesh.worker.model_gateway import build_router

    try:
        return build_router()
    except Exception as exc:  # pragma: no cover - runtime extra missing
        pytest.skip(f"litellm runtime not installed: {exc}")


def test_e2e_03_fallback_recovery_then_governed_budget_halt(monkeypatch):
    """E2E-03 combined run: a fallback recovers mid-run (retry-recovery), THEN a
    budget breach halts the run to a governed, observable FAILED terminal.

    Ordering is forced by seam semantics: fallback+retry are mid-run recovery and
    must SUCCEED first; the budget then exhausts and the run halts to FAILED."""

    # =====================================================================
    # STAGE A — model fallback + in-cascade retry-recovery (the cascade IS the
    # mid-run retry; mock_testing_fallbacks forces the primary to raise, the
    # configured fallback recovers). See RETRY-LEG RESOLUTION in the module docstring.
    # =====================================================================
    router = _build_router()

    resp = router.completion(
        model=_PRIMARY_DEPLOYMENT,
        messages=[{"role": "user", "content": "hi"}],
        mock_testing_fallbacks=True,  # primary raises InternalServerError -> cascade
        mock_response=_MOCK_CONTENT,  # the fallback serves this deterministically
    )

    # The call SUCCEEDED (the primary's error did not propagate) and the FALLBACK
    # deployment served — i.e. the cascade retried-and-recovered mid-run.
    assert resp.choices[0].message.content == _MOCK_CONTENT
    assert resp.model == _FALLBACK_MODEL, (
        f"expected the FALLBACK deployment ({_FALLBACK_MODEL}) to serve (retry-recovery), "
        f"but ModelResponse.model was {resp.model!r}"
    )
    assert resp.model != _PRIMARY_MODEL, "the primary served — the cascade did not occur"

    # =====================================================================
    # STAGE B — governed budget-limit halt -> FAILED terminal (one observable
    # budget_halt gateway_event, no provider leak). Replicates the governed_env
    # singleton-pinning pattern inline (anti-split-brain).
    # =====================================================================
    monkeypatch.setenv("TENANT_ID", _TENANT)
    monkeypatch.setenv("CLIENT_SLUG", _CLIENT)
    repo = InMemoryRepository()
    monkeypatch.setattr(repo_module, "_SINGLETON", repo)

    # A QUEUED task in the pinned-singleton repo (ingress would queue it; the
    # worker's QUEUED -> RUNNING transition is legal, RECEIVED -> RUNNING is not).
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

    # Force over-budget: record an over-cap ledger row for the budget owner
    # (== settings.tenant_id) so the next budget.check raises BEFORE any model call.
    repo.record_budget_event(
        BudgetEvent(
            tenant_id=_TENANT,
            client_slug=_CLIENT,
            budget_owner=_TENANT,
            task_id=None,
            model="high-complexity",
            prompt_tokens=1,
            completion_tokens=1,
            estimated_cost_usd=100.0,  # well past the USD $50/month cap
        )
    )

    # Force the real _delegate path (no creds), then PROVE the halt short-circuits
    # before any provider: make get_chat_model explode if it is ever reached.
    monkeypatch.setattr(graph_module, "_model_credentials_present", lambda: True)

    leaked = {"called": False}

    def _boom(tier, settings):  # pragma: no cover - must never run past the halt
        leaked["called"] = True
        raise AssertionError("provider construction reached past the budget halt")

    monkeypatch.setattr(mg, "get_chat_model", _boom)

    state = Worker(repo=repo).process(task.task_id)

    # Governed terminal FAILED state (not COMPLETED, not an unhandled exception).
    assert state == TaskState.FAILED.value
    final = repo.get_task(task.task_id)
    assert final is not None and final.state == TaskState.FAILED.value

    # Exactly one observable budget_halt gateway_event, tenant/task scoped, no
    # provider leak (provider_status is None because no provider was reached).
    events = repo.list_gateway_events(task.task_id, _TENANT)
    halt = [e for e in events if e.model_route == "budget_halt"]
    assert len(halt) == 1, "exactly one budget_halt gateway_event expected on halt"
    assert halt[0].tenant_id == _TENANT and halt[0].task_id == task.task_id
    assert halt[0].provider_status is None  # no provider reached

    # No provider leaked past the halt (the _boom guard was never invoked).
    assert leaked["called"] is False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-m", "not live", "-v"]))
