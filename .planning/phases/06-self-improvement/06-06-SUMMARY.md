---
phase: 06-self-improvement
plan: 06
subsystem: self-improvement
tags: [SI-02b, non-hot, versioned-promotion, rollback, ml-bom, criterion-5]
requires:
  - "06-01: repository.current_active_version / set_active_version (active-version pointer)"
  - "06-02: self_improvement.evaluate_proposal held-out harness (reconciled, not clobbered)"
  - "06-05: ai_bom.generate_ml_bom(...) -> snapshot_id"
provides:
  - "version_pin.active_version() / load_active_version_at_boot() — boot-time set-once non-hot active-version read path"
  - "promote_proposal: always fills PromotionRecord.ai_bom_snapshot_id + writes non-hot active pointer"
  - "rollback_promotion: re-points active pointer to previous_version (D-13)"
affects:
  - "src/agent_mesh/services/self_improvement.py (shared with 06-02; reconciled)"
tech-stack:
  added: []
  patterns:
    - "set-once module cache mirroring observability._PROCESS_PROVIDER (non-hot read path)"
    - "repo-root-anchored absolute manifest paths for worker-CWD safety (06-05 handoff)"
key-files:
  created:
    - src/agent_mesh/services/version_pin.py
    - tests/test_version_pin.py
  modified:
    - src/agent_mesh/services/self_improvement.py
decisions:
  - "active_version() reads ONLY the module cache; load_active_version_at_boot() unconditionally re-reads the store (no `if None` guard) so an explicit reload picks up the latest pointer"
  - "promote always generates a real ML-BOM snapshot id (kwarg becomes an override, not the sole source) so ai_bom_snapshot_id is never null"
  - "rollback guards a null previous_version (set_active_version requires str): the first-ever promote cannot be re-pointed"
metrics:
  duration: "~25 min"
  completed: "2026-06-07"
  tasks: 2
  files: 3
---

# Phase 06 Plan 06: Non-Hot Versioned Promotion + Rollback Re-point (SI-02b) Summary

Wired the controlled, versioned, NON-HOT promotion chokepoint (criterion 5): a boot-time
set-once active-version loader (`version_pin.py`), a `promote_proposal` that generates the
06-05 ML-BOM and writes the active pointer without hot-swapping running config, and a
`rollback_promotion` that re-points the active pointer to `previous_version` — all proven by
default-lane tests.

## What Was Built

### Task 1 — `version_pin.py`: boot-time set-once active-version loader (non-hot)
- `_ACTIVE_VERSION: str | None` module cache mirroring the `observability._PROCESS_PROVIDER`
  set-once *shape* (module global + accessor reads cache, not source).
- `active_version() -> str | None` — the hot path. Returns ONLY the cache; never reads the
  repo. This is what makes promotion non-hot: running code only ever calls `active_version()`.
- `load_active_version_at_boot(repo, tenant_id) -> str | None` — the explicit boot/reload step.
  **Unconditionally** re-reads `repo.current_active_version(tenant_id)` (deliberately no
  `if None` guard, so a reload reflects the latest pointer) and overwrites the cache.
- `_reset()` test-only hook to simulate a fresh boot.
- No `get_settings`/call-time read for the active version (D-12 / CLAUDE.md no-runtime-mutation).
- Commit `4f885f5`.

### Task 2 — promote/rollback wiring in `self_improvement.py`
- `promote_proposal`: after the existing approval+evaluation+payload-hash chokepoint (kept
  VERBATIM), generates the 06-05 CycloneDX ML-BOM via `ai_bom.generate_ml_bom(...)`, always
  filling `PromotionRecord.ai_bom_snapshot_id` (the kwarg is now an override, not the only
  source). Then writes the active pointer via `repo.set_active_version(...)` — NON-HOT (store
  only; no loader call), so a currently-loaded `active_version()` is unchanged until reload.
- `rollback_promotion`: keeps the `rolled_back`/`rollback_reason`/ROLLED_BACK flip and ADDS the
  active-pointer re-point to `previous_version` (D-13), guarded against a null previous_version.
- Manifest paths handed to `generate_ml_bom` are REPO-ROOT-ANCHORED ABSOLUTE
  (`Path(__file__).resolve().parents[3] / "manifests" / ...`), avoiding the latent
  FileNotFoundError the 06-05 handoff warned about (promote runs in a worker where CWD != repo root).
- `dataset_version` / `model_route_profile` sourced from `proposal.metadata` with config-driven
  fallback defaults (D-15) so `ai_bom_snapshot_id` can never remain null.
- Commit `ce79595`.

## Wave Reconciliation
- `self_improvement.py` was shared with 06-02 (held-out harness in `evaluate_proposal`). The
  new evaluate behavior was re-read fresh and left intact — only `promote_proposal` and
  `rollback_promotion` were extended; the 06-02 evaluation logic is untouched.

## Tests
- `tests/test_version_pin.py` (autouse `_reset` fixture for module-cache isolation):
  - `test_active_version_none_before_boot` — cache empty before any load.
  - `test_active_version_set_once_at_boot` — a store write does NOT change `active_version()`
    until an explicit reload (non-hot, criterion 5).
  - `test_promotion_is_non_hot` — promote writes v2 + a non-null ML-BOM id, but a loaded
    `active_version()` stays v1 until reload.
  - `test_rollback_repoints_to_previous_version` — after rollback + reload, `active_version()`
    == previous_version (D-13).
- Existing `tests/test_self_improvement.py` (refusal, hash-rebind, original rollback) all green.
- Full default lane: `271 passed, 6 skipped, 16 deselected (live)` — creds-free.

## Threat Mitigations Applied
- T-06-16 (EoP, hot-swap coercion): set-once boot cache; no call-time read; `test_promotion_is_non_hot`.
- T-06-17 (Tampering, mutated patch): payload-hash rebind chokepoint kept verbatim; existing test green.
- T-06-18 (Repudiation, fake rollback): `rollback_promotion` re-points the active pointer (D-13).
- T-06-19 (Info disclosure, cross-tenant): `set_active_version`/`current_active_version` tenant-scoped (06-01).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Guard rollback against a null previous_version**
- **Found during:** Task 2.
- **Issue:** `repo.set_active_version(tenant, version, ...)` requires `version: str`, but
  `PromotionRecord.previous_version` is `str | None`; a first-ever promote (no previous) would
  pass `None` into a `str` parameter.
- **Fix:** Re-point only `if promotion.previous_version is not None`; the first-ever promote
  leaves the pointer untouched on rollback.
- **Files modified:** `src/agent_mesh/services/self_improvement.py`
- **Commit:** `ce79595`

**2. [Rule 3 - Blocking] Docstring reworded to satisfy the `get_settings`-absent grep**
- **Found during:** Task 1 verification.
- **Issue:** The acceptance grep `grep -v '^#' | grep -c get_settings == 0` flagged a docstring
  sentence mentioning `get_settings()` (docstrings are not `#` comments).
- **Fix:** Reworded the docstring to "the settings accessor" — no behavior change; grep now 0.
- **Files modified:** `src/agent_mesh/services/version_pin.py`
- **Commit:** `4f885f5`

## Self-Check: PASSED
- `src/agent_mesh/services/version_pin.py` — FOUND
- `tests/test_version_pin.py` — FOUND
- `src/agent_mesh/services/self_improvement.py` — FOUND (modified)
- Commit `4f885f5` — recorded
- Commit `ce79595` — recorded
