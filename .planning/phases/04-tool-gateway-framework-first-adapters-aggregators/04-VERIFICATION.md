---
phase: 04-tool-gateway-framework-first-adapters-aggregators
verified: 2026-06-06T13:45:00Z
status: human_needed
score: 5/5 must-haves verified (framework-level); 2 clauses require live-lane human verification
overrides_applied: 0
human_verification:
  - test: "Run HubSpot live lane with real creds: PYTHONPATH=src .venv/bin/python -m pytest -q -m live tests/test_hubspot_live.py"
    expected: "HubSpot lookup_company returns real CRM data (not stub); no errors"
    why_human: "SC-1 requires a real direct adapter call; HUBSPOT_PRIVATE_APP_TOKEN must be set; cannot verify without real credentials"
  - test: "Run Composio live lane with real creds: PYTHONPATH=src .venv/bin/python -m pytest -q -m live tests/test_composio_live.py"
    expected: "Composio adapter executes at least one real tool call end-to-end (not stub)"
    why_human: "SC-3 requires both aggregator styles to execute a real tool call; COMPOSIO_API_KEY must be set"
  - test: "Run Nango live lane with real creds: PYTHONPATH=src .venv/bin/python -m pytest -q -m live tests/test_nango_live.py"
    expected: "Nango adapter executes one real REST proxy call via httpx (not stub)"
    why_human: "SC-3 requires both aggregator styles; NANGO_SECRET_KEY / NANGO_HOST / NANGO_CONNECTION_ID / NANGO_PROVIDER_CONFIG_KEY must be set"
---

# Phase 4: Tool Gateway Framework + First Adapters + Aggregators — Verification Report

**Phase Goal:** Deliver the Tool Gateway execution engine (credential resolution, schema validation, adapter dispatch registry, OTel span), two direct adapters (HubSpot, Google Workspace), two aggregator adapters (Composio primary, Nango fallback), and a creds-free deterministic test suite.
**Verified:** 2026-06-06T13:45:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Tool Gateway resolves credentials at execution time only; credential never returned to graph or placed in span/log | VERIFIED | `gateway.py:177` — `cred = resolver.resolve(spec.secret_name)` local only; `_stub_result()` at line 123 never includes cred; `observability.py:238` `tool_event_span()` sets tool/provider/category/approval_state/outcome — no credential attribute |
| 2 | Schema-invalid input is rejected at the gateway boundary for direct tools; aggregate tools are never blocked for missing runtime schema | VERIFIED | `validation.py` lines 102-113: `validate_tool_input()` raises `InputSchemaViolation` when `integration_style == "direct_api"` and `input_schema_ref is None`; aggregate styles with no `runtime_schema` return `None` (permissive). `test_schema_boundary.py` + `test_gateway_engine.py` prove this path. |
| 3 | Both aggregator styles (Composio and Nango) are wired end-to-end via single-key registration | VERIFIED | `composio.py`: `register("composio", composio_adapter)` at line 80 — exactly once, key "composio". `nango.py`: `register("nango", nango_adapter)` at line 124 — exactly once, key "nango". `adapters/__init__.py` `_AGGREGATOR_KEY = {"composio_aggregator": "composio", "nango_aggregator": "nango"}` routes correctly. |
| 4 | Deterministic suite runs green and creds-free; live tests skip (not error) without credentials | VERIFIED | `PYTHONPATH=src .venv/bin/python -m pytest -q -m "not live"` — 215 passed, 6 skipped, 9 deselected. `pytest -q -m live` — 9 skipped, 0 errors, 221 deselected. All live tests use pytest skip/skipif guards. |
| 5 | Per-provider credential and scope setup docs exist for all four providers | VERIFIED | `docs/credentials/README.md` (live-lane env matrix), `docs/credentials/hubspot.md`, `docs/credentials/google_workspace.md`, `docs/credentials/composio.md`, `docs/credentials/nango.md` — all 4 exist and cover required env vars. |

**Score:** 5/5 truths verified (framework-level). Live-call clauses of SC-1 and SC-3 deferred to human verification.

---

## Design Invariant Checks

All 8 invariants from phase_facts verified against source:

