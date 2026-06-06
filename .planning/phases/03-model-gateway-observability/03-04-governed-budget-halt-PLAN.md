---
plan_id: 03-04-governed-budget-halt
phase: "03"
wave: 3
gap_closure: true
autonomous: true
closes_gap: "03-VERIFICATION Gap 1 — budget-halt not governed (GW-03 / OBS-01)"
req_ids: [GW-03, OBS-01]
files_modified:
  - src/agent_mesh/worker/graph.py
  - src/agent_mesh/worker/orchestrator.py
  - tests/test_budget_halt_governed.py
---

<objective>
Close 03-VERIFICATION Gap 1: make the production budget-halt path **governed and
observable**, not an untyped exception. Today `BudgetExceeded` raised by
`budget.check()` inside `graph._delegate` propagates as an untyped LangGraph node
exception — no `gateway_event` audit row is written (`record_gateway_event` has
ZERO production call sites) and no governed terminal task state is set.

After this plan a budget halt MUST: (1) write a `gateway_event` audit row marking
the halt, (2) produce a governed terminal FAILED task state via the orchestrator,
(3) be proven by a production-path test that drives the real `_delegate` halt — not
a manual `repo.record_gateway_event()` call.

Scope guardrails: do NOT touch SEC-01/02 approval code, the CF chokepoint, or the
Router/budget-enforcement math. Pre-call spend-stop behavior stays exactly as is —
this plan only adds governance AROUND the existing halt. Keep the default suite
green with no cloud deps.
</objective>

<tasks>

<task id="1" name="Audit-row on halt in _delegate (GW-03/OBS-01)">
In `src/agent_mesh/worker/graph.py`, wrap the existing `budget.check()` call site in
`_delegate` so that when `BudgetExceeded` is raised, BEFORE it propagates, a
`gateway_event` row is written via the repository and then the exception re-raises
unchanged (pre-call spend-stop semantics preserved).

- Read the real `GatewayEvent` dataclass / `record_gateway_event` signature in
  `src/agent_mesh/services/repository.py` and use ONLY fields that exist. Per the
  03-02 deviation, `GatewayEvent` has no free-text `note` field — carry the halt
  marker in `model_route="budget_halt"` plus `dlp_action`/`provider_status` as the
  existing schema allows.
- The row MUST be tenant- and task-scoped (`tenant_id`, `task_id` from the call
  context / MeshState).
- Idempotency: a single halt writes exactly one `budget_halt` row. Do not emit on
  the normal (non-halt) path.
- Re-raise `BudgetExceeded` after the row is written — do NOT swallow it here.

RED first: add a failing test asserting that after a halted `_delegate` exactly one
`gateway_event` with `model_route="budget_halt"` exists for the task. GREEN: implement.
</task>

<task id="2" name="Governed terminal FAILED state in orchestrator (GW-03)">
In `src/agent_mesh/worker/orchestrator.py`, catch the `BudgetExceeded` that
propagates out of the graph run and convert it into a governed terminal outcome:
- Transition the task to a FAILED terminal `TaskState` via the existing
  `transition`/repository contract (use the real enum value present in the codebase;
  do not invent one), with a `note` explaining budget halt.
- Return an `OrchestrationResult` on the halt path consistent with the other return
  paths (set `trace_id`, status fields the same way the existing terminal paths do)
  rather than letting the exception escape `run_mesh`/the resume path untyped.
- Cover BOTH entry paths if both can call the budget path: the fresh `run_mesh` path
  and the resume-from-checkpoint path.

RED first: failing test asserting a budget halt yields a FAILED terminal task record
(not an unhandled exception) and an `OrchestrationResult` with a set `trace_id`.
</task>

<task id="3" name="Production-path governed-halt test + full-suite green">
Create `tests/test_budget_halt_governed.py` proving the END-TO-END production
contract with NO cloud deps (use the in-memory repo + a forced-over-budget ledger /
tiny cents cap, same stub mechanics 03-01/03-02 used):
- Driving a real delegated model call over budget produces: (a) exactly one
  `gateway_event` row with `model_route="budget_halt"`, tenant/task scoped; (b) a
  FAILED terminal task state; (c) no provider call leaked past the halt.
- Negative control: a within-budget call writes NO `budget_halt` row and reaches a
  normal terminal state.
- Assert via the durable repository round-trip (list events / get_task), not by
  inspecting in-process attributes only.

Gate: `PYTHONPATH=src python -m pytest -q` stays green (expect prior 130 passed to
rise by the new tests, 0 failures); `ruff check src/agent_mesh tests` clean;
`make smoke` SMOKE OK. Grep gate: `record_gateway_event` now has >=1 production call
site in `src/agent_mesh/worker/graph.py`.
</task>

</tasks>

<must_haves>
1. A halted `_delegate` writes exactly one tenant/task-scoped `gateway_event` with `model_route="budget_halt"`.
2. `record_gateway_event` has >=1 production call site (was 0).
3. A budget halt yields a governed FAILED terminal task state, not an untyped exception escaping `run_mesh`/resume.
4. `OrchestrationResult` on the halt path sets `trace_id` like the other paths (OBS-01 correlation preserved).
5. Pre-call spend-stop semantics unchanged; no SEC-01/02, CF-chokepoint, or Router-math edits.
6. Default suite green (no cloud deps), ruff clean, smoke OK; production-path test drives the real halt, not a manual event write.
</must_haves>
