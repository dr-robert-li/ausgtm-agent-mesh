---
phase: 06-self-improvement
plan: 04
subsystem: testing
tags: [llm-judge, position-bias, calibration, binomial, type-i, langfuse, live-lane, self-improvement]

# Dependency graph
requires:
  - phase: 06-02
    provides: "eval_harness.run_candidate(..., run_evaluators=[...]) run-level evaluator slot + held-out scoring"
  - phase: 03 (observability)
    provides: "observability.py lazy-optional-dep import-and-degrade pattern; conftest live_creds fixture + live marker"
provides:
  - "Opt-in live-lane LLM-judge dimension (SI-01d): order-swap position-bias control, human-calibrated TPR/FPR, finite-sample Type-I gate, close-margin non-sole-arbiter guard"
  - "Gateway-routed pairwise judge (GW-02 chokepoint) and a langfuse run-level evaluator plug-in for the 06-02 harness"
affects: [self-improvement promotion gate, 06-verification]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Exact one-sided binomial tail via stdlib math.comb (no scipy/numpy) — finite-sample Type-I gate that keeps module load dep-light"
    - "Order-swap pairwise verdict: a candidate win counts ONLY when both orderings agree (position-bias neutralisation)"
    - "Config-driven numerics via frozen JudgeConfig dataclass + module constants (mirrors eval_harness DEFAULT_ITEM_THRESHOLD precedent) — no bare literals at decision sites"
    - "Lazy-optional-dep guard (langfuse.experiment.Evaluation, model-gateway get_chat_model imported inside functions) so default-lane import stays creds-free"

key-files:
  created:
    - src/agent_mesh/eval/__init__.py
    - src/agent_mesh/eval/judges.py
    - tests/test_judges_live.py
  modified: []

key-decisions:
  - "Finite-sample Type-I gate = EXACT one-sided binomial tail (stdlib math.comb), not a normal/z approximation — correct at small n and pulls no scipy/numpy (keeps default-lane import dep-light)"
  - "Numerics (alpha, null win-rate, close-margin, min-TPR/max-FPR, min calibration n) are config-driven via frozen JudgeConfig defaults — POC discretion per 06-PATTERNS No-Analog"
  - "Live tests drive the deterministic judge guards with an injected compare (no real model/network/tokens) while staying entirely in the credential-gated live lane — the live gate is the lane contract, not a per-call network requirement"

patterns-established:
  - "Pattern: position-bias control via cross-order agreement (PairwiseVerdict.candidate_wins) + is_position_bias_flip diagnostic"
  - "Pattern: judge is NEVER the sole arbiter at close margins (JudgeDecision.sole_arbiter False when within close_margin) — caller defers to the deterministic harness gate"

requirements-completed: [SI-01d]

# Metrics
duration: 18min
completed: 2026-06-07
---

# Phase 06 Plan 04: Live-lane LLM-judge (SI-01d) Summary

**Opt-in `live`-lane LLM-judge with order-swap position-bias control, human-calibrated TPR/FPR, an exact finite-sample binomial Type-I gate, and a close-margin non-sole-arbiter guard — entirely behind `live_creds`, so the default `make test` lane imports none of it.**

## Performance

- **Duration:** ~18 min
- **Tasks:** 2
- **Files created:** 3

## Accomplishments
- `eval/judges.py` — the only Phase-6 surface that touches real models/creds: order-swap (win only when both orderings agree), `calibrate()` TPR/FPR against a human-labelled set with a trusted-judge gate, `passes_type_i()` exact one-sided binomial tail (config-driven `alpha`/null rate), and a close-margin guard so the judge defers to the deterministic gate where it is least reliable.
- Gateway-routed pairwise judge (`gateway_pairwise_judge` -> `worker.model_gateway.get_chat_model`, GW-02 chokepoint; judge never calls a provider SDK directly — threat T-06-13) and a langfuse run-level evaluator (`make_run_evaluator`) that plugs into the 06-02 `run_candidate(..., run_evaluators=[...])` slot only when creds exist.
- `tests/test_judges_live.py` — module-level `pytestmark = pytest.mark.live`, consuming `live_creds`; proves order-swap symmetry, TPR/FPR bounds, the alpha-driven Type-I rejection, and the close-margin defer. Collects ZERO running tests in the default lane; all 5 in the live lane.

