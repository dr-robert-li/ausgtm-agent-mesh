---
phase: 07-e2e-validation-deploy-readiness
verified: 2026-06-08T09:30:00Z
status: gaps_found
score: 3/4 must-haves verified
overrides_applied: 0
gaps:
  - truth: "MCP request triggers a long-running checkpointed mesh job that survives process restart and returns an artifact (SC-2 / E2E-02)"
    status: failed
    reason: >
      CR-01: The default-lane test (test_e2e_mcp_durable_job.py) directly invokes
      build_graph().compile(saver).invoke(...) without going through Worker.process() or
      orchestrator._run_langgraph(). It also uses thread_id = f"tenant-t::{task.task_id}"
      (tenant-prefixed, line 91) while production _graph_config() (orchestrator.py line 319)
      uses bare task.task_id. The test proves the LangGraph SqliteSaver drop-then-reopen
      checkpoint primitive works under a key that production code never writes. It does not
      prove the production durable wiring (Worker -> orchestrator._run_langgraph ->
      _select_checkpointer -> _graph_config). The Postgres lane (test_e2e_mcp_durable_job_live.py)
      does exercise _select_checkpointer/close_checkpointer but skips by default in every
      environment (no TEST_DATABASE_URL). In make test / the standard default lane, the
      production orchestrator entrypoints are never exercised for the durable resume path.
    artifacts:
      - path: "tests/e2e/test_e2e_mcp_durable_job.py"
        issue: "line 91 uses thread_id = f\"tenant-t::{task.task_id}\" — format production never produces; test invokes graph directly, bypassing Worker.process() and orchestrator._run_langgraph()"
      - path: "src/agent_mesh/worker/orchestrator.py"
        issue: "line 319: _graph_config() uses bare task.task_id, not tenant-prefixed form; never called by E2E-02 default-lane test"
    missing:
      - "A default-lane test that drives Worker.process(task_id) -> orchestrator._run_langgraph -> _graph_config on the restart-resume path, OR"
      - "Correct thread_id in test to match production _graph_config() output AND acknowledge that production durability is only proven via the Postgres lane (which skips by default)"
      - "If the intent is that production thread_id IS tenant-prefixed, update orchestrator._graph_config() to match and add a test asserting the format contract"
---

# Phase 7: E2E Validation and Deploy-Readiness Verification Report

**Phase Goal:** Assemble all layers and prove the platform end-to-end — a write-gated Slack action from evidence, an MCP-triggered long checkpointed job returning an artifact, and the failure modes — then validate that the gcloud and wrangler deployment scripts are idempotent and GCP-ready without provisioning live resources.
**Verified:** 2026-06-08T09:30:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Test Suite Run

Default lane: `PYTHONPATH=src .venv/bin/python -m pytest -q -m "not live"`

Result: **304 passed, 9 skipped, 23 deselected in 21.22s**

All 304 tests passed. The suite is green. Gaps are E2E fidelity issues (test bypasses production wiring) not suite failures.

---

## Goal Achievement

### Observable Truths / Success Criteria

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | Slack request -> write-gate pause -> token-gated approval -> completion proven through real FastAPI TestClient (E2E-01) | VERIFIED | tests/e2e/test_e2e_slack_write_gated.py — drives POST /slack/events, reads approval_token from repo, POST /v1/approvals, asserts TaskState.COMPLETED; SP-1 app_module._service rebind at line 82 prevents green-on-a-lie |
| SC-2 | MCP request triggers long durable checkpointed mesh job, artifact survives process restart (E2E-02) | FAILED (gap) | CR-01: default-lane test proves SqliteSaver checkpoint primitive in isolation under non-production thread_id key; does NOT drive Worker.process or orchestrator._graph_config; production restart-resume path never exercised in default lane |
| SC-3 | Combined failure run: model fallback + in-cascade retry-recovery + governed budget halt -> FAILED terminal (E2E-03) | VERIFIED | tests/e2e/test_e2e_failure_modes.py — Stage A proves fallback via mock_testing_fallbacks=True (resp.model == gemini-1.5-pro, not primary); Stage B pins singleton, records over-cap ledger, drives Worker.process -> FAILED with exactly one budget_halt gateway_event (provider_status=None) and leak-guard |
| SC-4 | gcloud/wrangler scripts are idempotent and GCP-ready; manifests consistent (DEP-01/DEP-02) | VERIFIED | tests/deploy/test_gcloud_idempotency.py: always-on bash -n, PATH-shim proves both EXISTS (no create) and ABSENT (create recorded) branches, Pub/Sub --max-delivery-attempts=5 asserted; tests/deploy/test_manifest_consistency.py: bidirectional env-var contract, tool-pack pointer resolution, required-stack tokens; shellcheck and wrangler both loud-skip on this runner |

