# Deferred Items — Phase 01

Out-of-scope discoveries logged during execution. NOT fixed by the owning plan.

## 01-01

- **Pre-existing env gap: `fastapi` not installed in this worktree's interpreters.**
  `tests/test_importability.py::test_module_imports[agent_mesh.api.app]` fails with
  `ModuleNotFoundError: No module named 'fastapi'`. `fastapi` is a base dependency in
  `pyproject.toml` but was never `pip install`-ed in this environment (no venv; no
  interpreter on PATH has it). The failure is independent of 01-01 (app.py and the
  importability test were not modified). Resolution: run `make install` (or
  `pip install -e .`) before `make test`. The full suite passes 60/60 once this single
  env-gated test is deselected.

## 01-02 (Pub/Sub dispatch, DUR-03)

- **`tests/test_importability.py::test_module_imports[agent_mesh.api.app]` fails in this
  worktree's minimal environment** because `fastapi` is not installed
  (`importlib.util.find_spec('fastapi') is None`). `src/agent_mesh/api/app.py` imports
  `fastapi` at module top level, so the importability matrix (which asserts the package
  imports under minimal deps) fails for that one module. This is pre-existing, unrelated
  to the Pub/Sub dispatch work, and reproduces independently of the 01-02 changes
  (the 01-02 test file and helper import cleanly with the suite green when this single
  pre-existing failure is deselected: `59 passed, 1 skipped, 3 deselected`).
  Resolution belongs to the API/ingress plan or to the test environment setup
  (install the `api` extra), not to 01-02. Same root cause as the 01-01 note above.

## Code-review findings (01-REVIEW.md) — orchestrator triage after Wave 2

Phase-01 code review surfaced 2 Critical / 4 Warning / 1 Info. Triage:

- **CR-01 (approval token leaked via unauthenticated task reads) — FIXED, not deferred.**
  Closed by `fix(01): redact approval tokens from task-read endpoints`. Centralized
  `api.serialization.public_task_dict` strips the token from both `GET /v1/tasks/{id}`
  and MCP `get_task`; HTTP + unit regression tests added. Listed here only for the
  audit trail.

- **WR-01 (single-entity `get_*` reads in `RepositorySQL` are not tenant-scoped) — ACCEPTED for Phase 1, deferred.**
  REQUIREMENTS.md DUR-02 reads "**All** repository read paths are tenant-scoped (e.g.
  `list_events`, `list_evaluations`…)". Plan 01-01 deliberately **narrowed "All" → the
  `list_*` paths** (PLAN lines 65-67, 101, 126, 150, 181, 192; cross-tenant must-have
  names "events or evaluations"). The `get_*` methods take a globally-unique PK and the
  protocol signatures do not accept `tenant_id`. The phase's stated DUR-02 behavior
  (cross-tenant `list_*` returns `[]`) is met and validated. Tenant-scoping `get_*` is a
  legitimate **defense-in-depth** hardening (a caller holding another tenant's record id
  could read it), but it requires a protocol-wide signature change and is **out of scope
  for Phase 1**. Tracked for a later hardening pass (candidate: Phase 2 or a security
  sweep). This note records the REQUIREMENTS-"All" vs plan-"list_*" narrowing explicitly
  so it is a documented decision, not a silent gap.

- **CR-02 (`_resume_after_approval` unconditionally transitions to COMPLETED) — DEFERRED, latent.**
  The current orchestrator stub emits at most one proposed write, so a partial-approval
  orphan cannot occur yet. The risk becomes real once the Phase 2 LangGraph orchestrator
  can emit >1 gated write in a run. Fix belongs with that work (only transition to
  COMPLETED when no tool calls remain in `AWAITING_APPROVAL`).

- **WR-02 / WR-03 / WR-04 / IN-01 — quality, non-blocking.** Token-replay-within-TTL
  (no nonce/consumed check), invalid `decision` → 500 instead of 400, post-commit re-read
  outside the transaction, and the misleadingly-named `_pending_calls`. Worth a follow-up
  hardening pass; none block the Phase 1 goal.
