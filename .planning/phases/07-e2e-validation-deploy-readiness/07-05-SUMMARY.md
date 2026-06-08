---
phase: 07-e2e-validation-deploy-readiness
plan: 05
subsystem: testing
tags: [langgraph, sqlite-checkpointer, postgres-checkpointer, fastmcp, e2e, durability, hitl]

# Dependency graph
requires:
  - phase: 07-e2e-validation-deploy-readiness
    provides: "E2E-02 default + opt-in lanes (07-02), production checkpointer seam (orchestrator.set_checkpointer_override / _select_checkpointer / _graph_config)"
provides:
  - "Default-lane E2E-02 (SC-2) durability proof that drives the REAL production Worker/orchestrator restart-resume wiring via the set_checkpointer_override seam"
  - "Discriminating durable-checkpoint assertions (pre-resume survival + post-resume consumption) that go red on checkpoint loss — not a state==completed tautology"
  - "WR-01: MCP-transport test driving the registered FastMCP create_task tool via call_tool"
  - "WR-02: Postgres-lane saver2-is-not-saver negative assertion + runnable make test-pg deploy-readiness hook + RUNBOOK note"
affects: [deploy-readiness, gsd-verify-work]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Seam-driven production-path E2E test: inject a file-backed SqliteSaver through the documented orchestrator.set_checkpointer_override seam and drive Worker.process end to end, rather than compiling an inline graph"
    - "Discriminating durability proof: read the REOPENED checkpointer under production _graph_config(task) for both survival (review channel) and consumption (decision is True)"
    - "DSN-gated deploy-readiness make target with loud-skip via the pg_dsn fixture"

key-files:
  created: []
  modified:
    - "tests/e2e/test_e2e_mcp_durable_job.py"
    - "tests/e2e/test_e2e_mcp_durable_job_live.py"
    - "Makefile"
    - "RUNBOOK.md"

key-decisions:
  - "Drive the default-lane durability proof through the production Worker.process -> run_mesh -> _run_langgraph -> _select_checkpointer -> _graph_config path via the existing set_checkpointer_override seam — no new production seam, production code unchanged."
  - "Key the checkpoint on the BARE production thread_id (task.task_id, uuid4 hex); bare is collision-safe because the checkpointer keys purely on the thread_id string and task_id is globally unique. Scope claimed honestly: proves durable resume through production wiring (CR-01), not DUR-02 cross-task isolation (needs a two-task test)."
  - "Keep BOTH discriminating reads: pre-resume get_tuple(cfg) review-channel survival AND post-resume get_tuple(cfg) decision-is-True consumption. Completion alone is non-discriminating (the approved write replays from the AWAITING_APPROVAL stash even on checkpoint loss)."
  - "Removed the invented tenant-t:: thread_id and the false DUR-02 docstring claim from both E2E-02 modules."

patterns-established:
  - "Production-path E2E via documented test seam: tests exercise the real orchestrator wiring, not a simplified inline copy."
  - "Override teardown hygiene: set_checkpointer_override(None) in finally so the module-global override cannot leak into later agents-gated tests."

requirements-completed: [E2E-02]

# Metrics
duration: 12 min
completed: 2026-06-08
---

# Phase 07 Plan 05: Close SC-2 / E2E-02 (CR-01) Default-Lane Production-Wiring Gap Summary

**Rewrote the default-lane E2E-02 durability test to prove durable restart-resume through the REAL production Worker/orchestrator wiring (via the set_checkpointer_override seam) with discriminating reopened-checkpoint assertions, and folded in the two live-companion warnings (WR-01 registered FastMCP tool, WR-02 Postgres negative assertion + deploy-readiness hook) — all test-side, production code unchanged.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-06-08T10:54Z
- **Completed:** 2026-06-08T11:06Z
- **Tasks:** 3 completed
- **Files modified:** 4