**Score:** 3/4 truths verified (SC-2 is a confirmed gap per CR-01 adjudication)

---

## CR-01 Adjudication (Inline)

**Finding:** E2E-02 default-lane test does not exercise the production durable-resume path.

**Evidence:**

Production path (`orchestrator.py` lines 305-323, 357, 449):
```python
def _graph_config(task: TaskRecord) -> dict:
    config: dict = {"configurable": {"thread_id": task.task_id}}  # BARE uuid, line 319
    ...

def _run_langgraph(self, task):
    ...
    result = graph.invoke({...}, _graph_config(task))   # line 357

def resume_mesh(self, task_id):
    task = self._repo.get_task(task_id)
    result = graph.invoke(Command(resume=True), _graph_config(task))  # line 449
```

Test (`test_e2e_mcp_durable_job.py` line 91):
```python
thread_id = f"tenant-t::{task.task_id}"  # PREFIXED — production never produces this
config = {"configurable": {"thread_id": thread_id}}
graph = build_graph().compile(checkpointer=saver)
graph.invoke({"prompt": _PROMPT, "task_id": task.task_id}, config)  # direct, no Worker
```

The test docstring at lines 17-19 asserts "the resume always keys on `thread_id == the tenant-scoped task_id` (`tenant-t::` form), never a bare thread_id — that is what scopes a checkpoint to one task." This contradicts production `_graph_config()` which uses bare `task.task_id`. Either the test or the production code is wrong about the key format; this is not verified, it is asserted against a divergent implementation.

**Bypass confirmed:** The test calls `request_from_mcp -> svc.create_task()` (real MCP ingress, correct), then immediately compiles and invokes the graph directly. `Worker`, `orchestrator.run_mesh`, `_run_langgraph`, `_select_checkpointer`, and `_graph_config` are not on any call path in the default-lane test.

**Classification:** FAILED (gap). The LangGraph checkpoint primitive (SqliteSaver drop-then-reopen) is proven to function. The production wiring that uses it is not exercised in the default lane. This is an **E2E fidelity gap**, not a production correctness claim — production durability may work, but the test does not prove it.

