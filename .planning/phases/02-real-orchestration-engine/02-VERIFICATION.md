---
phase: 02-real-orchestration-engine
verified: 2026-06-06T09:20:00+10:00
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification: true
human_verification_resolved:
  - test: "Durable Postgres restart test against a real DATABASE_URL"
    resolved: "RESOLVED by orchestrator. Ephemeral pgvector/pgvector:pg16 container + TEST_DATABASE_URL; tests/test_checkpointer_resume.py::test_resume_after_restart_postgres PASSED. PostgresSaver storage binding (_select_checkpointer -> from_conn_string -> setup -> cache -> close) executed and resumed from the durable checkpoint on the same thread_id. Full suite with DSN set: 95 passed, 1 skipped, 0 failed. Criterion 2 now execution-proven against real Postgres."
  - test: "Reconcile pyproject checkpoint-backend pin vs runtime (IN-02)"
    resolved: "FALSE ALARM. Pins langgraph-checkpoint-sqlite~=3.1 / -postgres~=3.1 MATCH the installed backends (both 3.1.0). The 4.1.1 cited is the core langgraph-checkpoint meta-package, which pyproject does NOT pin — resolved transitively by langgraph>=1.0,<2 (1.2.4). Pins are reproducible; no change required."
post_review_fixes:
  - "CR-01 (BLOCKER) + WR-01 (WARNING) fixed in d3febd9 with live Docker-gated containment test"
---

# Phase 02: Real Orchestration Engine — Verification Report

**Phase Goal:** Replace the orchestration stub with a real LangGraph supervisor delegating to a bounded Deep Agents roster, persist graph state in a Postgres checkpointer so long runs resume after restart, express approvals as graph interrupts, and harden the prompt-to-code sandbox. (The real graph runs against the STUBBED model path until Phase 3 — topology, checkpointing, and interrupts are proven here; real model behaviour is exercised in Phase 3/5.)

**Verified:** 2026-06-06T09:20:00+10:00
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A task runs through a real LangGraph supervisor that delegates to the four declared Deep Agents roster members; roster size is logged at startup | VERIFIED | `graph.py` has a real 5-node `StateGraph` (planner→researcher→code_writer→reviewer→write_gate); `roster.py` declares `ROSTER` with exactly 4 members; `roster_size()` returns `len(ROSTER)` == 4; `build_roster()` logs size and asserts general-purpose is absent; `test_roster_is_bounded_at_four` and `test_real_graph_delegation` ran and passed under `.venv`; agents-gated tests skip cleanly without the stack |
| 2 | A long-running (or simulated >60-min) run resumes from its durable Postgres checkpoint after a process restart | VERIFIED (mechanism) / HUMAN-VERIFY (Postgres path) | `test_resume_after_restart_sqlite` ran (13 passed, 1 skipped): file-backed SqliteSaver drop-then-reopen-same-file restart-sim proves the durable mechanism end-to-end. `test_resume_after_restart_postgres` was SKIPPED (no TEST_DATABASE_URL in this environment). `_select_checkpointer()` contains the full PostgresSaver construction, caching, and close lifecycle (code-verified, not execution-verified). See human-verify item 1. |
| 3 | A proposed write pauses the graph as a LangGraph interrupt and resumes from the checkpoint when the decision arrives | VERIFIED | `write_gate_node` in `graph.py:164` calls `interrupt({"proposed_writes": ...})`; `resume_mesh` in `orchestrator.py:246` dispatches `Command(resume=decision)` on the same thread_id; `runner._resume_after_approval` calls `resume_mesh(task, True)` with a bare boolean (no approver_id channel); `test_real_graph_interrupt_pauses_and_resume_mesh_resumes` ran (agents-gated, file-backed SqliteSaver injected via seam) and passed; SEC-01/02 invariant tests are always-on and passed |
| 4 | The sandbox enforces its memory limit without failing open and executes via the hardened container path | VERIFIED | `execute_code` raises `SandboxUnavailable` when `shutil.which("docker") is None` (no uncapped fallback); `--memory={mem}` and `--memory-swap={mem}` are equal in `_docker_run_argv`; `test_refuses_unbounded` (always-on) passed; `test_oom_enforced` (Docker-gated) ran and returned exit 137; `test_timeout_kills_container` (CR-01, Docker-gated) ran and confirmed no container leak after timeout |

