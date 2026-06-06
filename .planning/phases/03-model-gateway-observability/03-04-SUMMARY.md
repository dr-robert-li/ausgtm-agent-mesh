---
phase: 03-model-gateway-observability
plan: 04
subsystem: infra
tags: [langgraph, budget-governance, gateway-event, observability, litellm, otel]

# Dependency graph
requires:
  - phase: 03-model-gateway-observability
    provides: "GW-01 durable budget ledger + BudgetExceeded (03-01); GatewayEvent contract + record_gateway_event (03-02); OTel root span + trace_id on all OrchestrationResult paths (03-03)"
provides:
  - "Governed, observable production budget-halt path: a budget breach in graph._delegate writes exactly one tenant/task-scoped budget_halt gateway_event and the orchestrator converts the propagating BudgetExceeded into a FAILED terminal task state with trace_id set"
  - "record_gateway_event now has a production call site (was 0) wired from graph.py"
  - "Runner terminal-state guard so an orchestrator-owned FAILED outcome is honoured"
affects: [phase-04-tools, phase-05-e2e, verifier]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Halt-governance hook: catch BudgetExceeded at the SOLE-enforcer call site, write an audit row, re-raise UNCHANGED (pre-call spend-stop preserved)"
    - "Orchestrator-owned terminal transition + runner is_terminal guard so the state machine never double-transitions FAILED->COMPLETED"
    - "Marker rides existing contract fields (model_route='budget_halt') — GatewayEvent has no free-text note column (03-02 deviation)"

key-files:
  created:
    - tests/test_budget_halt_governed.py
  modified:
    - src/agent_mesh/worker/graph.py
    - src/agent_mesh/worker/orchestrator.py
    - src/agent_mesh/worker/runner.py

key-decisions:
  - "Carry the halt marker in model_route='budget_halt' + dlp_action='block' + provider_status=None (no note field exists); the orchestrator's transition_task note carries the free-text reason"
  - "task_id threaded through MeshState and every node's _delegate call so the audit row is task-scoped (the only new wiring the hook required)"
  - "Runner guard added (Rule 1) because run_mesh now sets FAILED itself — without it transition_task(FAILED, COMPLETED) raises IllegalTransition in production"
  - "resume_mesh halt-catch is belt-and-suspenders: resume re-enters at the write_gate interrupt so _delegate does not re-run, but the plan required covering both entry paths"

patterns-established:
  - "Governance is added AROUND an existing enforcement point, never replacing the enforcement math (budget.check / Router untouched)"

requirements-completed: [GW-03, OBS-01]

# Metrics
duration: 38min
completed: 2026-06-06
---

# Phase 3 Plan 04: Governed Budget Halt Summary

**A production budget breach in `graph._delegate` now writes exactly one tenant/task-scoped `budget_halt` gateway_event and the orchestrator turns the propagating `BudgetExceeded` into a governed FAILED terminal task state with `trace_id` set — closing 03-VERIFICATION Gap 1.**

## Performance

- **Duration:** ~38 min
- **Started:** 2026-06-06T06:25:00Z (approx)
- **Completed:** 2026-06-06T07:03:00Z (approx)
- **Tasks:** 3
- **Files modified:** 3 (+1 created)

## Accomplishments
- `record_gateway_event` now has >=1 production call site in `graph.py` (was 0) — the halt-observability contract is wired, not just asserted by a test.
- A budget halt yields a governed terminal FAILED task state instead of an untyped LangGraph node exception escaping `run_mesh`/`resume_mesh`.
- `OrchestrationResult` on the halt path sets `trace_id` like every other terminal path, preserving OBS-01 correlation.
- Pre-call spend-stop semantics are unchanged: the `budget.check` raise still happens before any `get_chat_model` construction (proven leak-free in the test).
- New `tests/test_budget_halt_governed.py` drives the REAL production halt (`_delegate` → `run_mesh` → `Worker.process`), not a manual `record_gateway_event` call.

## Task Commits

Each task was committed atomically (TDD: RED test added in this file, then GREEN src):

1. **Task 1: Audit-row on halt in `_delegate`** - `7156acc` (feat)
2. **Task 2: Governed terminal FAILED state in orchestrator** - `c4de1fd` (feat)
3. **Task 3: Production-path governed-halt test + full-suite green** - `36b9b7d` (test)