**What the Postgres lane adds:** `test_e2e_mcp_durable_job_live.py` routes through `_select_checkpointer`/`close_checkpointer` but: (1) it is a separate "live" companion module, (2) it skips by default in every environment without TEST_DATABASE_URL, (3) the 07-02 SUMMARY explicitly states "this lane is code-parity-backed, not executed-green here." The production orchestrator path is proven by code-reading, not test execution in the default gate.

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/e2e/test_e2e_slack_write_gated.py` | SC-1 full Slack write-gate E2E | VERIFIED | 139 lines; drives real FastAPI TestClient; SP-1 rebind at line 82; reads approval token from repo metadata; asserts TaskState.COMPLETED |
| `tests/e2e/test_e2e_mcp_durable_job.py` | SC-2 MCP durable restart-resume E2E | STUB (fidelity gap) | Exists and passes; proves checkpoint primitive; does not drive production Worker/orchestrator path; thread_id mismatch with production |
| `tests/e2e/test_e2e_failure_modes.py` | SC-3 combined fallback+budget-halt E2E | VERIFIED | 174 lines; Stage A: mock_testing_fallbacks cascade; Stage B: singleton-pinned budget halt to FAILED with leak guard |
| `tests/deploy/test_gcloud_idempotency.py` | DEP-01 idempotency + syntax + Pub/Sub | VERIFIED | 284 lines; always-on bash -n; PATH-shim both-direction proofs; Pub/Sub config asserted |
| `tests/deploy/test_manifest_consistency.py` | DEP-02 manifest consistency + required-stack | VERIFIED | 250 lines; 13-var env-var contract; tool-pack pointer resolution; required-stack assertion |
| `src/agent_mesh/worker/orchestrator.py` | Production _graph_config / _select_checkpointer | EXISTS (production wiring present but not covered by default-lane E2E) | _graph_config line 319 uses bare task.task_id; both _run_langgraph and resume_mesh call it |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| POST /slack/events | Worker.process() | TestClient -> app_module._service rebind (SP-1) | WIRED | test line 82: `app_module._service = svc`; prevents TestClient's stale service reference |
| Worker.process() | TaskState.AWAITING_APPROVAL | approval_tokens in task.metadata | WIRED | test reads token from `repo._tasks[task_id].metadata["approval_tokens"]` |
| POST /v1/approvals | Worker.process() -> TaskState.COMPLETED | token match + resume | WIRED | asserts `completed_task.state == TaskState.COMPLETED.value` |
| request_from_mcp | svc.create_task() | InProcessDispatcher | WIRED | real MCP ingress path exercised |
| E2E-02 test | Worker.process / orchestrator._run_langgraph | expected but absent | NOT WIRED | test bypasses; direct build_graph().compile().invoke() only |
| build_graph + SqliteSaver | drop-then-reopen restart simulation | del graph; del saver; conn.close(); new conn2 | WIRED (primitive level) | restart simulation mechanism correct; operates under non-production thread_id |
| _graph_config(task) | thread_id key | task.task_id (bare) | WIRED in production | never invoked by E2E-02 default test; format contradicts test docstring |
| Worker.process() | budget halt -> FAILED | repo_module._SINGLETON pin + BudgetEvent | WIRED | Stage B singleton-pin pattern correct; halt proven with leak guard |
| scripts/*.sh | bash -n syntax floor | parametrize over all scripts | WIRED | always-on regardless of shellcheck/wrangler availability |
| PATH-shim | resource-detection branches | prepended shim dir in subprocess PATH | WIRED | both EXISTS and ABSENT directions proven |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| test_e2e_slack_write_gated.py | task_id, approval_token | InMemoryRepository (real, not mock) | Yes — TaskRecord created with real transitions | FLOWING |
| test_e2e_mcp_durable_job.py | paused["__interrupt__"], resumed["review"] | SqliteSaver checkpoint (file-backed sqlite) | Yes (primitive level) — checkpoint data flows; production orchestrator path not sourced | FLOWING (primitive); DISCONNECTED from production wiring |
| test_e2e_failure_modes.py Stage A | resp.choices[0], resp.model | litellm Router mock cascade | Yes — mock_response controls output deterministically | FLOWING |
| test_e2e_failure_modes.py Stage B | TaskState, gateway_events | InMemoryRepository singleton-pinned | Yes — real BudgetEvent -> budget.check -> FAILED transition | FLOWING |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full default-lane suite passes | PYTHONPATH=src .venv/bin/python -m pytest -q -m "not live" | 304 passed, 9 skipped, 23 deselected in 21.22s | PASS |
| SC-1 Slack E2E green | included in above | 1 passed (test_e2e_slack_write_gated.py) | PASS |
| SC-2 MCP durable E2E green (primitive level) | included in above | 1 passed (test_e2e_mcp_durable_job.py) | PASS (but E2E fidelity gap — see CR-01) |
| SC-3 failure modes E2E green | included in above | 1 passed (test_e2e_failure_modes.py) | PASS |
| DEP-01/DEP-02 deploy tests green | included in above | 19 passed, 2 loud-skipped (shellcheck/wrangler absent) | PASS |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| E2E-01 | 07-01 | Slack request creates write-gated SaaS action from evidence, completes after approval | SATISFIED | test_e2e_slack_write_gated.py 139 lines — full chain through TestClient; evidence layer covered cross-phase by test_read_path.py (Phase 4) in same suite |
| E2E-02 | 07-02 | MCP request triggers long checkpointed mesh job, returns artifact | BLOCKED | CR-01: default-lane test bypasses Worker/orchestrator; thread_id mismatch; production restart-resume path not exercised by default gate |
| E2E-03 | 07-03 | Failure E2E: model fallback + job retry + budget-limit halt together | SATISFIED | test_e2e_failure_modes.py: Stage A (cascade recovery) + Stage B (budget halt -> FAILED); Pub/Sub retry asserted as deploy-config in test_gcloud_idempotency.py |
| DEP-01 | 07-04 | gcloud scripts: shellcheck/lint, syntax, idempotency-branch unit tests with mocked gcloud | SATISFIED (with note) | Always-on bash -n; PATH-shim proves both directions; shellcheck LOUD-SKIP (not installed on this runner — documented, not hidden) |
| DEP-02 | 07-04 | wrangler script: lint + dry-run; manifest schema-consistency | SATISFIED (with note) | Manifest consistency: 13-var env contract + tool-pack pointer resolution + required-stack tokens all pass; wrangler LOUD-SKIP (not installed — documented, not hidden) |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| tests/e2e/test_e2e_mcp_durable_job.py | 17-19 | Docstring asserts DUR-02 contract (tenant-t:: form is correct) but production _graph_config uses bare uuid | Warning | Documents a false contract; either the test or production is wrong about the correct thread_id format |
| tests/e2e/test_e2e_mcp_durable_job.py | 91 | thread_id = f"tenant-t::{task.task_id}" — key production never produces | Blocker | Test exercises checkpoint primitive under a non-production key; checkpoint durability through production wiring is not proven |
| tests/e2e/test_e2e_mcp_durable_job.py | 99-100 | build_graph().compile(checkpointer=saver).invoke(...) — direct invocation bypasses Worker | Blocker | Production entrypoints (Worker.process, orchestrator.run_mesh, _run_langgraph, _select_checkpointer, _graph_config) not on the call path |

No TBD/FIXME/XXX/XXX markers found in phase-7 test files. No unresolved debt markers.

---

## SC-1 "From Evidence" Note

E2E-01 criterion includes "from evidence" in the full requirement text (E2E-01: "creates a write-gated SaaS action from evidence"). The E2E-01 test drives the approval flow end-to-end but the write action is gated on a stub tool call (asserts `gated_call.result.get("stub") is True` in default lane — no real provider). The evidence/retrieval step is covered cross-phase: `test_read_path.py` (Phase 4) exercises the read tool, evidence summary, and T-04-04-01 (never returns raw dict) — and it passes in the current suite. This is cross-phase delegation that was planned and documented, not a silent drop. SC-1 status remains VERIFIED.

## SC-3 Retry-Leg Note

The "job retry" leg of E2E-03 is the thinnest of the three elements. It is satisfied by two separate interpretations: (a) Stage A's litellm in-cascade recovery (primary raises, fallback serves — the cascade IS the retry-then-recover), and (b) the Pub/Sub `--max-delivery-attempts=5` + `--dead-letter-topic` deploy-config assertion in test_gcloud_idempotency.py lines 275-283. These are staged in separate fixtures, not a single mesh run. This was a documented design decision (open design decision 1, resolved in 07-03 SUMMARY) and advisor-confirmed. Calling it explicitly: the criterion is met by reinterpretation, not by a Pub/Sub redelivery simulation. Status remains VERIFIED for SC-3 as a whole, but this is the weakest element.

## SC-4 Lint/Dry-Run Note

shellcheck and wrangler both LOUD-SKIP on this runner (not installed). The always-on `bash -n` syntax floor runs on all scripts unconditionally. The idempotency-logic PATH-shim harness and manifest consistency validator exercise the real script content and deployment manifest. "Pass lint + dry-run" for shellcheck/wrangler is unexercised-here. This is acceptable per plan D-10 design (loud-skip, not silent-skip), but noted for completeness.

---

## Human Verification Required

None identified. All verification items resolved programmatically or adjudicated as gaps.

---

## Gaps Summary

One gap blocking full goal achievement:

**SC-2 (E2E-02) — Production durable-resume path not exercised in default lane.**

Root cause: E2E-02 default test proves the LangGraph SqliteSaver checkpoint primitive works (restart-resume mechanism is real and correct at the primitive level). But it does not assemble the production path: `Worker.process() -> orchestrator.run_mesh() -> _run_langgraph() -> build_graph().compile(_select_checkpointer()) -> invoke({...}, _graph_config(task))`. It also uses a thread_id key (`tenant-t::{task.task_id}`) that production `_graph_config()` never generates (production uses bare `task.task_id`).

The Postgres lane companion test (`test_e2e_mcp_durable_job_live.py`) does exercise `_select_checkpointer`/`close_checkpointer` but skips by default in all environments (no TEST_DATABASE_URL). The SUMMARY explicitly acknowledges "code-parity-backed, not executed-green here."

Three resolution paths:

1. **Correct the default-lane test** to drive `Worker.process(task_id)` through the pause, then `Worker.resume_mesh(task_id)` (or equivalent orchestrator path) for the resume leg, using the same sqlite-backed checkpointer. Requires a seam to inject the saver into `_select_checkpointer` for the default lane, or an in-process mock of the Postgres-DSN env var.

2. **Correct the thread_id** in the test to match `task.task_id` (bare) and update the docstring to acknowledge that production durability through `_graph_config` is proven by code-reading and the Postgres lane (not default-lane execution), then accept the gap as a documented coverage limitation.

3. **Update production `_graph_config()`** to produce `f"tenant-t::{task.task_id}"` (tenant-prefixed) to match the test's documented DUR-02 contract, verify this is the intended key format, and update the Postgres-lane test to use the same mechanism.

All three are valid. Option 1 closes the gap most completely for the default lane. Option 3 is most faithful if the DUR-02 docstring is normative.

---

_Verified: 2026-06-08T09:30:00Z_
_Verifier: Claude (gsd-verifier)_
