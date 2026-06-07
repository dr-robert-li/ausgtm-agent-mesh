---
phase: 05-reference-adapter-breadth
plan: 05
subsystem: tool-gateway
tags: [clockify, direct_api, httpx, X-Api-Key, adapter, tool-pack, read-only]

# Dependency graph
requires:
  - phase: 05-reference-adapter-breadth (05-01)
    provides: clockify_read_time_entries manifest entry (workspace_id+user_id bindings, CLOCKIFY_API_KEY secret) + input/output JSON schemas
  - phase: 04 (04-03)
    provides: adapter-dispatch registry (register/get_adapter/adapter_key_for), one-dispatcher-per-provider invariant, D-11 stub-on-miss seam
provides:
  - Clockify direct adapter — ONE clockify dispatcher routing clockify_read_time_entries by spec.name over core httpx with X-Api-Key
  - two-segment /workspaces/{ws}/user/{usr}/time-entries read mapped into output-schema {entries:[...]}
  - default-lane unit test (fake httpx; path/header/schema assertions) + opt-in live lane + credential doc
affects: [05-07 (credential-docs guard / README adapter matrix), tool-gateway, e2e]

# Tech tracking
tech-stack:
  added: []  # core httpx only — no new dependency, no SDK, no opt-in extra
  patterns:
    - "direct_api read-only adapter over CORE httpx (no SDK, no ImportError degrade branch — only credential-None -> stub)"
    - "two-segment resource-binding path key (workspace_id + user_id) for a direct adapter"
    - "X-Api-Key header auth (NOT Bearer) — header-form auth distinct from the HubSpot/GWS bearer/SDK adapters"

key-files:
  created:
    - src/agent_mesh/tools/adapters/clockify.py
    - tests/test_clockify_adapter.py
    - tests/test_clockify_live.py
    - docs/credentials/clockify.md
  modified: []

key-decisions:
  - "httpx core dep -> NO ImportError degrade branch (contrast HubSpot's opt-in SDK extra); the only stub path is credential is None (D-11)"
  - "Single op this phase but the _CLOCKIFY_OPS dispatcher+map shape is preserved so a future second op slots in without a register-per-op last-wins collision (SC-1)"
  - "Default-lane HTTP faking via monkeypatching clockify.httpx.get with a capturing fake (no MockTransport precedent in the suite) — captures url/headers/params for the path+header assertions"

patterns-established:
  - "Pattern: core-httpx direct read adapter — credential-only degrade, header-auth, resource-binding path segments"
  - "Pattern: capturing-fake httpx.get monkeypatch for default-lane URL/header/schema assertions"

requirements-completed: [TOOL-03]

# Metrics
duration: 12min
completed: 2026-06-07
---

# Phase 5 Plan 05: Clockify Direct Adapter Summary

**Clockify `clockify_read_time_entries` read-only adapter — ONE clockify dispatcher over core httpx with X-Api-Key auth, building the two-segment `/workspaces/{ws}/user/{usr}/time-entries` path and mapping Clockify's bare array into the output-schema `{entries:[...]}`; degrades to the stub without the key.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 1
- **Files created:** 4
- **Files modified:** 0 (no shared-file edits — manifest/schemas/registry untouched, per 05-01 ownership)

## Accomplishments
- `clockify.py`: ONE `register("clockify", clockify_adapter)` routing `clockify_read_time_entries` by `spec.name` via `_CLOCKIFY_OPS`.
- Read calls Clockify API v1 over core `httpx` with the `X-Api-Key` header (NOT Bearer); resolves `workspace_id`+`user_id` from `spec.resource_bindings` to build the required two-segment path.
- Maps Clockify's bare JSON array into the OBJECT shape `{"entries":[...]}` (matches `schemas/clockify_read_time_entries.output.schema.json`; never a bare list — keeps the live-lane `result.get("stub")` assertion safe).
- `credential is None -> None` so the engine degrades to the deterministic stub (D-11); no `os.getenv` (key arrives via `credential`, D-02).
- Default-lane test (fake `httpx.get`) asserts the output-schema conformance, BOTH path segments in the URL, and the `X-Api-Key` header (no `Authorization`). Opt-in live lane skips cleanly without the key. Credential doc covers the key mint, `X-Api-Key` header, `workspace_id`/`user_id` bindings, the subdomain-key caveat, `CLOCKIFY_API_KEY`, and the placeholder-binding live caveat.

