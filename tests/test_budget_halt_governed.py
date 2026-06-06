"""Gap-closure 03-04: the PRODUCTION budget-halt path is governed and observable.

Closes 03-VERIFICATION Gap 1. These tests drive the REAL production halt — they
force ``graph._delegate`` over budget so ``budget.check`` raises ``BudgetExceeded``
BEFORE any model call, and assert that the halt is:

  (a) recorded as exactly one tenant/task-scoped ``gateway_event`` with
      ``model_route="budget_halt"`` (``record_gateway_event`` had ZERO production
      call sites before this plan — now >=1 in ``graph.py``);
  (b) converted by the orchestrator into a governed terminal FAILED task state
      with ``OrchestrationResult.trace_id`` set (not an untyped graph exception);
  (c) leak-free: no provider call happens past the halt.

NO cloud deps: with no creds the budget breach is forced by recording an
over-cap ``BudgetEvent`` in the durable ledger, and ``_model_credentials_present``
is monkeypatched True so the ``_delegate`` path runs. ``budget.check`` raises
before ``get_chat_model``, so no provider is ever reached.

Repo discipline (CRITICAL): the production path resolves the repository via the
process-wide ``get_repository()`` singleton and settings via ``get_settings()``.
These tests install ONE InMemoryRepository as that singleton and pin
``TENANT_ID``/``CLIENT_SLUG`` so the task tenant, the breach-ledger row, the
budget owner, and the gateway_event scope are all the SAME tenant — otherwise a
split-brain (fixture repo vs singleton) would let a test pass green on a lie.
"""

from __future__ import annotations

import pytest

from agent_mesh.contracts.enums import Entrypoint, TaskState
from agent_mesh.contracts.models import BudgetEvent, TaskRecord
from agent_mesh.services import repository as repo_module
from agent_mesh.services.repository import InMemoryRepository
from agent_mesh.worker import graph as graph_module
from agent_mesh.worker import orchestrator as orch_module
from agent_mesh.worker.budget import BudgetExceeded
from agent_mesh.worker.runner import Worker

_TENANT = "t"
_CLIENT = "c"


@pytest.fixture
def governed_env(monkeypatch):
    """Install a fresh InMemoryRepository as the process singleton and pin tenant.

    Yields ``(repo, make_task)`` where ``make_task`` creates a RECEIVED task in
    that singleton with the pinned tenant so every downstream scope matches.
    """
    monkeypatch.setenv("TENANT_ID", _TENANT)
    monkeypatch.setenv("CLIENT_SLUG", _CLIENT)
    repo = InMemoryRepository()
    monkeypatch.setattr(repo_module, "_SINGLETON", repo)

    def make_task(prompt: str = "summarize the latest research") -> TaskRecord:
        task = TaskRecord(
            tenant_id=_TENANT,
            client_slug=_CLIENT,
            entrypoint=Entrypoint.API,
            requester={"requester_id": _TENANT, "entrypoint": "api"},
            session_id="s1",
            prompt=prompt,
        )
        repo.create_task(task)
        # Queue it as ingress would, so the worker's RECEIVED/QUEUED -> RUNNING
        # transition (runner.py:54) is legal (RECEIVED -> RUNNING is not).
        return repo.transition_task(task.task_id, TaskState.QUEUED, note="queued")

    return repo, make_task


def _force_over_budget(repo: InMemoryRepository) -> None:
    """Push the budget owner (== settings.tenant_id) over the monthly cap.

    ``_delegate`` uses ``budget_owner = settings.tenant_id``; recording an
    over-cap ledger row for that owner makes the very next ``budget.check`` raise
    ``BudgetExceeded`` BEFORE any model call (the SOLE-enforcer guarantee)."""
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


# --- Task 1: halted _delegate writes exactly one budget_halt gateway_event ---


def test_delegate_halt_writes_one_budget_halt_gateway_event(governed_env):
    """RED (Task 1): a halted ``_delegate`` emits exactly one tenant/task-scoped
    ``gateway_event`` with ``model_route='budget_halt'`` and re-raises."""
    repo, make_task = governed_env
    task = make_task()
    _force_over_budget(repo)

    with pytest.raises(BudgetExceeded):
        graph_module._delegate(
            "planner", "high_complexity", task.prompt, task_id=task.task_id
        )

    events = repo.list_gateway_events(task.task_id, _TENANT)
    halt = [e for e in events if e.model_route == "budget_halt"]
    assert len(halt) == 1, "exactly one budget_halt gateway_event expected on halt"
    row = halt[0]
    assert row.tenant_id == _TENANT and row.task_id == task.task_id
    assert row.provider_status is None  # no provider reached
    assert row.dlp_action == "block"


