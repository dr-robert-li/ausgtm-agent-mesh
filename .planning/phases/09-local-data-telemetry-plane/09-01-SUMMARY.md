---
phase: 09-local-data-telemetry-plane
plan: 01
subsystem: local-data-telemetry-plane
tags: [makefile, runbook, env-config, postgres, pgvector, langfuse, tests]
requires:
  - "Phase 8 local inference lane (run-* operator-target pattern, RUNBOOK structure)"
  - "Existing migrations 0001->0004 + conftest pg_dsn fixture (committed pre-phase)"
provides:
  - "make run-pg best-effort local pgvector Postgres target"
  - "test-pg lane extended with the new DDL schema-assertion test"
  - "pinned dev-only local DSN defaults in .env.example (DATABASE_URL + TEST_DATABASE_URL)"
  - "LANGFUSE_HOST self-host default + documented upstream Langfuse self-host path"
  - "tests/test_local_data_plane.py — DDL-level assertion of 0003/0004 migrated objects"
affects:
  - "Phase 10 full-stack compose (consumes this local Postgres + Langfuse run path)"
  - "Phase 11 offline posture (consumes the local data plane)"
tech-stack:
  added: []
  patterns:
    - "best-effort operator run-target (out of CI, RUNBOOK-documented) — mirrors run-vllm/run-ollama"
    - "DSN loud-skip gating via the existing pg_dsn fixture (never silent, never hard-fail)"
    - "information_schema DDL introspection with subset (<=) assertions"
key-files:
  created:
    - "tests/test_local_data_plane.py"
    - ".planning/phases/09-local-data-telemetry-plane/09-01-SUMMARY.md"
  modified:
    - "Makefile"
    - "tests/conftest.py"
    - ".env.example"
    - "RUNBOOK.md"
decisions:
  - "Task 2's tdd=\"true\" treated as a false flag: both files are test-code, no source files, and the asserted schema (0003/0004) already exists in committed migrations — no RED/GREEN cycle was reachable, so both files were committed as one test() commit (behavior-adding predicate returns false: no src/ files)."
  - "conftest _MIGRATIONS kept as the explicit 4-tuple (NOT swapped for a directory glob) — a glob would auto-apply a future 0005 and risk non-migration .sql files; D-03's intent is already satisfied by the tuple."
  - "psycopg imported inside the test body (not module scope) to keep collection clean on any interpreter and match the conftest convention."
metrics:
  duration: 1 session
  tasks: 3
  files: 6
  completed: 2026-06-10
---

# Phase 9 Plan 01: Local Data & Telemetry Plane Summary

Documented and make-wired a fully local persistence + observability plane — a best-effort `make run-pg` pgvector Postgres target, pinned dev-only local DSN defaults, a self-host Langfuse default + documented upstream path, and a DDL-level schema-assertion test proving migrations 0003/0004 land in the live migrated schema — with **zero `src/` change**.

## What Was Built

**Task 1 — Makefile (LDATA-01), `feat`:** Added a best-effort `run-pg` target (single `pgvector/pgvector:pg16` container, persistent `-d` + named volume, creds/port/db locked to the pinned `.env.example` DSN), a `help` entry, `run-pg` in `.PHONY`, and extended the `test-pg` file list with `tests/test_local_data_plane.py`. `run-pg` is never referenced by `test`/CI; no `run-langfuse` target exists.

**Task 2 — conftest + new test (LDATA-03), `test`:** Corrected the stale `_apply_migrations` docstring (was "Apply 0001/0002") to state it applies all `_MIGRATIONS` (0001->0004) in lexical order — **applier body, tuple, comment-strip regex, and `;`-split untouched**. Created `tests/test_local_data_plane.py`: a DSN-gated test riding the existing `pg_dsn` fixture (loud-skips on unset `TEST_DATABASE_URL`, applies 0001->0004, truncates) that asserts via `information_schema` the three 0003 `tool_calls` columns (`integration_style`, `schema_validation`, `is_read`), the two 0004 tables (`self_improvement_active_version`, `ai_bom_snapshots`), and reachability — all subset (`<=`) assertions.

**Task 3 — .env.example + RUNBOOK (LDATA-01/02), `docs`:** Pinned dev-only local defaults (`DATABASE_URL` + new `TEST_DATABASE_URL` = the `run-pg` DSN, `LANGFUSE_HOST=http://localhost:3000`) with Langfuse keys left blank and a dev-only disclosure. Added a new RUNBOOK "Local data & telemetry plane" section: a Postgres run path (run-pg/test-pg copy-paste, pgvector-image fact, honest dev-only/best-effort/never-CI disclosure) and a documentation-only Langfuse self-host subsection (upstream docker compose path, UI port 3000, v3 multi-container stack marked datable/MEDIUM-confidence, client-vs-server key boundary, standup deferred to Phase 10).

## Verification

- Zero-src guardrail: `git diff e9d4104..HEAD -- src/` is **empty**.
- Default lane green + DB-free: full `pytest -m "not live"` via `.venv/bin/python` → **312 passed, 10 skipped, exit 0** (the new test loud-skips).
- New test loud-skips on unset `TEST_DATABASE_URL`: `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_local_data_plane.py` → `1 skipped`, exit 0.
- New test wired into the named durable lane: `tests/test_local_data_plane.py` in the `test-pg` file list.
- D-01 <-> D-04 lockstep: `run-pg` creds/port/db (`postgres:postgres`, `5432`, `agent_mesh`) match the pinned `.env.example` DSN.
- conftest applier behavior unchanged: explicit 4-tuple kept, no directory glob, stale docstring corrected.
- No forbidden targets: no `run-langfuse` in Makefile or RUNBOOK; Langfuse keys blank in `.env.example`.

## Deviations from Plan

None — plan executed exactly as written. Task 2 carried a `tdd="true"` flag, but per the plan's own CRITICAL D-03 reconciliation the asserted schema already exists and both files are test-code (no source files), so the behavior-adding predicate is false and no RED/GREEN cycle was reachable; both files were committed as a single `test()` commit (documented in decisions).

## Authentication Gates

None.

## Commits

- `7307234` feat(09-01): add best-effort run-pg target and wire new test into test-pg
- `c0d4b86` test(09-01): correct conftest docstring + add DDL schema-assertion test
- `1be4295` docs(09-01): pin local data-plane .env defaults + RUNBOOK section

## Known Stubs

None. The Langfuse self-host path is documentation-only by design (D-02); the multi-container standup is explicitly deferred to Phase 10's compose, as disclosed in RUNBOOK.

## Self-Check: PASSED

- FOUND: tests/test_local_data_plane.py
- FOUND: .planning/phases/09-local-data-telemetry-plane/09-01-SUMMARY.md
- FOUND commit 7307234, c0d4b86, 1be4295
