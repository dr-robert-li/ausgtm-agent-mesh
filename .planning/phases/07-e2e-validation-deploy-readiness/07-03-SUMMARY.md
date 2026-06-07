---
phase: 07-e2e-validation-deploy-readiness
plan: 03
subsystem: testing
tags: [e2e, litellm, fallback, budget-halt, langgraph, observability, pytest, live-marker]

# Dependency graph
requires:
  - phase: 03-model-gateway-observability
    provides: GW-03 litellm Router fallback cascade + governed/observable budget halt (graph._delegate auto-emits budget_halt gateway_event); BudgetTracker.check pre-call enforcement
  - phase: 07-01
    provides: tests/e2e/ package + the first E2E module (slack write-gated) establishing the e2e suite location
provides:
  - "E2E-03 default-lane combined-run proof: ONE creds-free test driving model fallback -> in-cascade retry-recovery -> governed budget halt -> FAILED terminal with exactly one observable budget_halt event and no provider leak"
  - "E2E-03 opt-in live variant: real Vertex->Anthropic fallback + real cents-cap ($0.02) budget halt through the production Worker.process path, live_creds-gated and spend-bounded to pennies"
  - "Resolution of open design decision 1 (the retry leg): in-cascade litellm recovery IS the mid-run retry; literal Pub/Sub job-redelivery deferred to DEP-01/07-04 as deploy-config consistency — no new fault-injection harness (honors D-05)"
affects: [07-04 deploy-readiness (DEP-01 Pub/Sub max-delivery-attempts assertion), phase-07 verification, ROADMAP SC-3]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Combined-run E2E: stage existing hardened seams into ONE test with staged asserts in forced order (recovery succeeds, then governed halt) rather than a new harness"
    - "Default/live lane split mirrored across both modules: default = mock_testing_fallbacks + over-cap ledger row (creds-free); live = real broken-Vertex inducer + cents-cap, whole-module pytest.mark.live + live_creds"
    - "Anti-split-brain singleton pinning replicated inline (repo_module._SINGLETON + TENANT_ID/CLIENT_SLUG) so task/ledger/budget-owner/event scope all match one tenant"

key-files:
  created:
    - tests/e2e/test_e2e_failure_modes.py
    - tests/e2e/test_e2e_failure_modes_live.py
  modified:
    - .planning/phases/07-e2e-validation-deploy-readiness/deferred-items.md

key-decisions:
  - "Retry-leg open decision resolved as option b: the litellm cascade IS the mid-run retry-then-recover (mock_testing_fallbacks forces the primary to raise, the configured fallback recovers); the literal Pub/Sub redelivery is asserted in DEP-01 (07-04), not via a new fault harness"
  - "Live variant drives the PRODUCTION Worker.process halt path and asserts the AUTO-EMITTED budget_halt event — deliberately NOT reproducing test_cascade_live.py's now-stale 'manually record the gateway_event' caveat (auto-emit was wired into graph.py since)"
  - "Combined Stage A + Stage B in ONE test (not split); when litellm absent the whole test SKIPS loudly per AC — the budget-halt seam is independently covered creds-free by test_budget_halt_governed.py, so the E2E test's job is the composition, which legitimately needs litellm"

patterns-established:
  - "Comment-immune AC greps: default-lane module must have ZERO `^pytestmark = pytest.mark.live` matches; live module must have exactly one (statement-anchored)"
  - "Live spend bound (D-08/T-07-07): few-cents cap routed at the cheapest tier + a _boom leak guard proves the real provider is never reached past the halt, so the halt leg costs zero model tokens"

requirements-completed: [E2E-03]

# Metrics
duration: 33min
completed: 2026-06-07
---

# Phase 07 Plan 03: E2E-03 Failure-Modes Validation Summary

**One combined creds-free run proving model fallback + in-cascade retry-recovery then a governed budget halt to FAILED with exactly one observable budget_halt event and no provider leak, plus an opt-in live variant firing a real fallback + real cents-cap halt for pennies.**

## Performance

- **Duration:** ~33 min
- **Started:** 2026-06-07T22:20:00Z (approx)
- **Completed:** 2026-06-07T22:53:45Z
- **Tasks:** 2
- **Files modified:** 3 (2 created, 1 appended)

## Accomplishments
- **E2E-03 default lane (ROADMAP SC-3):** `test_e2e_failure_modes.py` composes the Phase-3 seams into ONE combined run — Stage A builds the real litellm Router via `build_router()` and forces `mock_testing_fallbacks=True` so the primary (`low-complexity`/`gemini-1.5-flash`) raises and the configured fallback (`gemini-1.5-pro`) serves (the mid-run retry-recovery); Stage B pins a singleton repo + tenant, records an over-cap budget row, forces the real `_delegate` path, and drives `Worker.process` to a governed `FAILED` terminal with exactly one `budget_halt` gateway_event (`provider_status is None`) and a `_boom` leak guard proving no provider was reached. **Verified PASSING** end-to-end with the litellm extra installed.
- **E2E-03 live variant (D-06/D-08):** `test_e2e_failure_modes_live.py` is whole-module `pytest.mark.live` + `live_creds`-gated. Stage A wires a real broken-Vertex -> real-Anthropic fallback; Stage B sets a `$0.02` cap routed at the cheapest tier and drives the PRODUCTION `Worker.process` halt path to `FAILED` with the auto-emitted `budget_halt` event, leak-guarded so the halt fires before any spend. **Verified SKIPPING loudly** with no creds.
- **Open design decision 1 resolved** (the retry leg has no deterministic standalone analog): in-cascade litellm recovery is read as the mid-run retry (option b); the literal Pub/Sub job-redelivery (`--max-delivery-attempts=5` + `--dead-letter-topic`) is asserted as deploy-config consistency in DEP-01 (plan 07-04). No new fault-injection harness — honors D-05.