| # | Invariant | Status | Evidence |
|---|-----------|--------|----------|
| D-01 (D-02) | Credential resolved ONLY inside `gateway.execute()`, never returned to graph/agent | VERIFIED | `gateway.py:177` — only local binding `cred`; never in `return` dict, never passed to `_stub_result()`, never in span attributes (`test_tool_span.py:111` asserts `SENTINEL_CRED not in blob`) |
| D-02 (D-03) | `adapter_key_for(spec)`: direct→`spec.provider`; composio_aggregator→"composio"; nango_aggregator→"nango"; ONE dispatcher per key | VERIFIED | `adapters/__init__.py` `_AGGREGATOR_KEY` dict + `adapter_key_for()`. HubSpot: `register("hubspot", ...)` once at `hubspot.py:138`. GWS: `register("google_workspace", ...)` once at `google_workspace.py:423`. Composio: once at `composio.py:80`. Nango: once at `nango.py:124`. |
| D-03 (D-04/read-ungated) | Read path executes UNGATED — no approval ledger involvement | VERIFIED | `runner.py:85-103`: iterates `result.proposed_reads`, calls `self._execute(read_call)` directly. No call to `approvals.build_approval_request`, `approvals.open_approval`, or `approvals.is_approved` in that path. Write path at lines 122-161 calls all three. |
| D-04 (fail-closed) | Direct tool with no schema → BLOCKED; aggregate tool with no runtime schema → NOT blocked | VERIFIED | `validation.py:102-113`: `validate_tool_input()` — `direct_api` + None ref raises `InputSchemaViolation` (blocked). Aggregate styles + no `runtime_schema` → returns None (permissive, never raises). `test_schema_boundary.py` exercises both branches. |
| D-05 (D-11) | creds-absent → deterministic stub result; every adapter returns stub/None on cred=None | VERIFIED | `gateway.py:203-207`: `if adapter is None or cred is None: return self._stub_result(call)`. Every adapter starts with `if credential is None: return None` guard (`hubspot.py`, `google_workspace.py`, `composio.py`, `nango.py`). `test_tool_span.py:119` tests stub outcome with `resolver=_Resolver(None)`. |
| D-06 | Nango uses httpx REST proxy only — NO `nango` pip dependency | VERIFIED | `nango.py` imports: only `__future__`, `os`, `typing`, `agent_mesh.tools.adapters`. `httpx` is a core dep. `grep -ci 'import nango\|from nango' nango.py` = 0. Audit evidence in `04-08-SUMMARY.md:93-95`: "PyPI `nango` 0.1.2 CONFIRMED NOT installed — unrelated/squatted package." |
| D-07 | All GWS ops reachable via single `google_workspace` dispatcher | VERIFIED (9 ops) | `google_workspace.py` `_GWS_OPS` dict: 9 entries covering all 6 products (Drive×1, Gmail×1, Sheets×1, Calendar×2, Docs×2, Slides×2). Single registration at line 423. WARNING: module docstring says "twelve ops" and `test_all_twelve_ops_registered_in_dispatch_map` (line 260) names twelve — but the test body lists exactly 9 ops and passes. This is a documentation misnomer only; no `== 12` assertion exists. See warning below. |
| D-08 | Supply-chain package-legitimacy gates recorded as audit evidence | VERIFIED | T-04-05-SC (`hubspot-api-client>=12,<13`): `04-05-SUMMARY.md:66-70`. T-04-06-SC (`google-api-python-client`, `google-auth`, `google-auth-httplib2`): `04-06-SUMMARY.md:61-72`. T-04-08-SC (`composio>=0.13,<1`) + T-04-08-02 (nango DO-NOT-INSTALL): `04-08-SUMMARY.md:78-97`. All three SUMMARYs carry explicit operator-signed audit records. |

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/agent_mesh/tools/gateway.py` | Execution engine — cred resolution, dispatch, validation, OTel span | VERIFIED | 238+ lines; `ToolGateway.execute()` at line 166; `load_tool_pack()` at line 56; `_stub_result()` at line 123 |
| `src/agent_mesh/tools/validation.py` | JSON-Schema in/out validation boundary | VERIFIED | `Draft202012Validator` imported at module top (non-optional); `validate_tool_input()` + `validate_input()` + `validate_output()` |
| `src/agent_mesh/tools/adapters/__init__.py` | Registry with lazy-import-on-miss, `adapter_key_for()` | VERIFIED | `_REGISTRY` dict; `get_adapter()` with `importlib.import_module` fallback; `adapter_key_for()` |
| `src/agent_mesh/tools/adapters/hubspot.py` | HubSpot direct adapter (read + write ops) | VERIFIED | `_HS_OPS` with `hubspot_lookup_company` + `hubspot_create_deal`; lazy SDK import inside each op; `register("hubspot", ...)` once |
| `src/agent_mesh/tools/adapters/google_workspace.py` | GWS direct adapter (6 products, 9 ops) | VERIFIED | `_GWS_OPS` with 9 entries; single registration; lazy Google SDK imports |
| `src/agent_mesh/tools/adapters/composio.py` | Composio primary aggregator | VERIFIED | `register("composio", ...)` once; lazy `from composio import Composio` inside function; calls `aggregate_schema.fetch_runtime_schema()` |
| `src/agent_mesh/tools/adapters/nango.py` | Nango fallback aggregator (httpx REST only) | VERIFIED | `register("nango", ...)` once; no `nango` import; httpx REST proxy at `/proxy/{endpoint}` |
| `src/agent_mesh/tools/aggregate_schema.py` | Runtime schema fetcher with process cache | VERIFIED | `_SCHEMA_CACHE` dict; `fetch_runtime_schema()` for composio (duck-types session); returns None for nango/other (permissive) |
| `src/agent_mesh/tools/credentials.py` | `CredentialResolver` Protocol + `EnvCredentialResolver` | VERIFIED | Protocol + env-based impl; `SecretManagerResolver` path referenced for prod |
| `src/agent_mesh/observability.py` (tool_event_span) | OTel per-tool-call span (closes OBS-01) | VERIFIED | `tool_event_span()` at line 238; sets tool/provider/category/integration_style/approval_state/outcome + correlation keys; no-op when tracer unavailable |
| `docs/credentials/README.md` + 4 provider docs | Live-lane credential setup docs | VERIFIED | All 5 files exist; README has env var matrix |
| `tests/test_gateway_engine.py` | Gateway engine unit tests | VERIFIED | 361 lines; D-02/D-03/D-06/D-11/SC-1/SC-3 coverage |
| `tests/test_schema_boundary.py` | TOOL-02 validation boundary tests | VERIFIED | Input/output violation paths, direct vs aggregate branches |
| `tests/test_tool_span.py` | D-10 OTel span tests | VERIFIED | 3 tests: one span per execute, no cred/payload in span, stub outcome emits span |
| `tests/test_hubspot_adapter.py` | HubSpot adapter default-lane tests | VERIFIED | 183 lines; creds-free |
| `tests/test_gws_adapter.py` | GWS adapter default-lane tests | VERIFIED | 9-op dispatch map, credential-none degrades for all 9 ops |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `runner.py` proposed_reads | `gateway.execute()` | `self._execute(read_call)` at runner.py:85-103 | WIRED + UNGATED | No approval ledger call; reads bypass approval gate entirely |
| `runner.py` proposed_writes | `approvals.open_approval()` | runner.py:122-161 | WIRED | Writes go through full approval gate before execute |
| `gateway.execute()` | adapter dispatch | `adapters.get_adapter(adapter_key_for(spec))` | WIRED | Lazy import on registry miss; stub on None |
| `gateway.execute()` | OTel span | `observability.tool_event_span()` context manager | WIRED | Wraps entire execute flow; outcome attribute set on exit |
| `gateway.execute()` | credential resolver | `resolver.resolve(spec.secret_name)` | WIRED | Called once; local binding only |
| adapter registry | composio dispatch | `_AGGREGATOR_KEY["composio_aggregator"] = "composio"` | WIRED | composio_aggregator specs dispatch to "composio" key |
| adapter registry | nango dispatch | `_AGGREGATOR_KEY["nango_aggregator"] = "nango"` | WIRED | nango_aggregator specs dispatch to "nango" key |
| `composio.py` | `aggregate_schema.fetch_runtime_schema()` | called before validation | WIRED | Runtime schema fetched from Composio session for D-04 aggregate branch |

---

## Requirements Coverage

| Requirement | Plans | Description | Status | Evidence |
|-------------|-------|-------------|--------|----------|
| TOOL-01 | 04-04, 04-05, 04-06 | Tool Gateway execution engine + direct adapters | MET | gateway.py execute(); hubspot.py + google_workspace.py real SDK calls (stubbed when creds absent) |
| TOOL-02 | 04-03 | JSON-Schema in/out validation boundary | MET | validation.py; Draft202012Validator; D-04 fail-closed/permissive split |
| TOOL-04 | 04-08 | Composio primary + Nango fallback aggregators | MET | composio.py + nango.py registered; aggregate_schema.py runtime schema fetch |
| OBS-01 (leftover) | 04-09 | Per-tool-call OTel tool-event span | MET | observability.py:238 tool_event_span(); test_tool_span.py 3 tests pass |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Deterministic suite green | `PYTHONPATH=src .venv/bin/python -m pytest -q -m "not live"` | 215 passed, 6 skipped, 9 deselected | PASS |
| Live tests skip cleanly | `PYTHONPATH=src .venv/bin/python -m pytest -q -m live` | 9 skipped, 0 errors, 221 deselected | PASS |
| HubSpot real call | Requires `HUBSPOT_PRIVATE_APP_TOKEN` | Not run — no credentials | SKIP (human-needed) |
| Composio real call | Requires `COMPOSIO_API_KEY` | Not run — no credentials | SKIP (human-needed) |
| Nango real call | Requires `NANGO_SECRET_KEY` + 3 more vars | Not run — no credentials | SKIP (human-needed) |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `google_workspace.py` | 4 (docstring) | "twelve ops across six products" — only 9 exist | WARNING | Misleading documentation; no behavioral impact |
| `tests/test_gws_adapter.py` | 260-261 | Test named `test_all_twelve_ops_registered_in_dispatch_map` — checks 9 ops | WARNING | Test name will confuse future developers; no false pass (asserts correct 9 names) |

No TBD / FIXME / XXX debt markers found in phase-modified files.

---

## Human Verification Required

### 1. HubSpot Direct Adapter — Real CRM Call (SC-1)

**Test:** Set `HUBSPOT_PRIVATE_APP_TOKEN` env var, then run:
`PYTHONPATH=src .venv/bin/python -m pytest -q -m live tests/test_hubspot_live.py`

**Expected:** `hubspot_lookup_company` returns real company data from HubSpot CRM (not `{"stub": true}`); `hubspot_create_deal` creates a deal object and returns an ID.

**Why human:** SC-1 requires a real adapter call. Credentials must be present in the environment; cannot be verified without them.

### 2. Composio Primary Aggregator — Real Tool Call (SC-3)

**Test:** Set `COMPOSIO_API_KEY` env var, then run:
`PYTHONPATH=src .venv/bin/python -m pytest -q -m live tests/test_composio_live.py`

**Expected:** Composio adapter executes at least one tool call end-to-end (not stub); runtime schema is fetched from Composio SDK.

**Why human:** SC-3 requires both aggregator styles to execute a real tool call. Composio API key required.

### 3. Nango Fallback Aggregator — Real REST Proxy Call (SC-3)

**Test:** Set `NANGO_SECRET_KEY`, `NANGO_HOST`, `NANGO_CONNECTION_ID`, `NANGO_PROVIDER_CONFIG_KEY` env vars, then run:
`PYTHONPATH=src .venv/bin/python -m pytest -q -m live tests/test_nango_live.py`

**Expected:** Nango adapter issues a real httpx REST request to the Nango `/proxy/{endpoint}` route and returns non-stub result.

**Why human:** SC-3 requires Nango path exercised. All four env vars must be set.

---

## Warnings

**"Twelve ops" documentation misnomer:** `_GWS_OPS` contains 9 entries covering all 6 Google Workspace products. The module docstring (`google_workspace.py:4`), test function name (`tests/test_gws_adapter.py:260`), and the phase_facts invariant #7 all say "twelve" but mean nine. The test body asserts 9 names and passes. No `== 12` literal assertion exists anywhere. The behavioral coverage (all 6 products reachable via single dispatcher) is correct.

Recommended follow-up: correct the docstring to "nine ops across six products" and rename the test to `test_all_nine_ops_registered_in_dispatch_map`. This is cosmetic — it does not block the phase goal.

---

## Gaps Summary

No blocking gaps. All 5 roadmap success criteria are met at the framework/structural level. The two human_needed items (SC-1 real HubSpot call, SC-3 real Composio/Nango call) are external-service verifications that require live credentials — they cannot be falsified by code inspection alone, but the dispatch path, stub fallback, credential seam, and skip logic are all verified.

---

_Verified: 2026-06-06T13:45:00Z_
_Verifier: Claude (gsd-verifier)_