## Files Created/Modified
- `src/agent_mesh/worker/graph.py` - `_delegate` gains `task_id` kwarg + `except BudgetExceeded` that writes one `budget_halt` GatewayEvent before re-raising; `MeshState` carries `task_id`; every node forwards `state.get("task_id")` to `_delegate`.
- `src/agent_mesh/worker/orchestrator.py` - module-level `BudgetExceeded`/`get_repository`/`TaskState` imports; `_governed_budget_halt()` helper; `run_mesh` and the durable `resume_mesh` branch catch `BudgetExceeded` and return a typed FAILED result; graph initial state now passes `task_id`.
- `src/agent_mesh/worker/runner.py` - terminal-state guard after `run_mesh` and after `resume_mesh` so an orchestrator-set FAILED is honoured (no `FAILED->COMPLETED` IllegalTransition).
- `tests/test_budget_halt_governed.py` - production-path proof: forced over-budget ledger + singleton-pinned tenant; asserts one tenant/task-scoped `budget_halt` row, FAILED terminal state, no provider leak, `trace_id` set; negative control for the within-budget path.

## Decisions Made
- Halt marker rides `model_route="budget_halt"` (no `note` field on GatewayEvent — honours the 03-02 deviation); free-text reason lives on the task transition `note`.
- Used `settings.tenant_id`/`settings.client_slug` for the gateway_event scope (matches the budget owner) and threaded only `task_id` from state — the minimal new wiring.
- Test installs ONE `InMemoryRepository` as the process singleton and pins `TENANT_ID`/`CLIENT_SLUG` so the task tenant, breach-ledger row, budget owner, and gateway_event scope all match — preventing a fixture-vs-singleton split-brain that could pass green on a lie.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Runner double-transition guard**
- **Found during:** Task 2 (orchestrator governed terminal state)
- **Issue:** Once `run_mesh`/`resume_mesh` set the task to FAILED, `Worker.process` continued to `transition_task(task_id, COMPLETED)`. `assert_transition(FAILED, COMPLETED)` raises `IllegalTransition` (FAILED has no legal successors), so the orchestrator change would crash the worker in production even though a test calling `run_mesh` directly would pass.
- **Fix:** After `run_mesh` (and after `resume_mesh`), re-fetch the task and short-circuit (`return str(state)`) when `is_terminal(state)` is true. `is_terminal` was already imported in runner.py.
- **Files modified:** src/agent_mesh/worker/runner.py
- **Verification:** `test_worker_budget_halt_yields_failed_terminal_and_trace_id` drives the full `Worker.process` path and asserts FAILED terminal state with no crash; full suite green.
- **Committed in:** c4de1fd (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** The guard is required for correctness — the orchestrator change forces it. It touches none of the SEC-01/02 approval code, the CF chokepoint, or the Router/budget math. No scope creep.

## Issues Encountered
- `_delegate` lazy-imports `get_chat_model` from `model_gateway`, so the test could not monkeypatch `graph.get_chat_model` (not a module attribute). Resolved by patching `agent_mesh.worker.model_gateway.get_chat_model` at its source. The over-budget assertion needs no chat stub at all — `budget.check` raises before construction.
- `RECEIVED -> RUNNING` is not a legal transition; the worker assumes a QUEUED task. The test queues the task (`RECEIVED -> QUEUED`) before `Worker.process` so the worker's `QUEUED -> RUNNING` is legal.

## User Setup Required
None - no external service configuration required.

## Verification Gates
- Default suite: `134 passed, 6 skipped` (was 130 passed; +4 new tests, 0 failures), no cloud deps.
- `ruff check src/agent_mesh tests`: All checks passed.
- `make smoke` (venv interpreter): SMOKE OK.
- Grep gate: `record_gateway_event` has 1 production call site in `src/agent_mesh/worker/graph.py` (was 0).

## Next Phase Readiness
- 03-VERIFICATION Gap 1 (GW-03 / SC-1 / SC-2 budget-halt governance) is closed and provable on the default lane.
- Gap 2 (tool-execution OTel spans) remains a Phase 4 deferral as recorded in the verification report — out of scope here.

---
*Phase: 03-model-gateway-observability*
*Completed: 2026-06-06*

## Self-Check: PASSED

All 5 files exist on disk; all 4 commits (7156acc, c4de1fd, 36b9b7d, f3401f9) are in the branch history. STATE.md and ROADMAP.md untouched (orchestrator owns those writes).
