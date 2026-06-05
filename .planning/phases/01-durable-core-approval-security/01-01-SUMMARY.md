---
phase: 01-durable-core-approval-security
plan: 01
subsystem: persistence / durable core
tags: [DUR-01, DUR-02, repository, postgres, psycopg3, tenant-isolation]
requires: []
provides:
  - "RepositorySQL (durable Postgres-backed Repository over 0001/0002 schema)"
  - "Widened Repository protocol: tenant_id on list_events/list_evaluations + list_tool_calls/list_approvals"
  - "get_repository() DATABASE_URL routing (RepositorySQL when set, InMemoryRepository when unset)"
  - "SQL-backed test fixtures (pg_dsn/sql_repo) gated on TEST_DATABASE_URL"
affects:
  - "01-03 (SEC-01/02) builds the approval-token hardening on this durable repo"
tech-stack:
  added: ["psycopg-pool>=3.2 (runtime optional-dep)"]
  patterns: ["sync psycopg3 ConnectionPool", "single with-conn transaction for multi-write", "%s-parameterized SQL only", "application-layer tenant scoping"]
key-files:
  created:
    - tests/test_repository_sql.py
  modified:
    - src/agent_mesh/services/repository.py
    - src/agent_mesh/worker/runner.py
    - src/agent_mesh/services/self_improvement.py
    - tests/conftest.py
    - tests/test_approval_gating.py
    - tests/smoke.py
    - pyproject.toml
decisions:
  - "metadata persisted to task_metadata under a single '__all__' key (Pitfall 5: tasks has no metadata column) — round-trips, never silently dropped"
  - "sessions row upserted inside RepositorySQL.create_task (no protocol change; TaskRecord carries all sessions columns)"
  - "migrations applied EXTERNALLY (test fixture / psql); RepositorySQL never self-applies"
  - "_enum_value() helper coerces enum-or-str to .value for every enum write (str(enum) on a str-mixin yields 'TaskState.RECEIVED')"
metrics:
  duration: ~50m
  completed: 2026-06-05
  tasks: 3
  files: 8
---

# Phase 1 Plan 01: Durable RepositorySQL + Tenant Scoping Summary

Replaced the in-memory singleton with a durable Postgres-backed `RepositorySQL` (sync psycopg3 `ConnectionPool`) over the existing `0001`/`0002` schema, after widening the `Repository` protocol and migrating every private-dict reach-in so the resume-after-approval loop cannot silently drop an approved write — validated end-to-end against a live `pgvector/pgvector:pg16` Postgres.

## What Was Built

- **Task 1 (linchpin, `a164825`)** — Widened the `Repository` protocol: added `tenant_id` to `list_events`/`list_evaluations` (DUR-02) and added `list_tool_calls`/`list_approvals`. Implemented all four on `InMemoryRepository`. Migrated `runner._pending_calls` off `getattr(self._repo, "_tool_calls", {})` to `repo.list_tool_calls(task_id, tenant_id)`; migrated `self_improvement.list_evaluations` caller to pass `proposal.tenant_id`; migrated the `repo._approvals` reach-ins in `test_approval_gating.py` and `smoke.py` to `repo.list_approvals(...)`. Grep gate confirms no caller touches private dicts outside `repository.py`.
- **Task 2 (`8eef9b8`)** — Implemented `RepositorySQL` (all 22 methods) with one sync `ConnectionPool`, `%s` parameters only, JSONB via `Jsonb`, atomic `transition_task` (UPDATE tasks + INSERT task_events in one `with conn:` block — Pitfall 7), `create_task` upserting task + `task_metadata` (Pitfall 5) + `sessions` (DUR-01). Routed `get_repository()` on `settings.database_url`. Added `psycopg-pool>=3.2` to the `runtime` extra.
- **Task 3 (`c53d212`, TDD)** — Added `pg_dsn`/`sql_repo` conftest fixtures gated on `TEST_DATABASE_URL` (skip cleanly when unset) that apply `0001`/`0002` to the test DB and truncate between tests. `tests/test_repository_sql.py` proves round-trip (+`task_metadata`), restart-survival across a pool drop/reopen (all four DUR-01 families: tasks+task_events, sessions, approvals/tool_calls), cross-tenant empty reads (DUR-02), and resume-executes-approved-write against SQL (closes Pitfall 3).

## Verification Evidence

