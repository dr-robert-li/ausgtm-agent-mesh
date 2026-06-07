# Phase 07 — Deferred Items

Out-of-scope discoveries logged during execution (not fixed; see GSD scope-boundary rule).

## From plan 07-04 (deploy-readiness)

- **Pre-existing ruff E501 line-length errors in `tests/test_calcom_adapter.py`** (lines 153, 206 — 107 > 100).
  - Introduced in plan 05-04 (`b1c7c03`), unrelated to 07-04's `tests/deploy/` work.
  - `ruff check src tests` reports 2 errors here; `ruff check tests/deploy/` is clean.
  - Out of scope for 07-04 (only `tests/deploy/*` was created). Left untouched.
  - Fix: wrap the two long lines (or `# noqa: E501`) when the calcom test is next edited.

## From plan 07-03 (E2E-03)

- **Pre-existing suite failures: `ModuleNotFoundError: No module named 'cyclonedx'`** (11 failures in
  `tests/test_self_improvement.py` and `tests/test_version_pin.py`, raised from `src/agent_mesh/services/ai_bom.py:123`).
  - These tests require the Phase-6 self-improvement dependency `cyclonedx-python-lib`, which is in
    neither the `runtime` nor `agents` extra. The 07-03 plan installs NO new packages (threat-model
    T-07-SC: "No new packages installed (reuses existing extras)"), so this dependency is absent in the
    validation venv used for 07-03.
  - Entirely unrelated to 07-03's `tests/e2e/test_e2e_failure_modes*.py` files (no import overlap).
    On `main` (STATE.md: "135 passed") these pass because the full env including `cyclonedx-python-lib`
    is installed. Out of scope for 07-03 — left untouched.
  - Fix: ensure `cyclonedx-python-lib` (06-01 decision: `cyclonedx-python-lib 11.8.0`) is installed in
    the env running the full suite; or add it to a declared extra if it should be part of the worker image.
