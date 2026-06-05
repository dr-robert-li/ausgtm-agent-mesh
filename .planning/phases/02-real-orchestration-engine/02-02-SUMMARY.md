---
phase: 02-real-orchestration-engine
plan: 02
subsystem: orchestration
tags: [langgraph, checkpointer, interrupt, hitl, postgres-saver, sqlite-saver, orch-02, orch-03]

# Dependency graph
requires:
  - phase: 02-real-orchestration-engine
    plan: 01
    provides: "build_graph() uncompiled StateGraph topology, _run_langgraph compile+invoke, langgraph_available()/deep_agents_available() gates, raised agents-extra pins (both checkpoint backends)"
  - phase: 01-durability-persistence
    provides: "approvals signed-token ledger (verify_approval_token, is_approved), runner._resume_after_approval, AWAITING_APPROVAL lifecycle"
provides:
  - "Terminal write_gate node expressing the approval pause as a LangGraph interrupt() (ORCH-03)"
  - "Durable checkpointer selection: PostgresSaver from DATABASE_URL (prod) + test-injectable file-backed SqliteSaver hook; graph compiles WITH the checkpointer"
  - "orchestrator.resume_mesh(task, decision) mirroring the run_mesh langgraph_available() gate with a value-checked-checkpointer terminal no-op fallback"
  - "runner._resume_after_approval calls resume_mesh; the write still executes ONLY there under is_approved() (SEC-01/SEC-02 preserved)"
  - "ORCH-02 restart-sim (file-backed SqliteSaver always-on; PostgresSaver env-gated) + ORCH-03 interrupt-HITL coverage"
affects: [03-model-observability, phase-3-langfuse]

# Tech tracking
tech-stack:
  added: []  # pins already raised by 02-01; backends installed into the shared .venv at execution (see Deviations)
  patterns:
    - "interrupt() is the durable PAUSE mechanism ONLY; the signed-token ledger stays the single decision authority (RF-1)"
    - "Command(resume=...) carries an already-verified boolean decision, never an approver_id the graph trusts (SEC-01)"
    - "resume_mesh value-checks _select_checkpointer(): no durable checkpointer -> terminal no-op (NOT a blanket try/except ImportError swallow)"
    - "thread_id == tenant-scoped task_id (DUR-02); checkpointer keys on thread_id only"
    - "Test-injectable checkpointer seam (set_checkpointer_override) mirroring RepositorySQL's test-DSN seam; file-backed SqliteSaver, never InMemorySaver"

key-files:
  created:
    - tests/test_interrupt_hitl.py
    - tests/test_checkpointer_resume.py
  modified:
    - src/agent_mesh/worker/graph.py
    - src/agent_mesh/worker/orchestrator.py
    - src/agent_mesh/worker/runner.py

key-decisions:
  - "resume_mesh on the stack path with NO durable checkpointer returns a terminal no-op via a VALUE check on _select_checkpointer() (Command(resume=...) requires a checkpointer; absent one, the run paused via the worker's AWAITING_APPROVAL stash, not a graph interrupt). This is NOT the forbidden blanket try/except — it branches on langgraph_available() then on the checkpointer value."
  - "ORCH-03's durable graph-resume is PROVEN by an agents-gated test that injects a real file-backed SqliteSaver, so the no-op fallback is never hiding a dead feature (T-02-02-06 intent satisfied)."
  - "Checkpoint backends gated on actual importability (langgraph.checkpoint.sqlite/postgres find_spec), not just the conftest agents_stack fixture which only checks langgraph+deepagents."

requirements-completed: [ORCH-02, ORCH-03]

# Metrics
duration: 40min
completed: 2026-06-06
---

# Phase 2 Plan 02: Checkpointer + Interrupt-Based HITL Summary

**A proposed write now pauses the LangGraph mesh as a durable `interrupt()` and resumes from a Postgres/Sqlite-file checkpoint when the verified decision arrives (ORCH-02 + ORCH-03) — with the Phase-1 signed-token ledger kept as the single decision authority and the write still executing only in the worker under `is_approved()`, so SEC-01/SEC-02 hold through the new path.**

## Performance

