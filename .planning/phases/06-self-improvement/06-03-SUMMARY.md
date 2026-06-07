---
phase: 06-self-improvement
plan: 03
subsystem: self-improvement
tags: [gepa, reflective-proposer, held-out-isolation, reward-hacking, option-c, langgraph, deep-agents]

# Dependency graph
requires:
  - phase: 06-01
    provides: conftest stub_reflector + frozen_holdout_items fixtures (creds-free reflective-proposer doubles)
  - phase: 06-02
    provides: eval_harness held_out_item_ids() / held_out_pool() / evaluate_proposal held-out no-regression gate
provides:
  - "reflective_proposer.propose_from_traces: offline GEPA-style trace miner emitting inert DRAFT proposals via reflect_on_task"
  - "reflective_proposer.improve_loop: bounded, config-capped re-validated improvement loop with an injectable held-out gate"
  - "reflective_proposer.train_item_ids / assert_holdout_isolation / HeldOutLeakError: SI-01a held-out isolation invariant + zero-overlap guard"
affects: [06-04 ml-bom-on-promotion, 06-05 non-hot loader, self-evolving-surfaces-milestone]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Separated offline meta-agent: emits ONLY through the existing inert reflect_on_task seam; never imports the promotion/approval path; not wired into the LangGraph supervisor"
    - "Injectable reflect_fn (keyword reflect(evidence=...)) and injectable gate_fn so default lane stays creds-free and the loop-cap test is honest"
    - "Config-driven loop bound via module constant (env-overridable DEFAULT_MAX_ITERATIONS), no bare literal at the call site"
    - "Distinct train/dev id namespace (train-00x) vs held-out (holdout-00x) so zero-overlap disjointness is substantive"

key-files:
  created:
    - src/agent_mesh/services/reflective_proposer.py
    - tests/test_reflective_proposer.py
  modified: []

key-decisions:
  - "Iteration cap is a module constant DEFAULT_MAX_ITERATIONS = int(os.getenv('SI_IMPROVE_MAX_ITERATIONS','3')) inside reflective_proposer.py — keeps the change surface to the two declared files (plan permits a module default constant), conservative default 3 per RESEARCH Q1/D-15"
  - "improve_loop takes an injectable gate_fn (default = the 06-02 held-out evaluate path) so test_loop_caps_iterations can inject an always-fail gate; the default real gate always passes by construction (replay==baseline) and would otherwise exit at iteration 1, making the cap test trivially true"
  - "Forbidden tokens (promotion/approval symbols, held-out pool symbol) kept out of code AND prose so the strict acceptance grep returns 0; reference self_improvement at module level, never `from ... import` a sensitive symbol"
  - "Proposal type defaults to PROMPT_PATCH (a sensitive type) so reflect_on_task floors it to HIGH risk — correct for an autonomously-mined prompt-improvement proposal that can never auto-promote"

patterns-established:
  - "Held-out isolation as a testable invariant owned by the proposer plan: train_item_ids() ∩ held_out_item_ids() == ∅, with assert_holdout_isolation raising HeldOutLeakError on intersection"
  - "Bounded reflective loop: re-validate each round only THROUGH the gate; never feed held-out items back into the reflection signal"

requirements-completed: [SI-03, SI-01a]

# Metrics
duration: ~20min
completed: 2026-06-07
---

# Phase 06 Plan 03: Reflective Proposer (GEPA-style offline inert proposer + bounded loop) Summary

**Offline GEPA-style proposer that mines tenant-scoped durable `tool_calls` traces and emits inert DRAFT self-improvement proposals through the existing `reflect_on_task` seam, with a config-capped re-validated loop and a proven zero-overlap held-out isolation invariant (SI-01a).**

## Performance

- **Duration:** ~20 min
- **Tasks:** 2 (both TDD)
- **Files modified:** 2 (1 created source, 1 created test)

## Accomplishments
- `propose_from_traces(repo, task, reflect_fn)` mines `repo.list_tool_calls(task_id, tenant_id)` (tenant-scoped, DUR-02), reflects via an injected keyword `reflect_fn(evidence=...)`, and emits a DRAFT proposal through `self_improvement.reflect_on_task` — inertness inherited, no promotion path touched (T-06-08).
- `improve_loop(...)` runs at most `DEFAULT_MAX_ITERATIONS` rounds (config-driven module constant, env-overridable), re-validating each round through an injectable held-out gate; stops early on pass, halts at the cap otherwise (T-06-10).
- `train_item_ids()` + `assert_holdout_isolation()` + `HeldOutLeakError` enforce the SI-01a anti-reward-hack invariant; `test_holdout_isolation` proves `train_item_ids() ∩ eval_harness.held_out_item_ids() == ∅`.
- Confirmed the module is NOT imported by `worker/orchestrator.py` (or anywhere outside itself) — bounded-roster guardrail (D-07) preserved.