## Task Commits

1. **Task 1: E2E-03 default-lane combined run** — `3c90962` (test)
2. **Task 2: E2E-03 opt-in live variant** — `7b95d31` (feat)

_Note: Task 1 is a TDD task; because it captures the contract of already-shipped Phase-3 behaviour, the test was written and immediately verified green (no separate failing-RED commit was meaningful — the behaviour under test already exists and is committed)._

## Files Created/Modified
- `tests/e2e/test_e2e_failure_modes.py` — E2E-03 default-lane combined-run proof (fallback+retry-recovery -> governed budget_halt -> FAILED). Creds-free; skips loudly without the litellm extra.
- `tests/e2e/test_e2e_failure_modes_live.py` — E2E-03 opt-in live variant (real fallback + real cents-cap halt). `live`+`live_creds`-gated; cents-bounded.
- `.planning/phases/07-e2e-validation-deploy-readiness/deferred-items.md` — appended a pre-existing `cyclonedx` ModuleNotFoundError note (out of scope; see below).

## Decisions Made
- **Single combined test, not split:** per the plan AC, when the litellm extra is absent the whole test SKIPS loudly. The budget-halt seam is independently covered creds-free elsewhere, so this E2E test's distinct value is the *composition in order*, which legitimately requires litellm. (Advisor-confirmed.)
- **Live variant asserts production-emitted event, no stale caveat:** the older `test_cascade_live.py` manually records the halt gateway_event with a "production path doesn't auto-emit" caveat; that caveat is now stale (auto-emit was wired into `graph.py`, proven by `test_budget_halt_governed.py`). The live variant drives `Worker.process` and asserts the auto-emitted event instead.
- **Inline `governed_env` replication:** the analog's `governed_env` fixture is local to `test_budget_halt_governed.py` (not in conftest), so the singleton-pinning pattern is replicated inline in both new modules rather than imported.

## Deviations from Plan

None — plan executed exactly as written. No deviation rules (1–4) were triggered; both task actions and acceptance criteria were satisfiable as specified against the existing Phase-3 seams.

## Issues Encountered
- **Environment had no project dependencies installed.** The fresh worktree had no virtualenv, so `langgraph`/`litellm` were absent and the entire existing suite (including the analog `test_budget_halt_governed.py`) collected zero tests. Resolved by creating a throwaway `.venv-e2e` and installing `-e ".[dev,agents,runtime]"` (the `runtime` extra carries litellm) for validation only. The venv is gitignored (`.venv-e2e/`) and not committed; the threat-model "no new packages" constraint (T-07-SC) is about the *plan's* declared deps — no new entries were added to `pyproject.toml`.
- **11 pre-existing suite failures unrelated to this plan:** `ModuleNotFoundError: No module named 'cyclonedx'` in `tests/test_self_improvement.py` and `tests/test_version_pin.py` (from `src/agent_mesh/services/ai_bom.py:123`). The Phase-6 `cyclonedx-python-lib` dep is in no extra I installed and has zero relation to the E2E-03 files (no import overlap). Out of scope (GSD scope-boundary rule) — logged to `deferred-items.md`, not fixed. My two E2E files: 1 passed + 1 skipped (live), exactly as designed; `tests/e2e/ -m "not live"` is fully green (2 passed).

## User Setup Required
None — no external service configuration required. The live variant is opt-in and only runs when a developer exports real provider/gateway creds and passes `-m live`.

## Next Phase Readiness
- **E2E-03 (ROADMAP SC-3) is proven:** fallback, retry-recovery, and budget-limit halt are exercised together in one run, halting to a governed observable FAILED terminal. D-05, D-06, D-08 each observably satisfied.
- **Hand-off to 07-04 (DEP-01):** the literal Pub/Sub job-redelivery assertion (`--max-delivery-attempts=5` + `--dead-letter-topic` consistency in `gcp_bootstrap.sh`) is the other half of the three-part SC-3 criterion and belongs to plan 07-04 — flagged in both test modules' docstrings.
- **No blockers** introduced. The `cyclonedx` env gap (deferred-items.md) only affects the Phase-6 self-improvement tests, not E2E-03.

## Self-Check: PASSED

- FOUND: `tests/e2e/test_e2e_failure_modes.py`
- FOUND: `tests/e2e/test_e2e_failure_modes_live.py`
- FOUND commit `3c90962` (Task 1, test)
- FOUND commit `7b95d31` (Task 2, feat)
- Default lane VERIFIED: `tests/e2e/test_e2e_failure_modes.py -m "not live"` = 1 passed (with litellm) / skips loudly (without)
- Live lane VERIFIED: `tests/e2e/test_e2e_failure_modes_live.py -m live` = 1 skipped (no creds), never failed
- ruff clean on both modules; AC greps satisfied (default module has 0 `^pytestmark = pytest.mark.live`, live module has 1)

---
*Phase: 07-e2e-validation-deploy-readiness*
*Completed: 2026-06-07*