- **Duration:** ~40 min
- **Completed:** 2026-06-06
- **Tasks:** 3 (all TDD plan tasks)
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments
- Added a terminal `write_gate_node` in `graph.py` that calls `interrupt({"proposed_writes": ...})` to pause+checkpoint the run, and wired `reviewer -> write_gate -> END`. The node never executes the write and never reads/trusts an approver identity from the resumed value (RF-1).
- Added `_select_checkpointer()` in `orchestrator.py` (PostgresSaver from `DATABASE_URL` prod, test-injectable file-backed SqliteSaver via `set_checkpointer_override`) and compiled the graph WITH it. `_run_langgraph` now maps `__interrupt__` -> `OrchestrationResult.proposed_writes`.
- Added `resume_mesh(task, decision)` mirroring the `run_mesh` `langgraph_available()` gate, with a value-checked terminal no-op when no durable checkpointer is configured. Wired it into `runner._resume_after_approval`; the Tool Gateway `.execute` stays inside the worker under `approvals.is_approved()` (unchanged).
- Proved ORCH-02 with a file-backed SqliteSaver restart simulation (drop saver+graph+conn, reopen a fresh saver on the same file, `Command(resume=...)` on the same `thread_id` -> resumes from the persisted checkpoint to terminal), plus a TEST_DATABASE_URL-gated PostgresSaver mirror.
- Proved ORCH-03 interrupt-HITL: pause-on-write, verified resume completes+executes the write, structural SEC-01 (resume carries no identity channel), and SEC-02a (mutated payload blocks the write through the new resume flow).

## Task Commits
1. **Task 1: write-gate interrupt node + checkpointer compile + stub-aware resume_mesh** — `79a0294` (feat)
2. **Task 2: call resume_mesh from runner._resume_after_approval + ORCH-03 interrupt-HITL test** — `e5739bb` (feat)
3. **Task 3: ORCH-02 resume-after-restart test (SqliteSaver-file + PostgresSaver env-gated)** — `72e7b6e` (test)
4. **Post-task hardening: cache+close PostgresSaver and exercise the prod `_select_checkpointer()` branch** — `75d7cda` (fix) — see Deviation 4.

_All three are TDD plan tasks; verified against the real stack under the project `.venv` (the only interpreter with langgraph + the checkpoint backends). The agents-gated and TEST_DATABASE_URL-gated tests RAN for real (sqlite) or skipped cleanly (postgres, no DSN)._

## Files Created/Modified
- `src/agent_mesh/worker/graph.py` (modified) — `MeshState` gains `decision`/`done`; terminal `write_gate_node` calls `interrupt()`; `build_graph` wires `reviewer -> write_gate -> END`.
- `src/agent_mesh/worker/orchestrator.py` (modified) — `_select_checkpointer()` + `set_checkpointer_override()` test seam; `_graph_config` (thread_id = task_id, DUR-02); `_run_langgraph` compiles with the checkpointer and handles `__interrupt__`; `resume_mesh()` with the langgraph_available() gate + value-checked-checkpointer no-op.
- `src/agent_mesh/worker/runner.py` (modified) — imports `resume_mesh`; `_resume_after_approval` calls `resume_mesh(task, True)` (verified boolean only, no approver_id) before the unchanged `is_approved()` execute loop.
- `tests/test_interrupt_hitl.py` (created) — ORCH-03 pause/resume + SEC-01/SEC-02 invariants always-on + agents-gated real-graph interrupt durable resume.
- `tests/test_checkpointer_resume.py` (created) — ORCH-02 SqliteSaver-file restart-sim (always-on under the agents+backend stack) + PostgresSaver mirror (env-gated).