## Accomplishments
- Closed the CR-01 gap that reopened Phase 07: the default-lane durable-job test now drives `Worker.process` end to end on both the pause and resume legs through `run_mesh -> _run_langgraph -> _select_checkpointer -> _graph_config`, injecting a file-backed `SqliteSaver` via the documented `orchestrator.set_checkpointer_override` seam — replacing the prior inline-compiled-graph bypass that keyed on an invented `tenant-t::` thread_id.
- Made the durability proof DISCRIMINATING: a pre-resume `saver2.get_tuple(cfg)` survival read (review channel) and a post-resume `saver2.get_tuple(cfg)` consumption read (`decision is True`), both under the bare production key — they go red on checkpoint loss, so the proof is no longer a `state == completed` tautology.
- WR-01: the MCP-transport test now invokes the REGISTERED FastMCP `create_task` tool via `await server.call_tool(...)` and reads the task back through the shared `TaskService` — a broken/misrouted tool registration now fails.
- WR-02: added the `saver2 is not saver` post-close negative assertion to the Postgres lane, corrected it to the bare production key, and added a runnable `make test-pg` target + RUNBOOK note so the DSN-gated Postgres durable lane actually executes on deploy-readiness validation (loud-skips when `TEST_DATABASE_URL` is unset).

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite default-lane E2E-02 to drive production restart-resume wiring (CR-01)** - `c00d640` (test)
2. **Task 2: WR-01 — drive the registered FastMCP create_task tool via call_tool** - `4f8f23c` (test)
3. **Task 3: WR-02 — Postgres-lane negative assertion + make test-pg + RUNBOOK hook** - `e4cd3a7` (test)

## Files Created/Modified
- `tests/e2e/test_e2e_mcp_durable_job.py` - Default-lane E2E-02 rewritten to drive the production restart-resume wiring via `set_checkpointer_override` + file-backed sqlite, with discriminating `get_tuple(cfg)` survival + consumption assertions on the bare production key.
- `tests/e2e/test_e2e_mcp_durable_job_live.py` - WR-01 (registered FastMCP tool via `call_tool`) + WR-02 (`saver2 is not saver` negative assertion, bare-key `_graph_config`, corrected DUR-02 docstring).
- `Makefile` - `test-pg` target (DSN-gated Postgres durable lane), added to `.PHONY` and help.
- `RUNBOOK.md` - Postgres durable checkpointer lane note (DSN-gated, deploy-readiness `make test-pg` with a pgvector Postgres via `TEST_DATABASE_URL`).

## Verification

- `PYTHONPATH=src .venv/bin/python -m pytest tests/e2e/test_e2e_mcp_durable_job.py -m "not live" -q` → **1 passed** (not skipped) in the .venv.
- Full default lane `pytest -q -m "not live"` → **304 passed, 9 skipped, 23 deselected** — no override leak, no regressions.
- `ruff check` on both edited test modules → clean.
- Acceptance greps: `tenant-t::` == 0 (both modules); `set_checkpointer_override` == 6; `get_tuple(cfg)` == 3 (≥2); `:memory:` == 0; `.sqlite` present; `build_graph().compile` == 0; `"decision"` present; `call_tool` ≥ 1; `server is not None` == 0; `saver2 is not saver` == 1; `test-pg` in Makefile; `TEST_DATABASE_URL` in RUNBOOK.
- `make test-pg PY=.venv/bin/python` without `TEST_DATABASE_URL` → exit 0, Postgres lane loud-skipped.
- `git diff --stat src/` → **empty** (production `_graph_config` and all of `src/` unchanged).

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0. **Impact:** none — production code untouched, all acceptance criteria met first-pass (one in-flight docstring fix removed a literal `build_graph().compile` token from prose so the `== 0` grep held; not a behavioral deviation).

## Issues Encountered

None. Note: `make` targets require `python` on PATH or `PY=.venv/bin/python` (pre-existing environment condition — the `.venv` Python is not on the bare PATH; affects every Make target equally, not this plan).

## Self-Check: PASSED

- key-files modified exist on disk; `git log --grep="07-05"` returns the three task commits.
- All task acceptance criteria re-run and pass; plan-level `<verification>` steps 1-6 all pass.
- Production code unchanged (`git diff --stat src/` empty).

## Next Phase Readiness

Phase 07 gap closed — ready for phase verification (`gsd-verifier`) to re-check SC-2 / E2E-02 against the production-wired durable resume proof.