**Score:** 4/4 truths verified (criterion 2 has a human-verify dependency on the Postgres storage path)

---

### Deferred Items

No items deferred to later phases — all four criteria are within Phase 2 scope.

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/agent_mesh/worker/graph.py` | StateGraph with 4 role nodes + write_gate + `interrupt()` | VERIFIED | 195 lines; `build_graph()` defined; 5 nodes wired; `interrupt(` called in `write_gate_node`; no `InMemorySaver` |
| `src/agent_mesh/worker/roster.py` | Declared 4-member roster + startup size log + deepagents wiring | VERIFIED | `ROSTER` list has 4 dicts; `roster_size()` returns `len(ROSTER)`; `logger.info("roster size %d: %s", ...)` at line 151; `create_deep_agent` imported and called in `build_roster`; `GENERAL_PURPOSE_NAME` disabled via `HarnessProfile` |
| `src/agent_mesh/worker/orchestrator.py` | `_run_langgraph` calls `build_graph().compile(checkpointer=...)` + `resume_mesh` | VERIFIED | `build_graph` imported at line 215; `compile(checkpointer=_select_checkpointer())` at line 227; `def resume_mesh(task, decision)` at line 246; branches on `langgraph_available()` (value check, no blanket `ImportError` swallow) |
| `src/agent_mesh/worker/runner.py` | `_resume_after_approval` calls `resume_mesh`; write gated by `is_approved()` | VERIFIED | `from agent_mesh.worker.orchestrator import resume_mesh, run_mesh` at line 29; `resume_mesh(task, True)` called at line 117; `approvals.is_approved(record, call.parameters)` at line 127 — unchanged |
| `src/agent_mesh/sandbox/executor.py` | Docker cgroup path + `SandboxUnavailable` + equal `--memory`/`--memory-swap` | VERIFIED | `SandboxUnavailable` at line 29; `shutil.which("docker") is None` gate at line 131; `f"--memory={mem}"` and `f"--memory-swap={mem}"` equal at lines 77-78; `--ulimit=cpu=...` (WR-01) at line 79; named container + `_force_remove_container` on timeout (CR-01); fail-open `except (ValueError, OSError): pass` block absent (grep returns 0 matches) |
| `tests/test_orchestration_graph.py` | ORCH-01 coverage: stub fallback + agents-gated delegation | VERIFIED | `test_stub_fallback` always-on; `test_real_graph_delegation` agents-gated; `test_roster_is_bounded_at_four` agents-gated; all passed |
| `tests/test_checkpointer_resume.py` | ORCH-02 SqliteSaver-file restart-sim (agents-gated) + PostgresSaver env-gated | VERIFIED (code) | `SqliteSaver` used (file-backed, not `:memory:`); `InMemorySaver` absent; `test_resume_after_restart_sqlite` ran and passed; `test_resume_after_restart_postgres` DSN-gated, skipped cleanly |
| `tests/test_interrupt_hitl.py` | ORCH-03 pause/resume + SEC-01/02 invariants always-on | VERIFIED | 4 always-on security tests + 1 agents-gated interrupt-resume test; all passed |
| `tests/test_sandbox.py` | SBX-01: always-on refuse-unbounded + Docker-gated OOM-137 + CR-01 containment | VERIFIED | `test_refuses_unbounded` always-on passed; `test_oom_enforced` Docker-gated passed (exit 137); `test_timeout_kills_container` Docker-gated passed (no container leak) |
| `pyproject.toml` | Agents extra pins: langchain>=1.0, langgraph>=1.0,<2, checkpoint backends, deepagents~=0.6.8 | VERIFIED (pin correctness WARNING) | Pins present; NOTE: see IN-02 — checkpoint-backend pins are `~=3.1` but installed runtime is 4.1.1; see human-verify item 2 |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `orchestrator.py` | `graph.py` | `build_graph().compile().invoke()` | VERIFIED | `from agent_mesh.worker.graph import build_graph` (line 215); `build_graph().compile(checkpointer=...)` (line 227); `compiled.invoke({"prompt": task.prompt}, _graph_config(task))` (line 228) |
| `graph.py` | `roster.py` | Nodes call `build_roster()` when model creds present | VERIFIED (conditional) | `planner_node` imports and calls `build_roster()` under `_model_credentials_present()` guard. On the stub path (no creds, current env) the graph topology runs deterministically without the roster harness — by design (D-01/D-02). Phase 3 activates real delegation. |
| `graph.py` | checkpointer | `builder.compile(checkpointer=...)` | VERIFIED | `_select_checkpointer()` in `orchestrator.py` selects PostgresSaver (prod) or test-injected SqliteSaver; passed to `compile()` |
| `runner.py` | `orchestrator.py` | `resume_mesh(task, True)` inside `_resume_after_approval` | VERIFIED | `from agent_mesh.worker.orchestrator import resume_mesh, run_mesh` (line 29); `resume_mesh(task, True)` (line 117); no `approver_id` in call |
| `runner.py` | `approvals.py` | `is_approved()` re-hash before Tool Gateway execute | VERIFIED | `approvals.is_approved(record, call.parameters)` (line 127); Tool Gateway `.execute` only reachable through this branch |

---

### Data-Flow Trace (Level 4)

Not applicable — no dynamic data-rendering components in this phase. The phase delivers orchestration topology, durable state, and an isolation executor. The approval data flow is fully traced via key-link verification and security invariant tests above.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite green (90 tests) | `PYTHONPATH=src .venv/bin/python -m pytest -q` | 90 passed, 6 skipped (all SQL/DSN-gated) | PASS |
| Phase 2 test files: 13 pass, 1 skip | `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_orchestration_graph.py tests/test_checkpointer_resume.py tests/test_interrupt_hitl.py tests/test_sandbox.py` | 13 passed, 1 skipped (`test_resume_after_restart_postgres` — no TEST_DATABASE_URL) | PASS |
| Stub fallback returns OrchestrationResult | `test_stub_fallback` (always-on) | Passed | PASS |
| Refuse-to-run-unbounded invariant | `test_refuses_unbounded` (always-on, monkeypatches Docker absent) | Passed | PASS |
| Real graph: 4 nodes execute, role-distinct state | `test_real_graph_delegation` (agents-gated, ran under .venv) | Passed | PASS |
| Roster bounded at 4, general-purpose absent | `test_roster_is_bounded_at_four` (agents-gated, ran under .venv) | Passed | PASS |
| SEC-01/SEC-02 invariants through resume path | `test_approval_security.py` phase gate | 15 passed | PASS |

---

### Probe Execution

No conventional `scripts/*/tests/probe-*.sh` probes declared or present for this phase. The pytest suite serves as the probe equivalents; results are recorded in Behavioral Spot-Checks above.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ORCH-01 | 02-01 | Real LangGraph supervisor delegating to bounded 4-member Deep Agents roster; size logged at startup | SATISFIED | `graph.py` + `roster.py` + `orchestrator._run_langgraph`; `test_real_graph_delegation` + `test_roster_is_bounded_at_four` passed; `[x]` in REQUIREMENTS.md |
| ORCH-02 | 02-02 | LangGraph Postgres checkpointer wired; >60-min run resumes from durable checkpoint after restart | SATISFIED (mechanism) / HUMAN-VERIFY (Postgres path) | SqliteSaver restart-sim ran and proved mechanism; PostgresSaver code path present but not execution-verified (DSN-gated skip). See human-verify item 1. |
| ORCH-03 | 02-02 | Write approval is a LangGraph interrupt; pauses graph, resumes from checkpoint when decision arrives | SATISFIED | `write_gate_node` + `resume_mesh` + `runner._resume_after_approval`; `test_real_graph_interrupt_pauses_and_resume_mesh_resumes` passed; SEC-01/02 invariants preserved |
| SBX-01 | 02-03 | Sandbox enforces memory limits without failing open; executes via hardened container path | SATISFIED | `SandboxUnavailable` + equal `--memory`/`--memory-swap` + CR-01 timeout containment; `test_refuses_unbounded` + `test_oom_enforced` + `test_timeout_kills_container` all passed |

No orphaned requirements: all four IDs claimed in plan frontmatter match REQUIREMENTS.md Phase 2 assignments. REQUIREMENTS.md still shows `[ ]` for ORCH-02/03 and SBX-01 — that status update is orchestrator-owned and does not reflect the implementation state.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `pyproject.toml` | agents extra | `langgraph-checkpoint-*~=3.1` pins resolve to `>=3.1,<4` but validated runtime is `4.1.1` (`langgraph-checkpoint` core 4.1.1) | WARNING | A clean `pip install .[agents]` cannot reproduce the tested stack. API surface (`PostgresSaver.setup()`, `SqliteSaver`, `Command(resume=...)`) may differ between 3.x and 4.x. See human-verify item 2. Documented in 02-REVIEW.md as IN-02. |
| `src/agent_mesh/worker/roster.py` + `orchestrator.py` | lines 151 / 223 | Roster size logged from two places with different messages ("roster size %d: %s" vs "roster size %d at startup") | INFO | Cosmetic duplication — no correctness impact. Documented in 02-REVIEW.md as IN-03. Not a blocker. |
| `src/agent_mesh/worker/graph.py` + `orchestrator.py` | WRITE_TRIGGERS | Substring matching (`trigger in lowered`) over-matches non-mutating prompts; heuristic duplicated across three sites | INFO | Fail-safe direction (extra approval gates, not skipped gates). Tracked in `deferred-items.md` as WR-03. Not a blocker. |

No `TBD`, `FIXME`, or `XXX` debt markers found in any phase-2 source or test file. No `InMemorySaver` references in source or phase tests. No `langsmith`, `LANGCHAIN_TRACING_V2`, or `LANGSMITH_API_KEY` in any phase-2 source file.

---

### Human Verification Required

#### 1. Postgres Durable Restart Test

**Test:** With a real Postgres instance available, run:
```
TEST_DATABASE_URL=<postgres-dsn> PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_checkpointer_resume.py::test_resume_after_restart_postgres -v
```

**Expected:** Test exits 0. The test simulates a process restart by closing the cached `PostgresSaver`, reopening a fresh one on the same DSN, dispatching `Command(resume=True)` on the same `thread_id`, and asserting the graph reaches terminal (no `__interrupt__` in the resumed state, `review` field populated from the preserved checkpoint).

**Why human:** No local Postgres is available in this verification environment. `test_resume_after_restart_postgres` was skipped (DSN-gated). The SQLite-file restart-sim proves the durable-resume mechanism end-to-end, but the Postgres storage binding (`PostgresSaver.from_conn_string`, `.setup()`, cache/close lifecycle in `_select_checkpointer`) was not observed executing. Criterion 2 specifically requires Postgres durability.

#### 2. Checkpoint-Backend Pin Version Reconciliation

**Test:** Run a clean `pip install -e .[agents]` in a fresh virtualenv and confirm:
1. `langgraph-checkpoint-sqlite` and `langgraph-checkpoint-postgres` resolve to versions whose API surface (`SqliteSaver`, `PostgresSaver.from_conn_string`, `PostgresSaver.setup()`, `Command(resume=...)`) matches what the tests use.
2. Either confirm `~=3.1` resolves correctly, or update the pin to `~=4.1` to match the 4.1.1 runtime the tests were validated against.

**Expected:** `pip install` succeeds, the checkpoint backends import, and the `test_checkpointer_resume.py` suite runs (agents-gated + DSN-gated) with the cleanly-installed versions.

**Why human:** IN-02 from 02-REVIEW.md: `pyproject.toml` pins `~=3.1` (`>=3.1,<4`) but the installed runtime used during execution was 4.1.1. The pin and the tested version are different major versions of the checkpoint API — a clean install from the manifest may produce a different API surface than the one that was validated. This is a non-trivial deploy-readiness concern for ORCH-02/ORCH-03.

---

### Gaps Summary

No BLOCKER gaps found. All four success criteria are met by real implementation, and the full test suite runs clean (90 passed, 6 skipped — all skips are DSN-gated or agents-stack-gated by design). The two human-verification items are:

1. **Postgres restart proof** — the durable-resume mechanism is fully implemented and proven via SQLite-file simulation, but the Postgres storage path has not been execution-verified (no local DSN). This is the same gating pattern accepted for DUR-01 in Phase 1.

2. **Pin version reconciliation** — the checkpoint-backend pins in `pyproject.toml` (`~=3.1`) diverge from the validated runtime (4.1.1). A deploy-readiness check should confirm the pinned version produces a compatible API or update the pin.

Neither item indicates a defect in the orchestration logic, security invariants, or sandbox hardening. All four phase requirements (ORCH-01, ORCH-02, ORCH-03, SBX-01) are code-complete and test-covered within the environment constraints of this verification.

---

_Verified: 2026-06-06T09:20:00+10:00_
_Verifier: Claude (gsd-verifier)_
