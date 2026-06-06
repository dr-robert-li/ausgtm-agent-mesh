---
phase: 04-tool-gateway-framework-first-adapters-aggregators
plan: 04
subsystem: read-execution-seam
tags: [tool-gateway, read-seam, ungated-reads, worker-bootstrap, TOOL-01, audit-item-A, audit-item-B, audit-item-C]
requires:
  - "OrchestrationResult / _run_stub / _run_langgraph (worker/orchestrator.py)"
  - "MeshState / researcher_node / reviewer_node (worker/graph.py)"
  - "ToolGateway.from_manifest + execute(call, *, resolver) (04-03)"
  - "EnvCredentialResolver / CredentialResolver Protocol (04-03)"
  - "ToolCall is_read / category / schema_validation additive fields (04-01)"
provides:
  - "OrchestrationResult.proposed_reads — the executed-read seam (audit item A)"
  - "MeshState.proposed_reads + researcher_node emission (item A/C)"
  - "runner.process ungated post-run read loop (EXECUTED category=read/is_read rows, tenant-scoped, no approval ledger)"
  - "Worker.resolver (default EnvCredentialResolver) + _execute passes resolver to gateway.execute"
  - "main._build_worker injecting ToolGateway.from_manifest into both bootstrap paths (audit item B)"
affects:
  - src/agent_mesh/worker/orchestrator.py
  - src/agent_mesh/worker/graph.py
  - src/agent_mesh/worker/runner.py
  - src/agent_mesh/worker/main.py
  - tests/test_read_path.py
tech-stack:
  added: []
  patterns:
    - "ungated read loop mirrors the write-gate loop INVERTED: immediate execution, no approval ledger, before the write branch"
    - "proposed_reads is accumulated channel state (researcher node) surfaced in BOTH _run_langgraph branches — never carried in the interrupt value"
    - "evidence stays list[str]: a string summary is appended per read, never the raw result dict (T-04-04-03)"
    - "single _execute call site serves reads + writes; governance (gate vs ungated) decided by the caller, never by _execute"
    - "deterministic read uses a schema-DECLARING tool (hubspot_lookup_company) with schema-valid params so the real from_manifest path exercises validation, then stubs creds-free (D-11)"
key-files:
  created:
    - tests/test_read_path.py
  modified:
    - src/agent_mesh/worker/orchestrator.py
    - src/agent_mesh/worker/graph.py
    - src/agent_mesh/worker/runner.py
    - src/agent_mesh/worker/main.py
decisions:
  - "Deterministic read = hubspot_lookup_company {object_type: companies, query: prompt[:60] or 'context'} — DECLARES input/output schemas (D-04) and guards the empty-prompt minLength-1 case so the real validation boundary is exercised on the default lane and never input-rejects."
  - "proposed_reads pulled from final_state.get('proposed_reads', []) in BOTH _run_langgraph branches because reads are accumulated channel state (researcher runs upstream of write_gate), NOT in __interrupt__[0].value (which only carries proposed_writes). Confirmed empirically: langgraph_available() is True in this env, so run_mesh hits _run_langgraph; the researcher node populates the channel before the gate fires."
  - "Worker._resolver is SHARED by the ungated read loop and the gated write path (both go through _execute -> gateway.execute(call, resolver=self._resolver)). Creds-free by default (EnvCredentialResolver resolves every secret to None -> deterministic stub, D-11), so the write-gate suite is unaffected."
  - "Item C kept conservative: reviewer_node's write proposal is functionally IDENTICAL (still hubspot_create_deal, heuristic-derived). The plan's hard constraint is 'do NOT soften the approval path'; the real Task-1 deliverable is researcher_node emitting reads. The hardcoded write was NOT replaced with a riskier plan-derived selection that could destabilize the write-gate suite."
  - "Read evidence threaded into the write-gate approval request (build_approval_request evidence=read_evidence) so a gated write carries the read context — but only as STRING summaries, never the raw dict."
requirements: [TOOL-01]
metrics:
  duration: "~40m"
  completed: "2026-06-06"
  tasks: 2
  commits: 4
---

# Phase 4 Plan 04: Read-Execution Seam Summary

Closed audit item A — the plan-shaping gap: until now there was **no executed-read
path**. `OrchestrationResult` carried only `proposed_writes` + `evidence`, and
`runner.py` executed only writes after approval. HubSpot lookup, Drive search, and
both aggregator reads are READS, so TOOL-01/TOOL-04 could not run end-to-end without
this seam. Added `proposed_reads` across `worker/` (orchestrator dataclass + both
`_run_langgraph` branches, `MeshState` + `researcher_node`), an **ungated post-run
read loop** in the runner that records `category=read` / `is_read=True` EXECUTED
ToolCalls and feeds string evidence **without ever touching the approval ledger**, and
wired the live worker bootstrap with a real `ToolGateway.from_manifest(...)` + resolver
(audit item B). Default suite green and creds-free: **182 passed, 6 skipped, 4 deselected**
(baseline 165; +17).