## Task Commits

Each task was committed atomically (TDD: shared RED commit, then GREEN):

1. **Task 1 + 2 RED: failing tests** - `1847b91` (test) — inertness, tenant-scope, held-out isolation, loop cap
2. **Task 1 + 2 GREEN: proposer + bounded loop** - `943b704` (feat) — `reflective_proposer.py`

_Note: both TDD tasks share a single source file; the RED tests for both were authored together, the GREEN implementation lands both surfaces in one module commit._

## Files Created/Modified
- `src/agent_mesh/services/reflective_proposer.py` - Offline reflective proposer: `propose_from_traces`, `improve_loop`, `train_item_ids`, `assert_holdout_isolation`, `HeldOutLeakError`, `DEFAULT_MAX_ITERATIONS`, `ImproveLoopResult`.
- `tests/test_reflective_proposer.py` - Default-lane (creds-free) tests: `test_proposer_emits_inert_draft`, `test_trace_mining_is_tenant_scoped`, `test_holdout_isolation`, `test_loop_caps_iterations`.

## Decisions Made
- Iteration cap implemented as an in-file module constant (env-overridable) rather than a `Settings` field, keeping the change surface to the two declared files while remaining config-driven (plan explicitly permits a module default constant).
- `improve_loop` exposes an injectable `gate_fn` (default = the 06-02 held-out evaluate path). This was necessary because the default real gate passes by construction (`replay_task` returns `expected_output`, so candidate == baseline), which would exit the loop at iteration 1 and make the loop-cap test trivially true. Injecting an always-fail gate makes the RED test fail for the right reason and proves boundedness honestly.
- `reflect_fn` is called by keyword (`reflect_fn(evidence=...)`) to match the existing `stub_reflector.reflect(*, evidence=None, **kwargs)` keyword-only contract — so no conftest fixture changes were needed and all existing default-lane tests stay green.
- Distinct `train-00x` vs `holdout-00x` id namespaces so the zero-overlap proof is substantive, not an accident of namespacing.

## Deviations from Plan

None - plan executed exactly as written. The conftest `stub_reflector` signature matched the real proposer interface (keyword `evidence`), so the wave-handoff "align the conftest fixture if the real signature diverges" path did not trigger; no conftest edit was made and all existing default-lane tests remain green.

## Issues Encountered
- The plan's `read_first` PATTERNS pseudocode showed `reflect_fn(evidence)` positionally, which would `TypeError` against the keyword-only stub. Resolved by calling `reflect_fn(evidence=evidence)` (caught before writing the implementation).
- Forbidden acceptance-grep tokens initially appeared in docstring prose (the criterion's grep strips only full-line `#` comments, not docstrings). Reworded the docstrings so `promote_proposal`, `open_promotion_approval`, and `held_out_pool` appear 0 times anywhere in the file, satisfying the strict grep.

## User Setup Required
None - no external service configuration required. `SI_IMPROVE_MAX_ITERATIONS` is an optional env override for the loop cap (defaults to 3).

## Next Phase Readiness
- 06-04 (ML-BOM-on-promotion) and 06-05 (non-hot loader) can build on the inert proposal seam unchanged; the proposer never promotes, so the promotion/AI-BOM wiring remains entirely downstream and human-gated.
- The held-out isolation invariant (`train_item_ids` vs `held_out_item_ids`) is now test-enforced; any future plan adding optimization signal must keep these disjoint.

## Verification
- Default-lane suite green and creds-free: `271 passed, 6 skipped, 16 deselected` (the lone `Failed to export span batch code: 401` is a harmless background OTLP export attempt to Langfuse cloud, unrelated to this plan).
- Plan Task 1 + Task 2 verify commands: all 4 targeted tests pass.
- Strict acceptance greps: forbidden promotion/approval/held-out-pool tokens = 0; `list_tool_calls(task_id, tenant_id)` tenant-scoped; loop bound references the config-driven constant (no bare literal); module not imported by the orchestrator.

## Self-Check: PASSED
- FOUND: src/agent_mesh/services/reflective_proposer.py
- FOUND: tests/test_reflective_proposer.py
- FOUND commit: 1847b91 (test RED)
- FOUND commit: 943b704 (feat GREEN)

---
*Phase: 06-self-improvement*
*Completed: 2026-06-07*