## Task Commits

1. **Task 1: eval/judges.py — order-swap + calibration + Type-I gate (live-lane)** - `c35377d` (feat)
2. **Task 2: live-marked judge tests (order-swap, calibration, Type-I)** - `ebb151f` (test)

## Files Created/Modified
- `src/agent_mesh/eval/__init__.py` - eval package marker; documents the default-lane-creds-free contract
- `src/agent_mesh/eval/judges.py` - live-lane LLM-judge: order-swap, calibration, finite-sample Type-I gate, close-margin guard, gateway-routed pairwise judge, run_evaluator plug-in
- `tests/test_judges_live.py` - live-marked judge tests (5 tests; consume live_creds; skip cleanly in default lane)

## Decisions Made
- **Exact binomial over approximation:** "finite-sample Type-I" is implemented as an exact one-sided binomial upper tail (`binomial_upper_tail` via `math.comb`). A normal/z approximation is invalid at the small samples a judge calibration set provides; the exact tail is correct AND pulls no scipy/numpy, so the default-lane import probe stays dep-light.
- **Config-driven numerics:** alpha (0.05), null win-rate (0.5), close-margin (0.05), min-TPR (0.70), max-FPR (0.30), min calibration n (20) live as module constants + `JudgeConfig` frozen-dataclass defaults. Threading every value through `Settings` was unnecessary — the codebase precedent (`eval_harness.DEFAULT_ITEM_THRESHOLD`) treats named module constants/dataclass defaults as "config-driven", and 06-PATTERNS marks the numerics Claude's-discretion.
- **Deterministic live tests:** the judge guards are pure-Python and deterministic, so the live tests inject a deterministic `compare`/baseline rather than calling a real model — proving the guard behaviour without spending tokens, while still living entirely in the credential-gated `live` lane.

## Deviations from Plan
None - plan executed exactly as written. (The plan frontmatter listed `files_modified` paths `eval/__init__.py`, `eval/judges.py`, `test_judges_live.py`; all three were created as specified.)

## Issues Encountered
- Initial ruff failures (unused `field` import, `typing.Callable` deprecated, `zip` without `strict=`) — fixed inline before the Task 1 commit. No behavioural change.

## User Setup Required
None - no external service configuration required. The judge is OFF by default; running it live requires provider/gateway creds (`ANTHROPIC_API_KEY` / `VERTEX_PROJECT_ID` / `CF_AIG_WRAPPER_URL`) and `make test-live`.

## Next Phase Readiness
- SI-01d delivered: the live judge is a calibrated, position-bias-controlled SECONDARY signal that can never wave a close-margin regression through alone. The deterministic 06-02 no-regression gate remains the primary promotion-eligibility check.
- Default `make test` lane verified green (267 passed, 6 skipped, 21 deselected) and imports no judge code at runtime.
- No blockers.

### Verification evidence
- `python -c "import agent_mesh.eval.judges"` exits 0 with no creds and no scipy/numpy (`grep -c alpha` = 5).
- `pytest -m "not live" tests/test_judges_live.py` -> 5 deselected (zero running).
- `pytest --collect-only -m live tests/test_judges_live.py` -> lists order-swap, calibration, Type-I, close-margin, run_evaluator (5 collected).
- `pytest -m live tests/test_judges_live.py` (dummy cred) -> 5 passed.
- ruff clean on `src/agent_mesh/eval/` and `tests/test_judges_live.py`.

## Self-Check: PASSED
- FOUND: src/agent_mesh/eval/__init__.py
- FOUND: src/agent_mesh/eval/judges.py
- FOUND: tests/test_judges_live.py
- FOUND commit: c35377d (Task 1)
- FOUND commit: ebb151f (Task 2)

---
*Phase: 06-self-improvement*
*Completed: 2026-06-07*