## Task Commits

1. **Task 1: Clockify dispatcher (read_time_entries) over httpx X-Api-Key + default & live tests + doc** — `1af9311` (feat)

## Files Created/Modified
- `src/agent_mesh/tools/adapters/clockify.py` - Clockify direct adapter: one dispatcher, httpx X-Api-Key read, two-segment path, output-schema wrap, credential-None stub.
- `tests/test_clockify_adapter.py` - Default-lane: registry isolation, creds-absent->None, fake-httpx mapping (schema + both path segments + X-Api-Key header), get_adapter reachability, unknown-spec.name KeyError guard.
- `tests/test_clockify_live.py` - Opt-in live lane: `pytest.mark.live`, inline skip on `CLOCKIFY_API_KEY` absence, one real read through `gateway.execute`, non-stub + output-schema assertion.
- `docs/credentials/clockify.md` - API-key mint, `X-Api-Key` header, `workspace_id`/`user_id` bindings (+ how to resolve them), subdomain-key caveat, `CLOCKIFY_API_KEY`, placeholder-binding live operator note.

## Decisions Made
- httpx is a core dep, so the adapter has NO lazy-`ImportError` degrade branch (the plan/interfaces explicitly forbid one) — the single stub path is `credential is None`.
- Kept the `_CLOCKIFY_OPS` dispatcher+map shape despite a single op (05-01 froze Clockify read-only), so a future second op never collides via register-per-op (SC-1).
- Faked the HTTP call by monkeypatching `clockify.httpx.get` with a capturing fake (no `MockTransport` precedent existed in the suite); this captures url/headers/params for the path+header assertions while staying creds-free.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None for the plan's own files. The full `pytest -m "not live"` suite shows 20 failures + 5 collection errors in UNRELATED files (`test_tool_span.py`, `test_model_gateway_router.py`, `test_orchestration_graph.py`, `test_sandbox.py`, etc.) — all caused by optional dependencies absent in this minimal worktree environment (`opentelemetry`, `langfuse`, `litellm`, `deepagents` are declared in the `runtime`/`agents` extras and are not installed here). These are pre-existing and OUT OF SCOPE (SCOPE BOUNDARY): the Clockify adapter depends only on core `httpx` (present) and uses `jsonschema` in tests (present). The full Clockify + sibling-adapter cohort (`test_clockify_adapter.py`, `test_hubspot_adapter.py`, `test_gws_adapter.py`, `test_aggregator_adapters.py`) passes (26 passed, 1 skipped), and all plan acceptance-criteria grep checks pass.

## User Setup Required
**External service requires manual configuration for the live lane.** Mint a Clockify API key (Profile Settings -> API -> Generate; subdomain workspaces need a subdomain-specific key), export `CLOCKIFY_API_KEY`, and set REAL `workspace_id`/`user_id` `resource_bindings` in the manifest (placeholder bindings error the live call rather than skipping it). See [docs/credentials/clockify.md](../../../docs/credentials/clockify.md). The default suite stays green and creds-free.

## Next Phase Readiness
- Clockify direct_api read adapter complete; proves the direct-api style on a read-only provider with a two-segment (workspace+user) path key.
- 05-07 (credential-docs guard / README adapter matrix) can now count `docs/credentials/clockify.md` and the `clockify` adapter among the Phase-5 direct adapters.

## Self-Check: PASSED

- FOUND: src/agent_mesh/tools/adapters/clockify.py
- FOUND: tests/test_clockify_adapter.py
- FOUND: tests/test_clockify_live.py
- FOUND: docs/credentials/clockify.md
- FOUND commit: 1af9311 (feat 05-05 Clockify adapter)

---
*Phase: 05-reference-adapter-breadth*
*Completed: 2026-06-07*
