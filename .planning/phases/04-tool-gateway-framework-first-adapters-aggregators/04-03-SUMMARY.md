---
phase: 04-tool-gateway-framework-first-adapters-aggregators
plan: 03
subsystem: tool-gateway-execution-engine
tags: [tool-gateway, adapter-registry, credential-resolver, otel-span, D-02, D-03, D-10, D-11, TOOL-01, OBS-01]
requires:
  - "tools/validation.py validate_tool_input / validate_output (04-02)"
  - "ToolCall integration_style/schema_validation fields (04-01)"
  - "observability.get_tracer / trace_metadata / set_span_metadata / set_tracer_provider_override (Phase 3)"
provides:
  - "tools/credentials.py: CredentialResolver Protocol + EnvCredentialResolver (D-02)"
  - "tools/adapters/__init__.py: register / get_adapter (lazy-import-on-miss) / adapter_key_for(spec) — the parallel-adapter seam"
  - "ToolGateway.execute(call, *, resolver) real engine: resolve -> validate input -> dispatch -> validate output -> span"
  - "ToolSpec D-03 fields (integration_style, input_schema_ref, output_schema_ref)"
  - "observability.tool_event_span(...) — D-10 tool-event span (closes OBS-01)"
  - "LOCKED CONTRACT for 04-05/06/08: register under adapter_key_for-derived key (direct=provider, composio_aggregator=composio, nango_aggregator=nango); ONE dispatcher per provider key routing by spec.name; adapter signature adapter(spec, params, *, credential)->dict"
affects:
  - src/agent_mesh/tools/gateway.py
  - src/agent_mesh/tools/credentials.py
  - src/agent_mesh/tools/adapters/__init__.py
  - src/agent_mesh/observability.py
  - src/agent_mesh/worker/runner.py
  - tests/test_gateway_engine.py
  - tests/test_tool_span.py
tech-stack:
  added: []
  patterns:
    - "lazy-import-on-miss registry (importlib.import_module in get_adapter; ImportError -> None -> stub)"
    - "credential resolved only inside execute(); never returned to graph/span/log (D-02)"
    - "tool_event_span @contextmanager copies _approval_span shape (no-op when OTel absent; correlation keys only)"
    - "asymmetric validation reused from 04-02: input hard-rejects pre-dispatch, output quarantines post-call"
key-files:
  created:
    - src/agent_mesh/tools/credentials.py
    - src/agent_mesh/tools/adapters/__init__.py
    - tests/test_gateway_engine.py
    - tests/test_tool_span.py
  modified:
    - src/agent_mesh/tools/gateway.py
    - src/agent_mesh/observability.py
    - src/agent_mesh/worker/runner.py
decisions:
  - "adapter_key_for(spec) = _AGGREGATOR_KEY.get(integration_style, spec.provider) — provider keys direct dispatch (HubSpot+GWS both direct_api collide on style); aggregator name keys aggregator dispatch"
  - "get_adapter does import-on-miss so adapter modules registering at import time are loaded the first time looked up; ImportError swallowed -> None -> D-11 stub. Lazy-import probe test uses a synthetic throwaway module because real adapters land in wave 4"
  - "execute() signature changed to execute(call: ToolCall, *, resolver=None); runner._execute updated to pass `call` with NO resolver (resolver=None -> credential None -> stub) — 04-04 wires EnvCredentialResolver at that call site"
  - "validation order: input validated BEFORE the no-cred/no-adapter stub fallback, so a stub call still passes the 04-02 boundary (a direct schema-less tool is BLOCKED even on the stub path, D-04)"
  - "stub-degradation branch records call.schema_validation='ok' (input passed; no SaaS call); input violation records 'input_rejected'; output violation records 'output_quarantined'"
  - "credential-leak guard: tool_event_span sets only bounded identifiers + trace_metadata correlation keys (set_span_metadata filters); never the credential or full params/result"
