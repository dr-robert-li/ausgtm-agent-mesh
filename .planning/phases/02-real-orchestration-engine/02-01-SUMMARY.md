---
phase: 02-real-orchestration-engine
plan: 01
subsystem: orchestration
tags: [langgraph, deepagents, langchain, stategraph, supervisor-roster, orch-01]

# Dependency graph
requires:
  - phase: 01-durability-persistence
    provides: OrchestrationResult contract, run_mesh stub-fallback gates, TaskRecord
provides:
  - Real LangGraph StateGraph topology (planner -> researcher/tool-router -> code-writer -> reviewer, reviewer terminal)
  - Declared bounded 4-member Deep Agents roster with the auto general-purpose subagent disabled and roster size logged at startup
  - orchestrator._run_langgraph now compiles+invokes the real graph (no durable-state saver) and maps terminal state to OrchestrationResult
  - Raised agents-extra pins (langchain 1.x, langgraph 1.x, both checkpoint backends, deepagents 0.6.8) so 02-02 needs no pyproject edit
  - conftest agents_stack skip fixture + ORCH-01 test coverage (always-on stub + agents-gated real-graph delegation/bounded-roster)
affects: [02-02-checkpointer-interrupt, 03-model-observability, phase-3-langfuse]

# Tech tracking
tech-stack:
  added: [langgraph>=1.0,<2, langgraph-checkpoint-postgres~=3.1, langgraph-checkpoint-sqlite~=3.1, deepagents~=0.6.8, langchain>=1.0]
  patterns:
    - "Own the StateGraph; use Deep Agents inside nodes as the per-role harness (RF-3 boundary)"
    - "Optional-dep stub-fallback: nodes return deterministic role-distinct output when model creds absent; no model call on the stub path"
    - "Bounded-roster invariant asserted creds-free via SubAgentMiddleware(StateBackend).subagent_names"

key-files:
  created:
    - src/agent_mesh/worker/graph.py
    - src/agent_mesh/worker/roster.py
    - tests/test_orchestration_graph.py
  modified:
    - src/agent_mesh/worker/orchestrator.py
    - pyproject.toml
    - tests/conftest.py

key-decisions:
  - "Disable deepagents' auto general-purpose subagent via a model-scoped HarnessProfile(general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)) — empirically verified against deepagents 0.6.8, not guessed"
  - "Verify the bounded roster (==4, no general-purpose) creds-free by reading SubAgentMiddleware.subagent_names rather than introspecting the compiled CompiledStateGraph"
  - "Compile the graph WITHOUT a durable-state saver in this plan; the Postgres saver + interrupt write-gate are 02-02"

patterns-established:
  - "Real-graph path and stub path both derive proposed_writes from the same write-trigger heuristic so the approval path is exercised identically"
  - "Agents-gated tests use the conftest agents_stack fixture, reusing orchestrator.langgraph_available()/deep_agents_available() so skip and runtime branch never drift"

requirements-completed: [ORCH-01]

# Metrics
duration: 35min
completed: 2026-06-05
---

# Phase 2 Plan 01: Supervisor Roster Summary

**Real LangGraph StateGraph delegating planner -> researcher/tool-router -> code-writer -> reviewer over a bounded, declared 4-member Deep Agents roster (auto general-purpose subagent disabled, size logged), with the deterministic stub kept as the no-stack fallback.**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-06-05T21:38:00Z (approx)
- **Completed:** 2026-06-05T22:13:28Z
- **Tasks:** 3
- **Files modified:** 6 (3 created, 3 modified)

## Accomplishments
- Replaced the placeholder `_run_langgraph` (which returned `_run_stub`) with a real 4-node `StateGraph` that genuinely executes and threads role-distinct state.
- Declared a bounded 4-member Deep Agents roster and **empirically verified** the deepagents 0.6.8 disable mechanism for the auto general-purpose subagent (T-02-01-E), asserting the effective declared roster is exactly four with size logged at startup.
- Raised the stale agents-extra pins to the verified current set (including both checkpoint backends, pinned now so 02-02 never edits `pyproject.toml`); no `langsmith` in any extra.
- ORCH-01 covered by an always-on stub-fallback test plus agents-gated real-graph delegation and bounded-roster tests; the suite stays green on the no-stack interpreter (agents-gated tests skip cleanly) and on the full `.venv` stack (they run and pass).

## Task Commits

Each task was committed atomically:

1. **Task 1: Raise stale agents-extra pins + add agents_stack skip marker** - `2c38a59` (chore)
2. **Task 2: Build the declared bounded roster + the real StateGraph topology** - `832e64c` (feat)
3. **Task 3: Wire orchestrator._run_langgraph to the real graph + ORCH-01 test** - `b7217a4` (feat)

_Note: Tasks 2 and 3 are TDD plan tasks. The roster/graph modules (Task 2) implement the behavior; the always-on + agents-gated tests (Task 3) prove it. Both were verified against the real stack under `.venv` (the only interpreter with the full dependency set) — agents-gated tests genuinely RAN and passed there, and SKIP cleanly under the no-stack interpreter._

## Files Created/Modified
- `src/agent_mesh/worker/graph.py` (created) - Real `StateGraph` with `MeshState` TypedDict and four deterministic, role-distinct nodes; reviewer derives `proposed_writes`; `build_graph()` returns the uncompiled graph (no saver, no write-gate node).
- `src/agent_mesh/worker/roster.py` (created) - `ROSTER` (4 declared subagents), `roster_size()`==4, `effective_roster_names()` (creds-free observation), `build_roster()` (disables general-purpose, asserts the bound, logs size, returns the deepagents supervisor).
- `src/agent_mesh/worker/orchestrator.py` (modified) - `_run_langgraph` builds/compiles/invokes the real graph and maps terminal state to `OrchestrationResult`; `run_mesh` keeps the `langgraph_available()` stub-fallback branch; `import logging` added.
- `pyproject.toml` (modified) - `agents` extra raised to langchain>=1.0, langgraph>=1.0,<2, langgraph-checkpoint-postgres~=3.1, langgraph-checkpoint-sqlite~=3.1, deepagents~=0.6.8.
- `tests/conftest.py` (modified) - `agents_stack` skip fixture reusing the orchestrator import gates.
- `tests/test_orchestration_graph.py` (created) - ORCH-01 tests.

