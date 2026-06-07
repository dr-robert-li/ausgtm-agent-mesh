# Phase 07 — Deferred Items

Out-of-scope discoveries logged during execution (not fixed; see GSD scope-boundary rule).

## From plan 07-04 (deploy-readiness)

- **Pre-existing ruff E501 line-length errors in `tests/test_calcom_adapter.py`** (lines 153, 206 — 107 > 100).
  - Introduced in plan 05-04 (`b1c7c03`), unrelated to 07-04's `tests/deploy/` work.
  - `ruff check src tests` reports 2 errors here; `ruff check tests/deploy/` is clean.
  - Out of scope for 07-04 (only `tests/deploy/*` was created). Left untouched.
  - Fix: wrap the two long lines (or `# noqa: E501`) when the calcom test is next edited.