requirements: [TOOL-01, TOOL-02, OBS-01]
metrics:
  duration: "~25m"
  completed: "2026-06-06"
  tasks: 2
  commits: 5
---

# Phase 4 Plan 03: Tool Gateway Execution Engine Summary

Turned `tools/gateway.py` from an echo stub into the real execution engine and —
critically for Wave-4 parallelism — established the **adapter-dispatch registry** so
HubSpot (04-05), Google Workspace (04-06), and Composio/Nango (04-08) each ship as an
additive own-file module instead of an edit to `execute()`. The engine resolves the
credential only at call time (never leaked, D-02), validates the 04-02 input/output
boundary, dispatches via `get_adapter(adapter_key_for(spec))` (or degrades to the
deterministic stub when no adapter/credential is present, D-11), and emits exactly one
OTel tool-event span (D-10, closing the OBS-01 tool-span leftover). Default suite green
and creds-free: **164 passed, 6 skipped, 4 deselected** (baseline 148; +16).

## What Was Built

### Task 1 — ToolSpec D-03 fields + CredentialResolver + lazy-import adapter registry (TDD)
- **ToolSpec D-03 fields**: added `integration_style` (default `"direct_api"`),
  `input_schema_ref`, `output_schema_ref`; `load_tool_pack` populates them via
  `raw.get(...)`. The frozen-dataclass `validate()` write-class invariant is unchanged.
- **`tools/credentials.py`**: `CredentialResolver` Protocol + `EnvCredentialResolver`
  (`os.getenv(name)`, `None` when name falsy/absent). Module docstring documents the
  D-02 hard rule (resolve only inside `execute()`, never returned), the prod
  `SecretManagerResolver` swap seam, and the `GOOGLE_WORKSPACE_OAUTH` JSON-blob shape.
- **`tools/adapters/__init__.py`**: `_REGISTRY`, `register(key, fn)`, `get_adapter(key)`
  with **lazy-import-on-miss** (`importlib.import_module(...)` wrapped in
  `try/except ImportError: return None`), `_AGGREGATOR_KEY` map, and
  `adapter_key_for(spec)`. The module docstring locks the INVARIANT
  (registration key == module filename == lookup key), the one-dispatcher-per-provider
  rule (GWS registers ONE `google_workspace` dispatcher routing by `spec.name`), and the
  adapter call contract `adapter(spec, params, *, credential) -> dict`.
- TDD: RED `3b6fb2f` (8 tests, ImportError on collection) -> GREEN `1becb78` (8 passed).

### Task 2 — Real execute(call) engine + D-10 tool-event span (TDD)
- **`ToolGateway.execute(self, call: ToolCall, *, resolver=None) -> dict`**: the engine
  flow — (1) resolve credential at call time only; (2) `validate_tool_input` (04-02) —
  `InputSchemaViolation` hard-rejects with NO adapter call and `outcome="input_rejected"`;
  (3) `get_adapter(adapter_key_for(spec))` — `None` adapter OR `None` credential returns
  the EXACT existing stub dict shape with `outcome="stub"` (D-11); (4) call
  `adapter(spec, params, credential=credential)`; (5) `validate_output` — a violation
  marks `outcome="output_quarantined"` and returns the result flagged (the SaaS call
  already ran, D-06). The whole body runs inside `tool_event_span`.
- **`observability.tool_event_span(...)`**: a `@contextmanager` copying `_approval_span`
  — no-op when `get_tracer()` is None, builds correlation via `trace_metadata()` +
  `set_span_metadata`, sets `tool/provider/category/integration_style/approval_state`
  (caller sets `outcome` on the yielded span). Never sets the credential or full payload.
- **`runner._execute`**: updated `self._gateway.execute(call.tool_name, call.parameters)`
  -> `self._gateway.execute(call)` (Rule 3 blocking fix; no resolver -> stub, creds-free).
- TDD: RED `34108cb` (8 tests, TypeError on the new signature) -> GREEN `46882f5` (16
  passed across both files).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] runner._execute call-site signature update**