- No-DB (default `make test` equivalent): **60 passed, 4 skipped** (SQL tests skip on unset `TEST_DATABASE_URL`). `make smoke` → `SMOKE OK`.
- Live DB (`pgvector/pgvector:pg16` on `:55432`, `TEST_DATABASE_URL` set, psycopg installed in a venv): **64 passed** — the 4 SQL-backed tests run and pass.
- Grep gate (Task 1): no `repo._tool_calls`/`repo._approvals` reach-ins outside `repository.py`.
- SQL parameterization (T-01-02): the only f-strings in SQL embed static `_*_COLS` identifier constants; every value uses `%s`.
- ruff: clean on all changed files.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Enum value coercion for model fields built from enum defaults**
- **Found during:** Task 3 (the live-DB round-trip test surfaced it; the in-memory suite could not).
- **Issue:** `RepositorySQL` wrote `str(task.state)` etc. for enum-valued model fields. Under `use_enum_values=True`, fields populated from an enum *default* (e.g. `TaskRecord.state = TaskState.RECEIVED`) keep the bare enum, and `str(TaskState.RECEIVED)` on a str-mixin enum yields `'TaskState.RECEIVED'` — written into the TEXT column, then failing Pydantic re-validation on read (`ValidationError: Input should be 'received'...`).
- **Fix:** Added `_enum_value(value) -> str` (returns `.value` for `Enum`, else `str()`) and used it for every enum write in `create_task`, `transition_task`, `append_event`, `upsert_tool_call`, `upsert_approval`, `upsert_proposal`.
- **Files modified:** `src/agent_mesh/services/repository.py`
- **Commit:** `c53d212`

**2. [Rule 3 - Blocking] Migration applier comment/statement splitting**
- **Found during:** Task 3 (first live-DB run errored `syntax error at or near "approvals"`).
- **Issue:** `0001_init.sql` contains `--` comments whose prose has commas/semicolons, plus one inline trailing comment after a `;`; a naive `split(";")` corrupted statements.
- **Fix:** The conftest applier now cuts each line at `--` (no `--` appears inside any string literal in these DDL files) before splitting on `;`. Statement-splitting also sidesteps any psycopg multi-statement `execute` restriction.
- **Files modified:** `tests/conftest.py`
- **Commit:** `c53d212`

### Advisor-flagged landmines pre-empted (no separate fix needed)
- `list_events`/`list_evaluations` signature widening broke the one real caller (`self_improvement.py:253`) — updated in Task 1 (grep confirmed it was the only non-test caller).
- Session durability done inside `create_task` (no `upsert_session` protocol method that only `RepositorySQL` would implement, which would break the Protocol contract).

## Out-of-Scope / Deferred

- **Pre-existing env gap:** `fastapi` is not installed in this worktree's interpreters, so `tests/test_importability.py::test_module_imports[agent_mesh.api.app]` fails (`ModuleNotFoundError: fastapi`). Unrelated to 01-01 (app.py untouched; no interpreter on PATH has fastapi). Resolution: `make install` before `make test`. Logged in `deferred-items.md`. The full suite is 60/60 (no-DB) once this single env-gated test is deselected.

## Threat Model Disposition

| Threat ID | Disposition | Evidence |
|-----------|-------------|----------|
| T-01-01 (cross-tenant disclosure) | mitigated | `tenant_id` mandated in protocol + `WHERE ... AND tenant_id = %s`; `test_cross_tenant_reads_return_empty` asserts `[]` |
| T-01-02 (SQL tampering) | mitigated | `%s` params only; f-strings embed static column-list identifiers, not values |
| T-01-03 (audit-trail repudiation) | mitigated | `transition_task` UPDATE+INSERT in one `with conn:`; restart-survival test reads back the task_events row |
| T-01-04 (silent drop of approved write) | mitigated | protocol widened + reach-ins migrated before SQL existed; `test_resume_executes_approved_write_against_sql` asserts `executed` against SQL |
| T-01-SC (psycopg-pool supply chain) | accepted | RESEARCH dispositioned it first-party companion to psycopg (same maintainer/repo); plan stayed autonomous |

No new threat surface introduced beyond the plan's `<threat_model>`.

## Self-Check: PASSED
- FOUND: src/agent_mesh/services/repository.py (`class RepositorySQL`)
- FOUND: tests/test_repository_sql.py (`TEST_DATABASE_URL`)
- FOUND: pyproject.toml (`psycopg-pool`)
- FOUND commit a164825 (Task 1)
- FOUND commit 8eef9b8 (Task 2)
- FOUND commit c53d212 (Task 3)
