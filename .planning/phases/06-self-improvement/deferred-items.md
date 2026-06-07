# Phase 6 — Deferred / Out-of-Scope Items

Logged during execution. Not fixed (out of the current task's scope).

## Pre-existing lint errors (not introduced by Phase 6)

- `tests/test_calcom_adapter.py:153` — E501 line too long (>100). Pre-exists since
  Phase 05-04 (commit b1c7c03). Out of scope for 06-01.
- `tests/test_calcom_adapter.py:206` — E501 line too long (>100). Pre-exists since
  Phase 05-04 (commit b1c7c03). Out of scope for 06-01.

## WR-09 — `get_task` missing tenant_id filter (DUR-02 defense-in-depth)

- Surfaced by Phase 6 code review (06-REVIEW.md, WR-09). `RepositorySQL.get_task`
  has no `tenant_id` filter. This is a **pre-existing DUR-02 gap accepted in the
  Phase 1 security audit (0 blockers)**, NOT introduced by Phase 6. Verified that
  `promote_proposal` does not traverse `get_task`/`transition_task` (it uses
  `get_proposal`/`list_evaluations`/`get_approval`), so it is not a Phase-6
  regression. Correct remediation is a dedicated DUR-02 hardening task that changes
  the `get_task` signature + all Phase 1–5 callers — out of scope for Phase 6.