- **Found during:** Task 2 (execute() signature change).
- **Issue:** Changing `execute()` from `(name, parameters)` to `(call, *, resolver)`
  breaks the sole caller `runner._execute`, which would fail the suite immediately.
- **Fix:** Updated `self._gateway.execute(call.tool_name, call.parameters)` ->
  `self._gateway.execute(call)` — the minimal green fix. No resolver is wired in
  (`resolver=None` -> credential `None` -> stub), preserving today's creds-free behavior;
  04-04 owns wiring `EnvCredentialResolver` at this call site (per the plan's interface note).
- **Files modified:** src/agent_mesh/worker/runner.py
- **Commit:** 46882f5

**2. [Rule 1 - Code quality] ruff lint fixes on new code**
- **Found during:** post-Task-2 verification (`ruff check` flagged 5 issues in the new
  code only — baseline was otherwise clean).
- **Issue:** Quoted type annotations under `from __future__ import annotations` (UP037)
  and `Callable` imported from `typing` instead of `collections.abc` (UP035).
- **Fix:** `ruff check --fix` on the two new/modified files; full suite re-run green.
- **Files modified:** src/agent_mesh/tools/gateway.py, src/agent_mesh/tools/adapters/__init__.py
- **Commit:** 46882f5

## Verification

- `PYTHONPATH=src .venv/bin/python -m pytest -q -m "not live"` -> **164 passed, 6 skipped,
  4 deselected** (baseline 148 passed; +16). Creds-free; no provider SDKs installed.
- `ruff check src/` -> All checks passed.
- Acceptance criteria (Task 1):
  - `grep -c integration_style src/agent_mesh/tools/gateway.py` = 3 (>= 2) ✓
  - `grep -c "class EnvCredentialResolver" .../credentials.py` = 1 ✓
  - `grep -cE "def register|def get_adapter|def adapter_key_for" .../adapters/__init__.py` = 3 ✓
  - `grep -c import_module .../adapters/__init__.py` = 2 (>= 1) ✓
  - `grep -cE "composio_aggregator|nango_aggregator" .../adapters/__init__.py` = 6 (>= 1) ✓
  - lazy-import-on-miss synthetic-probe test + `get_adapter("bogus") -> None` (no raise) ✓
  - `EnvCredentialResolver.resolve` returns None when unset ✓
  - ToolSpec.validate() write-class invariant unchanged (test + existing suite) ✓
- Acceptance criteria (Task 2):
  - `grep -c "def execute" gateway.py` = 1, signature takes `call: ToolCall` ✓
  - `grep -cE "adapter_key_for|get_adapter" gateway.py` = 3 (>= 1) ✓
  - `grep -c tool_event_span observability.py` = 1 (>= 1) ✓
  - credential-leak assertion: SENTINEL secret in neither returned dict nor any span
    attribute (engine + span tests) ✓
  - BOTH direct-lane and aggregator-lane specs reach a registered adapter (NOT stub),
    closing SC-1/SC-3 ✓
  - InMemorySpanExporter (via set_tracer_provider_override) asserts exactly one
    tool-event span with `integration_style` + `outcome` ✓
  - stub dict shape returned when credential/adapter absent (D-11) ✓
  - input-reject path makes NO adapter call; `schema_validation`/`outcome` = "input_rejected" (D-06) ✓

## Must-Haves Coverage (from PLAN frontmatter)

- "ToolSpec surfaces integration_style + input/output_schema_ref (D-03)" -> ToolSpec fields
  + loader; `test_load_tool_pack_surfaces_d03_fields` ✓
- "execute() resolves the credential at call time only and never returns it (D-02)" ->
  resolver called inside execute, SENTINEL never in result/span;
  `test_credential_resolved_only_in_execute_and_never_leaks` +
  `test_span_attributes_never_contain_credential_or_payload` ✓
- "credential-absent -> deterministic stub (D-11)" -> stub branch;
  `test_stub_degradation_when_credential_absent` ✓
- "adapter selected by registry keyed on adapter_key_for (provider for direct, aggregator
  name for aggregator); dispatch key == module filename" -> `adapter_key_for` +
  `get_adapter`; `test_adapter_key_for_derives_dispatch_key`,
  `test_adapter_reached_direct_lane`, `test_adapter_reached_aggregator_lane` ✓