## What Was Built

### Task 1 — proposed_reads on OrchestrationResult + graph emission (items A/C) (TDD)
- **`OrchestrationResult.proposed_reads`** (orchestrator.py): additive `list[dict]`
  field, same `{tool_name, category, parameters}` shape as `proposed_writes`, default
  `[]` so every other terminal path stays read-free.
- **`_run_stub`**: after the write heuristic, emits a deterministic
  `hubspot_lookup_company` read (`object_type=companies`, `query=prompt[:60] or "context"`)
  — a schema-DECLARING tool so the read path runs through the 04-02 validation boundary
  on the default lane.
- **`_run_langgraph`**: surfaces `proposed_reads` from `final_state.get("proposed_reads", [])`
  in BOTH the interrupt and no-interrupt branches (the RESEARCH wrinkle): reads are
  accumulated channel state from the researcher node, NOT in `__interrupt__[0].value`
  (which only carries `proposed_writes`), so a write that pauses the run never drops the
  reads gathered before the gate.
- **`MeshState.proposed_reads`** (graph.py) + **`researcher_node`** emits a heuristic
  `_proposed_reads(prompt)` (kept in lockstep with `_run_stub`) while retaining its
  role-distinct `research` output. **Item C:** `reviewer_node`'s write proposal is
  unchanged (still heuristic-derived `hubspot_create_deal`) — the approval path was NOT
  softened.
- TDD: RED `34740a4` (8 tests, 6 failing on the proposed_reads gap) -> GREEN `93ccc67`
  (8 passed).

### Task 2 — Ungated post-run read loop + execute(call, resolver) + gateway injection (items A/B) (TDD)
- **`runner.process` ungated read loop**: after `run_mesh` + the governed-halt re-check,
  BEFORE the write-gate branch, iterates `result.proposed_reads`, builds
  `ToolCall(category=ToolCategory.READ, approval_required=False, is_read=True,
  status=EXECUTED, ...)`, calls `self._execute(call)` IMMEDIATELY and UNGATED, persists
  tenant-scoped via `upsert_tool_call`, and appends a STRING summary
  (`f"read {tool}: {n} field(s)"`) to a local `read_evidence` list. The loop references
  **NO** `approvals.*` primitive (verified by source inspection).
- **`build_approval_request(..., evidence=read_evidence)`**: the gated write now carries
  the read context as string summaries (never the raw dict, T-04-04-03).
- **`Worker.resolver`**: new ctor arg defaulting to `EnvCredentialResolver()`; `_execute`
  now calls `self._gateway.execute(call, resolver=self._resolver)` (the 04-03 signature),
  with the `gateway is None -> stub` fallback intact (D-11). The resolver is shared by
  reads and writes — creds-free by default, so the write-gate suite is unaffected.
- **`main._build_worker`**: both `_run_pubsub` and `_run_inprocess` now construct
  `Worker(tool_gateway=ToolGateway.from_manifest(TOOL_PACK_MANIFEST))` (audit item B) —
  the worker boots with a real manifest-loaded gateway instead of `tool_gateway=None`.
- TDD: RED `1f03a1d` (8 new tests failing on the missing read loop / resolver / injection)
  -> GREEN `25b568c` (17 passed across both tasks).

## Deviations from Plan

None — plan executed exactly as written. Item C was kept conservative per the plan's
explicit constraint ("do NOT soften the approval path"): `reviewer_node`'s write
proposal stays functionally identical rather than being swapped for a riskier
plan-derived selection.

## Verification

- `PYTHONPATH=src .venv/bin/python -m pytest -q -m "not live"` -> **182 passed, 6 skipped,
  4 deselected** (baseline 165; +17). Creds-free; no provider SDKs installed.
- `ruff check src/ tests/test_read_path.py` -> All checks passed.
- **Security (T-04-04-01, headline):** source inspection asserts the read loop references
  none of `approvals.is_approved` / `build_approval_request` / `open_approval` /
  `approvals.`; a runtime spy test (`test_read_path_never_opens_an_approval`) monkeypatches
  all three approval primitives and asserts NONE is called for a read-only task.
- Acceptance criteria (Task 1):
  - `grep -c proposed_reads orchestrator.py` = 5 (>= 3: dataclass + _run_stub + both branches) ✓
  - `grep -c proposed_reads graph.py` = 7 (>= 2: MeshState + researcher_node) ✓
  - `test_run_stub_emits_a_schema_declaring_read` asserts a schema-declaring read tool ✓
  - `test_run_stub_read_params_are_schema_valid` validates params against the manifest schema ✓
  - existing write-gate / approval tests still pass (item C not softened) ✓
