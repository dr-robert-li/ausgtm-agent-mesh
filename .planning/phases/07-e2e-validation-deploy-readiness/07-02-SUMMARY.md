---
phase: 07-e2e-validation-deploy-readiness
plan: 02
subsystem: e2e-tests
tags: [e2e, durability, checkpointer, mcp, langgraph, sqlite, postgres]
requires:
  - "agent_mesh.worker.graph.build_graph (write_gate interrupt)"
  - "agent_mesh.services.task_service.request_from_mcp / TaskService.create_task"
  - "agent_mesh.worker.orchestrator._select_checkpointer / close_checkpointer"
  - "agent_mesh.api.mcp_server.build_mcp_server (mcp extra)"
  - "tests/conftest.py fixtures: agents_stack, pg_dsn, repo"
provides:
  - "E2E-02 default-lane proof: in-process MCP ingress + sqlite durable restart-resume + artifact survival"
  - "E2E-02 opt-in Postgres-lane + MCP-transport variant"
affects:
  - "tests/e2e/ suite (default lane stays green; opt-in axes skip loudly when unavailable)"
tech-stack:
  added: []
  patterns:
    - "Deferred imports after skip gates (collectable+skippable in minimal env, never a collection error)"
    - "File-backed SqliteSaver drop-then-reopen-same-store restart-sim (NEVER :memory:)"
    - "Postgres lane routed through PROD _select_checkpointer/close_checkpointer lifecycle (no inline saver)"
key-files:
  created:
    - "tests/e2e/test_e2e_mcp_durable_job.py"
    - "tests/e2e/test_e2e_mcp_durable_job_live.py"
  modified: []
decisions:
  - "Deferred build_graph import inside the test body (not analog's top-level import) so the test SKIPS loudly rather than erroring at collection when the agents stack is absent — required by the AC."
  - "MCP-transport test asserts build_mcp_server constructs and funnels into the shared TaskService (mirrored-capability invariant), without standing up an HTTP/streamable transport."
metrics:
  duration: "~25 min"
  completed: "2026-06-08"
requirements: [E2E-02]
---

# Phase 7 Plan 02: E2E-02 MCP Durable Checkpointed Job Summary

Proves E2E-02 (ROADMAP SC-2) end-to-end: an in-process MCP request drives a long-running
checkpointed mesh job that pauses at the LangGraph `write_gate` interrupt, survives a
simulated process restart on a real file-backed sqlite checkpoint, and resumes to return a
non-empty reviewer artifact — with an opt-in Postgres lane and MCP-transport variant.

## What Was Built

**Task 1 — `tests/e2e/test_e2e_mcp_durable_job.py` (default lane, commit `ed49e6d`)**
- In-process MCP ingress via `request_from_mcp(...) -> TaskService.create_task` (D-03
  corrected: there is NO `/mcp` HTTP route; app.py exposes only /healthz, /v1/tasks,
  /slack/events, /v1/approvals).
- File-backed `SqliteSaver` drop-then-reopen-same-store restart-resume (D-04), copied
  verbatim in mechanism from `tests/test_checkpointer_resume.py:56-83`. NEVER `:memory:` —
  the only `:memory:` occurrences are documentation comments asserting the discipline.
- `thread_id == f"tenant-t::{task.task_id}"` (DUR-02 tenant-scoped task id; T-07-05 cross-task
  guard).
- Asserts the paused run carried `proposed_writes`, the resumed run cleared `__interrupt__`,
  `decision is True`, and a non-empty `review` artifact survived the restart.
- No `live` marker; gated on the `agents_stack` fixture + `langgraph-checkpoint-sqlite`
  backend; skips loudly when absent.

**Task 2 — `tests/e2e/test_e2e_mcp_durable_job_live.py` (opt-in variant, commit `e63b3c3`)**
- Postgres lane: the same MCP-request → checkpointed-job → surviving-artifact proof against a
  REAL `PostgresSaver`, routed through the PRODUCTION
  `orchestrator._select_checkpointer()` / `close_checkpointer()` lifecycle (cache reuse
  asserted, drop via `close_checkpointer`, re-select on the same DSN) — never an inline saver.
  Gated on `pg_dsn` (TEST_DATABASE_URL) + the postgres backend; no `live` marker.