- "each call emits one OTel tool-event span with tool/provider/category/integration_style/
  approval_state/outcome and NO raw creds/payloads (D-10, closes OBS-01)" ->
  `tool_event_span`; `test_execute_emits_exactly_one_tool_event_span` ✓

## Threat Model Coverage

- **T-04-03-01 (HIGH, Information disclosure — credential leak)** — MITIGATED + test-asserted.
  Credential resolved only inside `execute()`, never placed in the return dict or a span
  attribute (`set_span_metadata` filters to known correlation keys; tool attributes are
  bounded identifiers). `test_credential_resolved_only_in_execute_and_never_leaks` and
  `test_span_attributes_never_contain_credential_or_payload` assert the SENTINEL secret
  appears nowhere in output or span attributes. No high-severity threat left open.
- **T-04-03-02 (Tampering — malformed input -> SaaS call)** — `validate_tool_input` runs
  pre-dispatch; input violation hard-rejects with no adapter call (D-06).
- **T-04-03-03 (Spoofing — unvalidated direct tool)** — 04-02 fail-closed-direct-only is
  invoked before dispatch (a schema-less direct tool is BLOCKED even on the stub path).
- **T-04-03-04 (Repudiation — no audit trace)** — every call emits a D-10 OTel tool-event
  span correlated by tenant/task (closes OBS-01).

No new threat surface beyond the registered register: no network/auth path is added in
this plan (adapters arrive in wave 4); the engine only resolves a local env secret and
dispatches to a registered callable.

## Known Stubs

The no-credential / no-adapter fallback returns the deterministic stub dict by design
(D-11) — this is the intended creds-free default-lane behavior, not an undelivered goal.
Real adapter modules (`hubspot.py`, `google_workspace.py`, `composio.py`, `nango.py`)
land in wave 4 (04-05/06/08); the lazy-import-on-miss seam degrades cleanly to the stub
until they exist. No unintended stubs.

## Commits

- `3b6fb2f` test(04-03): add failing tests for ToolSpec D-03 fields, CredentialResolver, lazy-import adapter registry (RED)
- `1becb78` feat(04-03): ToolSpec D-03 fields + CredentialResolver + lazy-import adapter registry (GREEN)
- `34108cb` test(04-03): add failing tests for execute(call) engine + D-10 tool-event span (RED)
- `46882f5` feat(04-03): real execute(call) engine + D-10 tool-event span (GREEN)
- (this) docs(04-03): complete tool-gateway execution-engine plan

## TDD Gate Compliance

Both tasks `tdd="true"`. Task 1: RED `3b6fb2f` (8 tests failing on collection — modules
absent) precedes GREEN `1becb78` (8 passed). Task 2: RED `34108cb` (8 tests failing on the
old `execute` signature) precedes GREEN `46882f5` (16 passed). No refactor commits needed;
the ruff fixes were folded into the GREEN commit as a Rule-1 quality fix. Gate sequence
(test -> feat) present for both tasks.

## Self-Check: PASSED

- `src/agent_mesh/tools/credentials.py` exists on disk and is committed.
- `src/agent_mesh/tools/adapters/__init__.py` exists on disk and is committed.
- `tests/test_gateway_engine.py` and `tests/test_tool_span.py` exist on disk and are committed.
- Commit hashes `3b6fb2f`, `1becb78`, `34108cb`, `46882f5` all exist in git log.
- Working tree clean except the untracked `.venv` symlink (environment-only, never staged).