- Acceptance criteria (Task 2):
  - `grep -c proposed_reads runner.py` = 2 (>= 1); loop builds ToolCategory.READ / is_read=True ✓
  - `grep -c from_manifest main.py` = 1 (both ctor sites via `_build_worker`) ✓
  - no-approval security test for a read (spy) ✓
  - `runner._execute` calls `gateway.execute(call, resolver=...)`, stub fallback intact ✓
  - write-gate suite (AWAITING_APPROVAL + approval opened) still passes ✓
  - full default suite exits 0 ✓

## Must-Haves Coverage (from PLAN frontmatter)

- "Proposed reads execute UNGATED immediately post-run, recording category=read ToolCalls
  and feeding evidence (item A)" -> read loop;
  `test_read_executes_ungated_and_records_executed_row` ✓
- "The read path NEVER routes through approvals.is_approved() (security invariant)" ->
  loop has no approval primitive (inspection) + spy test
  `test_read_path_never_opens_an_approval` ✓
- "Write-class proposals stay gated through the existing payload-hash ledger, unchanged
  (SEC-01/SEC-02)" -> `test_write_trigger_still_parks_and_opens_approval` + the unchanged
  existing interrupt/approval-security suites ✓
- "The worker boots with a real ToolGateway.from_manifest(...) + CredentialResolver (item B)" ->
  `main._build_worker`; `test_main_bootstrap_injects_real_manifest_gateway` +
  `test_worker_has_resolver_defaulting_to_env_resolver` ✓
- "make test stays green with the gateway-None stub fallback still recording deterministic
  read rows (D-11)" -> `test_read_executes_ungated...` (gateway=None) +
  `test_read_via_real_manifest_gateway_stubs_cleanly_creds_free` ✓

## Threat Model Coverage

- **T-04-04-01 (HIGH, Elevation of privilege — read becoming a write-without-approval hole)**
  — MITIGATED + test-asserted. The read loop builds `ToolCategory.READ` /
  `approval_required=False` only, calls `_execute` directly, and references NO approval
  primitive (source-inspection guard + runtime spy `test_read_path_never_opens_an_approval`).
  Write-class proposals continue through the unchanged payload-hash ledger (SEC-01/SEC-02
  untouched; existing interrupt/approval-security suites green). No high-severity threat
  left open.
- **T-04-04-02 (Tampering — a write smuggled into proposed_reads)** — the read loop sets
  `category=ToolCategory.READ` UNCONDITIONALLY regardless of the proposed dict; the
  reviewer keeps `proposed_writes` heuristic-derived (item C not softened), and the
  manifest write-class invariant + the gateway's own input validation remain.
- **T-04-04-03 (Information disclosure — read dicts leaking into evidence)** — evidence
  appends a STRING summary (`f"read {tool}: {n} field(s)"`), never the raw result dict;
  the gateway already excludes credentials from results (04-03).
- **T-04-04-04 (Tampering — cross-tenant read rows)** — the read ToolCall is built with
  `task.tenant_id`; `upsert_tool_call` + `list_tool_calls` are tenant-scoped (DUR-02);
  `test_read_executes_ungated...` asserts `read.tenant_id == "t"`.

## Known Stubs

The gateway-None and no-credential fallbacks return the deterministic stub dict by design
(D-11) — the intended creds-free default-lane behavior, not an undelivered goal. With a
real `from_manifest` gateway but no creds, the read still records an EXECUTED row whose
result is the stub dict and `schema_validation="ok"` (input passed; no SaaS call). Real
adapter modules land in wave 4 (04-05/06/08); the read seam degrades cleanly to the stub
until then. No unintended stubs.

## Commits

- `34740a4` test(04-04): add failing tests for proposed_reads on OrchestrationResult + graph emission (RED)
- `93ccc67` feat(04-04): proposed_reads on OrchestrationResult + researcher emission (items A/C) (GREEN)
- `1f03a1d` test(04-04): add failing tests for ungated read loop + resolver + gateway injection (RED)
- `25b568c` feat(04-04): ungated post-run read loop + execute(call,resolver) + worker gateway injection (items A/B) (GREEN)

## TDD Gate Compliance

Both tasks `tdd="true"`. Task 1: RED `34740a4` (tests added, 6 failing on the
proposed_reads gap) precedes GREEN `93ccc67` (8 passed). Task 2: RED `1f03a1d` (8 new
tests failing on the missing read loop / resolver / injection) precedes GREEN `25b568c`
(17 passed). No refactor commits needed; ruff fixes folded into GREEN. Gate sequence
(test -> feat) present for both tasks.

## Self-Check: PASSED

- `tests/test_read_path.py` exists on disk and is committed.
- `src/agent_mesh/worker/{orchestrator,graph,runner,main}.py` modified and committed.
- Commit hashes `34740a4`, `93ccc67`, `1f03a1d`, `25b568c` all exist in git log.
- Working tree clean except the untracked `.DS_Store` (environment-only, never staged).