## Decisions Made
- **General-purpose disable (the plan's flagged open question A1/Open-Question-1):** confirmed empirically against the installed deepagents 0.6.8 that `create_deep_agent` auto-injects a fifth `general-purpose` subagent, and that registering a model-scoped `HarnessProfile(general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False))` drops it back to exactly the four declared members. Chosen over supplying a placeholder `general-purpose` subagent (which would pollute the roster).
- **Creds-free bound verification:** the compiled `CompiledStateGraph` does not expose subagent names (they live in the `task` tool description, consumed at build), so the bound is asserted via `SubAgentMiddleware(backend=StateBackend(), subagents=ROSTER).subagent_names` — a public accessor that needs no model credentials and is the documented observation point.
- **Topology only:** the graph is compiled with no durable-state saver and contains no pause/write-gate node, per the plan's explicit 02-02 boundary.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Selected the project `.venv` interpreter for verification**
- **Found during:** Execution start (baseline test run)
- **Issue:** With no venv activated, the Makefile's `PY ?= python` resolves to the *system* Python 3.14, which lacks `fastapi` (a declared core dependency) AND the agents stack — 8 pre-existing API-import failures and all agents-gated tests would only skip there. The project's `.venv` (Python 3.14 with fastapi + langgraph 1.2.4 + deepagents 0.6.8 installed) is the interpreter with the full set; the normal workflow is `source .venv/bin/activate && make test`.
- **Fix:** Ran all verification under `/Users/robertli/Desktop/consulting/ausgtm-agent-mesh/.venv/bin/python` with `PYTHONPATH=src`. No source change required; the missing `fastapi` is a pre-existing environment gap (out of this plan's scope), not a code defect.
- **Verification:** Under `.venv`: full suite 81 passed / 5 skipped (SQL-DB-gated only), agents-gated orchestration tests RAN and passed, `make smoke` → SMOKE OK, ruff clean. Under system python: 2 always-on pass, 2 agents-gated skip cleanly.
- **Committed in:** N/A (no source change; verification-environment selection only)

---

**Total deviations:** 1 (1 blocking, verification-environment selection — no source/scope change)
**Impact on plan:** None on deliverables. The plan's acceptance criteria assumed "agents stack absent → tests skip" for *this* env; in reality the working interpreter HAS the stack, so the agents-gated tests run for real and pass — a stronger result than the assumed skip. The pre-existing system-python `fastapi` gap is documented and out of scope.

## Issues Encountered
- The plan flagged the deepagents 0.6.8 general-purpose disable mechanism as unverified (A1/Open-Question-1). Resolved by reading the installed package source and running a capture experiment (monkeypatching `SubAgentMiddleware.__init__`) to confirm both the default 5-subagent injection and the harness-profile disable down to 4. No guessing of flag names.

## Threat Surface
- T-02-01-E (roster grows beyond declared 4) — **mitigated and verified**: `general-purpose` is disabled and `effective_roster_names()` asserts exactly `{planner, researcher, code_writer, reviewer}`; an agents-gated test checks `general-purpose` is absent.
- T-02-01-I (LangSmith auto-tracing leaks prompts) — **mitigated**: no `langsmith` import, no `LANGCHAIN_TRACING_V2`/`LANGSMITH_API_KEY` set (grep-clean in source).
- T-02-01-SC (package install) — first-party langchain-ai stack already installed in `.venv`; no new install performed during execution.

No new threat surface introduced beyond the plan's register.

## Known Stubs
- Graph nodes return deterministic role-shaped output when model credentials are absent. This is the intended D-01/D-02 design (no model calls in the importable POC); Phase 3 swaps in gateway-routed models via `build_roster(model=...)` and live node delegation. Documented and intentional — not a blocking stub for ORCH-01.

## Next Phase Readiness
- **02-02** can add the Postgres checkpointer and the interrupt-based write-gate: `build_graph()` returns an uncompiled `StateGraph` ready to `.compile(checkpointer=...)`, and both checkpoint backends are already pinned. No `pyproject` edit needed.
- **Phase 3** can wire real models/Langfuse: `build_roster(model=...)` is the seam; `trace_id` is intentionally left unset for Langfuse correlation.
- **`register_harness_profile` is a session-global side effect.** `build_roster()` registers a harness profile that disables the general-purpose subagent for its model id, and that registration persists for the rest of the process/test session. Benign here (no other test builds a deepagent for that model), but 02-02 / Phase-3 authors building deepagents for the same model id will inherit the disable — worth keeping in mind.
- **Verify under the project venv:** verification was run with the project `.venv` interpreter (`source .venv/bin/activate && make test`, or `.venv/bin/python -m pytest`). The system Python on PATH has neither `fastapi` (a pre-existing gap, confirmed in the pre-change baseline) nor the agents stack, so the agents-gated tests only run under the venv. The verifier should run under the activated venv as usual.

## Self-Check: PASSED
- All created/modified files present: graph.py, roster.py, test_orchestration_graph.py, orchestrator.py, pyproject.toml, conftest.py, 02-01-SUMMARY.md.
- All task commits resolvable in git: 2c38a59, 832e64c, b7217a4.

---
*Phase: 02-real-orchestration-engine*
*Completed: 2026-06-05*