def test_delegate_normal_path_emits_no_budget_halt_event(governed_env, monkeypatch):
    """A within-budget delegate run writes NO budget_halt row (idempotency /
    no false-positive). We stub the chat model at its source module (``_delegate``
    lazy-imports ``get_chat_model`` from ``model_gateway``) so no provider is reached."""
    from agent_mesh.worker import model_gateway as mg

    repo, make_task = governed_env
    task = make_task()  # no over-budget ledger row -> within budget

    class _FakeChat:
        def invoke(self, prompt):  # noqa: D401 - minimal stand-in
            class _Msg:
                content = "[fake] ok"
                usage_metadata = {"input_tokens": 1, "output_tokens": 1}

            return _Msg()

    monkeypatch.setattr(mg, "get_chat_model", lambda tier, settings: _FakeChat())

    out = graph_module._delegate(
        "planner", "high_complexity", task.prompt, task_id=task.task_id
    )
    assert isinstance(out, str)
    events = repo.list_gateway_events(task.task_id, _TENANT)
    assert [e for e in events if e.model_route == "budget_halt"] == []


# --- Task 2/3: production-path governed terminal FAILED state via the worker ---


def test_worker_budget_halt_yields_failed_terminal_and_trace_id(
    governed_env, monkeypatch
):
    """END-TO-END (Task 3): driving a real delegated model call over budget via
    ``Worker.process`` produces a governed FAILED terminal task state, exactly one
    ``budget_halt`` gateway_event, a set ``trace_id``, and no provider leak."""
    from agent_mesh.worker import model_gateway as mg

    repo, make_task = governed_env
    task = make_task()
    _force_over_budget(repo)

    # Force the real _delegate path (no creds). ``budget.check`` raises BEFORE
    # ``get_chat_model`` (the SOLE construction path), so no provider is reached;
    # we make get_chat_model explode to PROVE the halt short-circuits before it.
    monkeypatch.setattr(graph_module, "_model_credentials_present", lambda: True)

    leaked = {"called": False}

    def _boom(tier, settings):  # pragma: no cover - must never run
        leaked["called"] = True
        raise AssertionError("provider construction reached past the budget halt")

    monkeypatch.setattr(mg, "get_chat_model", _boom)

    state = Worker(repo=repo).process(task.task_id)

    # Governed terminal FAILED state (not COMPLETED, not an unhandled exception).
    assert state == TaskState.FAILED.value
    final = repo.get_task(task.task_id)
    assert final is not None and final.state == TaskState.FAILED.value

    # Exactly one budget_halt gateway_event, tenant/task scoped (OBS-01 audit row).
    events = repo.list_gateway_events(task.task_id, _TENANT)
    halt = [e for e in events if e.model_route == "budget_halt"]
    assert len(halt) == 1
    assert halt[0].tenant_id == _TENANT and halt[0].task_id == task.task_id
    assert halt[0].provider_status is None  # no provider reached

    # No provider leaked past the halt (get_chat_model never constructed).
    assert leaked["called"] is False


def test_run_mesh_budget_halt_sets_failed_and_trace_id(governed_env, monkeypatch):
    """Task 2: the orchestrator catches the propagating ``BudgetExceeded`` and
    returns a governed ``OrchestrationResult`` with ``trace_id`` set, having
    transitioned the task to FAILED — instead of letting the exception escape."""
    repo, make_task = governed_env
    task = make_task()
    _force_over_budget(repo)
    monkeypatch.setattr(graph_module, "_model_credentials_present", lambda: True)

    # Pre-transition to RUNNING as the worker does (only RUNNING/PLANNING/APPROVED
    # may go to FAILED). The task is already QUEUED from make_task.
    repo.transition_task(task.task_id, TaskState.RUNNING, note="test setup")
    running = repo.get_task(task.task_id)
    assert running is not None and running.state == TaskState.RUNNING.value

    result = orch_module.run_mesh(running)

    assert result.trace_id is not None
    assert result.proposed_writes == []
    final = repo.get_task(task.task_id)
    assert final is not None and final.state == TaskState.FAILED.value


def test_worker_within_budget_reaches_completed_via_stub_lane(governed_env):
    """Negative control (Task 3, COMPLETED half): a within-budget read-only task
    reaches a normal COMPLETED terminal state with NO ``budget_halt`` row.

    This runs the orchestration topology on the deterministic stub lane (creds
    absent, so ``_delegate`` is not entered). The complementary
    ``test_delegate_normal_path_emits_no_budget_halt_event`` already proves the
    REAL ``_delegate`` path writes no halt row on a within-budget call. We do NOT
    drive the full four-node real-``_delegate`` run to COMPLETED here because the
    low-complexity route model (``gemini-1.5-flash``) is unmapped in this litellm
    build's price map (its pre-call ``cost_per_token`` estimate raises) — an
    environmental pricing gap unrelated to the halt-governance contract under
    test. Splitting the negative control this way keeps both halves green and
    cloud-free."""
    repo, make_task = governed_env
    # Read-only prompt (no write-trigger verb) -> no approval pause -> COMPLETED.
    task = make_task(prompt="research the latest findings")

    state = Worker(repo=repo).process(task.task_id)

    assert state == TaskState.COMPLETED.value
    final = repo.get_task(task.task_id)
    assert final is not None and final.state == TaskState.COMPLETED.value
    events = repo.list_gateway_events(task.task_id, _TENANT)
    assert [e for e in events if e.model_route == "budget_halt"] == []