- MCP-transport axis: drives `build_mcp_server(service)` (the FastMCP surface behind the `mcp`
  extra) and confirms it funnels into the shared `TaskService` (mirrored-capability
  invariant). Gated on the `mcp` extra being importable; skips loudly when absent.

## Verification Evidence

Run against the project's full-stack dev environment (the parent `.venv`, which has
`.[agents]` + `mcp` + sqlite/postgres backends + ruff — equivalent to `make install-dev`):

| Check | Result |
|-------|--------|
| `pytest tests/e2e/test_e2e_mcp_durable_job.py -m "not live"` (stack present) | **1 passed** |
| `pytest tests/e2e/test_e2e_mcp_durable_job_live.py` (no DSN, mcp present) | **1 passed (mcp-transport), 1 skipped (postgres, no DSN)** |
| `pytest tests/e2e/ -m "not live"` (full e2e suite, stack present) | **3 passed, 1 skipped** (green) |
| Both new files, bare base-only env (langgraph absent) | **3 skipped** (loud, named reasons; never errored/failed) |
| `ruff check` both files | **All checks passed (exit 0)** |
| Greps: `request_from_mcp`, `Command(resume=`, `checkpoints.sqlite`, `tenant-t::`, `_select_checkpointer`, `close_checkpointer`, `pg_dsn`, `build_mcp_server` | all present |
| `:memory:` as a saver / `live` marker | absent (only in doc comments / no marker) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Deferred `build_graph` import to satisfy the loud-skip AC**
- **Found during:** Task 1 (pre-write analysis).
- **Issue:** The durability analog `tests/test_checkpointer_resume.py` imports
  `from agent_mesh.worker.graph import build_graph` at module top-level. In a minimal env
  (langgraph absent), that errors at **collection** — a FAILED collection, not a clean skip.
  Task 1's AC explicitly requires "with the stack absent → SKIPPED loudly, never failed."
- **Fix:** Moved `build_graph` (and `SqliteSaver` / `Command` / service imports) inside the
  test body, AFTER the `agents_stack` fixture + `_backend_available` skip gates. The mechanism
  itself is still copied verbatim from the analog; only the import placement differs. Same
  deferred-import discipline applied to Task 2.
- **Files modified:** both new test files.
- **Commit:** `ed49e6d`, `e63b3c3`.

## Deferred Issues / Out-of-Scope Observations

- The wave-1 file `tests/e2e/test_e2e_slack_write_gated.py` (07-01, commit `38d85b8`) FAILS in a
  bare base-only env with a `ModuleNotFoundError` at its `fastapi.testclient` import (line ~53).
  This is the dependency plan's deliverable and runs green in the full-stack dev env where the
  suite is intended to run (`make test` after `make install-dev`). It is OUT OF SCOPE for this
  plan (E2E-02 only modifies its own two files) and is left untouched.

## Threat Surface

No new security-relevant surface introduced — test-only plan exercising already-hardened
durability seams. T-07-04 (durability-SPOF-masking) is the elevated concern and is directly
mitigated: the saver is file-backed sqlite / real Postgres, never in-memory (asserted by the
`:memory:`-absence discipline and the real-restart drop/reopen). T-07-05 (cross-task resume)
is mitigated by the `tenant-t::`-form tenant-scoped thread_id. No threat flags.

## Known Stubs

None. Both files are real assertions against the production graph + checkpointer lifecycle;
the default lane proves durability via the sqlite fallback (not deferred to live), and the
Postgres lane exercises the production `_select_checkpointer`/`close_checkpointer` path.

## Self-Check

- `tests/e2e/test_e2e_mcp_durable_job.py` — FOUND
- `tests/e2e/test_e2e_mcp_durable_job_live.py` — FOUND
- Commit `ed49e6d` — FOUND
- Commit `e63b3c3` — FOUND