## Decisions Made
- **Value-checked no-op vs forbidden try/except (the load-bearing fix):** `Command(resume=...)` raises `RuntimeError("Cannot use Command(resume=...) without checkpointer")` in langgraph 1.2.4. `resume_mesh` therefore branches on `langgraph_available()` (mirroring `run_mesh`) and then on the *value* of `_select_checkpointer()` — when it is `None` (no `DATABASE_URL`, no test override), the run was never durably graph-checkpointed (it paused via the worker's AWAITING_APPROVAL stash), so resume is a terminal no-op. This is a value check, not a blanket `try/except ImportError` swallow (which the Task-1 acceptance criterion forbids).
- **No-op is not hiding a dead feature:** an agents-gated test injects a real file-backed SqliteSaver and exercises the actual `interrupt()` pause + `Command(resume=...)` durable resume, so ORCH-03's graph-resume is genuinely proven (T-02-02-06 intent).
- **Backend importability gating:** the new tests gate on `importlib.util.find_spec("langgraph.checkpoint.sqlite"/"postgres")` in addition to the conftest `agents_stack` fixture, because that fixture only checks langgraph+deepagents, not the separately-optional checkpoint backends.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed the declared checkpoint backends into the shared `.venv` ("pinned ≠ installed")**
- **Found during:** Execution start (env probe).
- **Issue:** 02-01 raised the `[agents]` extra pins to include `langgraph-checkpoint-postgres~=3.1` and `langgraph-checkpoint-sqlite~=3.1`, and its SUMMARY claimed both backends were "installed". They were NOT installed in the project `.venv` (only langgraph 1.2.4 core + `langgraph-checkpoint` 4.1.1). `from langgraph.checkpoint.sqlite import SqliteSaver` raised `ModuleNotFoundError`. The plan's tests import these backends directly; without them `tests/test_checkpointer_resume.py` would ERROR (not skip) at import, breaking the "pytest -q tests/ exits 0" gate.
- **Fix:** Installed the repo's OWN declared extra (`pip install "langgraph-checkpoint-sqlite~=3.1" "langgraph-checkpoint-postgres~=3.1"`). This is provisioning the committed `[agents]` extra (first-party langchain-ai names already in `pyproject.toml`), not introducing an unknown package — outside the package-legitimacy checkpoint exclusion. A dry-run resolver pass was read first to confirm the install is ADDITIVE: core `langgraph` (1.2.4) and `langgraph-checkpoint` (4.1.1) were UNCHANGED; only `aiosqlite`, `sqlite-vec`, and the two `~=3.1` backends were added. The `~=3.1` pins co-resolve with the installed `langgraph-checkpoint>=4.1.0,<5.0.0` core, confirming the pins are correct.
- **Verification:** post-install both backends import; full suite 89 passed / 6 skipped; sqlite restart-sim ran for real.
- **Committed in:** N/A (no source change; shared-env provisioning of the declared extra). No `pyproject` edit needed — the pins already existed.

**2. [Rule 1 - Bug] `resume_mesh` stack-path no-op had to be reachable when the stack is present but no checkpointer is configured (regression of the always-on SEC suite)**
- **Found during:** Task 2 (first run of `tests/test_interrupt_hitl.py` + the phase-gate suite).
- **Issue:** The plan's threat register (T-02-02-06) assumed the stub no-op is reachable ONLY when the stack is genuinely ABSENT — it assumed THIS env had no agents stack. That assumption is false (02-01 documented the `.venv` HAS the stack, and this plan installed the checkpoint backends). With the stack present and no `DATABASE_URL`, the unconditional `resume_mesh(task, True)` in the runner took the stack path and crashed on `Command(resume=...) without checkpointer`, turning the always-on `test_approval_security::test_mutated_payload_invalidates_approval` (the PHASE GATE) RED.
- **Fix:** `resume_mesh` value-checks `_select_checkpointer()` after the `langgraph_available()` gate and returns a terminal no-op when it is `None`. The write still executes in the worker under `is_approved()`; ORCH-03's durable resume is proven by the agents-gated SqliteSaver test. The phase gate is green again.
- **Committed in:** `e5739bb` (Task 2).

**3. [Rule 1 - Bug] `tests/test_interrupt_hitl.py` needed an autouse `APPROVAL_SIGNING_SECRET` fixture (gate fails closed)**
- **Found during:** Task 2 test run.
- **Issue:** The approval gate fails closed; `verify_approval_token` returns `None` without a configured secret. The new test file initially set the secret only in two tests, so the pause/token-issue assertions failed.
- **Fix:** Added an autouse `_signing_secret` fixture mirroring `tests/test_approval_security.py`.
- **Committed in:** `e5739bb` (Task 2).

**4. [Rule 1 - Bug] `_select_checkpointer()` prod Postgres branch leaked a connection per task and was untested; restored Task-1's dropped "expose a `close()`" instruction**
- **Found during:** Final review.
- **Issue:** Task 1's action said "construct via `PostgresSaver.from_conn_string(...)`, call `.setup()`, expose a `close()`." The first cut entered the `from_conn_string` context manager (`__enter__`) per call with NO close — every `run_mesh`/`resume_mesh` on the prod path would open a fresh connection and never release it (a per-task leak). The DATABASE_URL construction branch was also exercised by no test (the postgres restart test built its own inline saver, never calling `_select_checkpointer()`).
- **Fix:** `_select_checkpointer()` now builds the `PostgresSaver` ONCE, caches it by DSN, reuses it across run/resume, and `close_checkpointer()` releases it. `test_resume_after_restart_postgres` was rewired to go through `_select_checkpointer()` (with `DATABASE_URL` monkeypatched to the test DSN), so the prod construction + cache + close lifecycle is genuinely exercised whenever a DSN is present (it still skips cleanly without one — no usable local Postgres in this env, consistent with the existing `test_repository_sql` Postgres gating).
- **Verification:** full suite 89 passed / 6 skipped; ruff clean; smoke OK; phase gate 15 passed.
- **Committed in:** `75d7cda`.

---

**Total deviations:** 4 (1 blocking env-provisioning of the repo's own declared extra; 3 bug fixes in this plan's new code/tests). **Impact on deliverables:** none — all ORCH-02/ORCH-03 acceptance criteria met and SEC-01/SEC-02 preserved.

## Issues Encountered
- 02-01's SUMMARY claim that "both checkpoint backends" were installed was inaccurate (they were pinned, not installed). Verified env truth directly rather than trusting the summary; installed the declared backends (Deviation 1).
- The plan/threat-register assumed this env lacks the agents stack, so the `resume_mesh` stub no-op would keep SEC green. In reality the stack IS present, so the no-op had to be reachable via a checkpointer value check, not via the absent-stack path (Deviation 2). The security INTENT is unchanged and stronger: the real interrupt/resume path is genuinely exercised by an agents-gated test.

## Threat Surface
All six 02-02 STRIDE entries are mitigated and exercised:
- **T-02-02-01** (forged approver via `Command(resume=...)`) — structural: `resume_mesh(task, decision)` takes no `approver_id`; the runner passes a bare boolean; approver derived only from `verify_approval_token`. Asserted in `test_resume_carries_no_identity_channel`.
- **T-02-02-02** (mutated payload after approval) — write executes only under `is_approved()`; asserted in `test_mutated_payload_blocks_write_through_resume` and the phase-gate suite.
- **T-02-02-03** (cross-tenant/task resume) — `thread_id == tenant-scoped task_id`; checkpointer keys on thread_id only.
- **T-02-02-04** (interrupt() treated as the approval record) — no Tool Gateway `.execute` in any graph node; interrupt is pause-only.
- **T-02-02-05** (restart loses durable state) — file-backed SqliteSaver / PostgresSaver; no purely in-memory saver; restart-sim proves durable resume.
- **T-02-02-06** (resume silently no-ops, defeating ORCH-03) — `resume_mesh` branches on `langgraph_available()` then a checkpointer VALUE check (no blanket ImportError swallow); the agents-gated SqliteSaver test proves the real durable resume so the no-op is never hiding a dead feature.

No new threat surface beyond the plan's register.

## Known Stubs
- The graph nodes still return deterministic role-shaped output when model credentials are absent (inherited D-01/D-02 design from 02-01; Phase 3 wires gateway-routed models). Not a blocking stub for ORCH-02/ORCH-03 — the durability/interrupt machinery is fully real and exercised.
- `resume_mesh`'s no-checkpointer terminal no-op is intentional, not a stub: without a configured durable saver the run paused via the worker's AWAITING_APPROVAL stash and the write still executes under `is_approved()`. Documented above.

## Next Phase Readiness
- **Phase 3** can wire real models/Langfuse via the existing `build_roster(model=...)` seam (unchanged) and correlate traces via the still-unset `trace_id`.
- **Prod durable resume** activates once `DATABASE_URL` is set: `_select_checkpointer()` builds a `PostgresSaver` ONCE (cached by DSN, reused across run/resume to avoid a per-task connection leak), calls `.setup()` (idempotent, library-owned sibling schema), and `resume_mesh` takes the real `Command(resume=...)` path. `close_checkpointer()` releases the cached connection at shutdown. The Postgres construction + cache + close lifecycle is exercised by `test_resume_after_restart_postgres` when `TEST_DATABASE_URL` is set (it routes through `_select_checkpointer()` with `DATABASE_URL` monkeypatched); it skips cleanly without a DSN, so the prod branch is verified-when-a-DB-is-present rather than never.
- **Worker shutdown must call `orchestrator.close_checkpointer()`** to release the cached PostgresSaver connection (no-op when no DSN was used). Wiring this into the actual worker process lifecycle is a small follow-up for the prod runtime.
- **The checkpoint backends must be installed in any environment that runs the agents-gated checkpointer tests or the prod Postgres path.** The pins live in the `[agents]` extra; ensure `pip install -e .[agents]` (or equivalent) actually installs `langgraph-checkpoint-sqlite`/`-postgres` — 02-01 pinned but did not install them.

## Self-Check: PASSED
- Created/modified files all present: graph.py, orchestrator.py, runner.py, tests/test_interrupt_hitl.py, tests/test_checkpointer_resume.py, 02-02-SUMMARY.md.
- Commits resolvable in git: 79a0294, e5739bb, 72e7b6e, 75d7cda.
- Plan verification gate: `test_approval_security.py` 15 passed; full `tests/` 89 passed / 6 skipped; `make smoke` SMOKE OK; no InMemorySaver in changed src/tests; ruff clean.

---
*Phase: 02-real-orchestration-engine*
*Completed: 2026-06-06*
