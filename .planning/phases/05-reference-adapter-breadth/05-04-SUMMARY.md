---
phase: 05-reference-adapter-breadth
plan: 04
subsystem: tool-gateway
tags: [calcom, direct_api, httpx, scheduling, adapter, cal-api-version]

# Dependency graph
requires:
  - phase: 05-01
    provides: calcom manifest entries (provider/op names/category/bindings) + calcom_list_bookings/create_booking output JSON schemas
  - phase: 04-03
    provides: adapter dispatch registry (register/get_adapter/adapter_key_for) + adapter call contract adapter(spec, params, *, credential)
  - phase: 04-05
    provides: hubspot single-dispatcher template (_HS_OPS, ONE register, creds-absent->None, default+live lane structure)
provides:
  - Cal.com direct adapter (TOOL-03) — ONE calcom dispatcher routing calcom_list_bookings (read) + calcom_create_booking (approval-gated write) by spec.name over core httpx
  - mandatory dated cal-api-version 2026-05-01 header sent on BOTH ops + Bearer auth
  - default-lane unit tests (creds-absent, routing collision guard, header-on-both-ops, read+write output-schema conformance) + opt-in live lane + credential doc
affects: [05-07, e2e-tool-gateway, reference-adapter-breadth]

# Tech tracking
tech-stack:
  added: []  # no new dependency — uses CORE httpx (no Cal.com SDK exists/needed)
  patterns:
    - "direct_api multi-op single-dispatcher over httpx with a mandatory dated provider header (cal-api-version)"
    - "write output-quarantine guard: the create response shape is validated in the default lane (the live lane never runs the approval-gated write)"

key-files:
  created:
    - src/agent_mesh/tools/adapters/calcom.py
    - tests/test_calcom_adapter.py
    - tests/test_calcom_live.py
    - docs/credentials/calcom.md
  modified: []

key-decisions:
  - "httpx.request monkeypatch (not httpx.MockTransport) for header capture — the adapter uses a local `import httpx`, so monkeypatching httpx.request on the same module object captures the headers both ops send with no Client injection point"
  - "Both ops pin cal-api-version as module constant _CAL_API_VERSION = 2026-05-01 via a shared _headers() builder — a missing/wrong version 400s every call (T-05-04-03)"
  - "event_type_id read from spec.resource_bindings (manifest binding), never os.getenv — keeps the adapter env-read-free; the live read needs no event_type_id so it skips cleanly on a placeholder binding"
  - "create_booking response shape validated against calcom_create_booking.output.schema.json in the DEFAULT lane (the write output-quarantine guard) since the live lane only exercises the read"

patterns-established:
  - "Cal.com is the canonical multi-op direct provider with a natural read+write pair — _CALCOM_OPS single-dispatcher map is the exact collision-guard shape (Pitfall 3)"

requirements-completed: [TOOL-03]

# Metrics
duration: 18min
completed: 2026-06-07
---

# Phase 5 Plan 04: Cal.com direct adapter (TOOL-03) Summary

**Cal.com direct adapter — ONE `calcom` dispatcher routing `calcom_list_bookings` (read) + `calcom_create_booking` (approval-gated write) by `spec.name` over core httpx, sending the mandatory dated `cal-api-version: 2026-05-01` header on every call and degrading to the stub without `CALCOM_API_KEY`.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-06-07
- **Completed:** 2026-06-07
- **Tasks:** 1
- **Files modified:** 4 (all created)

## Accomplishments
- Single `register("calcom", calcom_adapter)` dispatching `_CALCOM_OPS = {calcom_list_bookings, calcom_create_booking}` by `spec.name` — the canonical multi-op collision guard (no register-per-op last-wins).
- Both ops call Cal.com API v2 (`GET`/`POST https://api.cal.com/v2/bookings`) over core httpx (no SDK, no new dependency) with a shared `_headers()` builder emitting `Authorization: Bearer <key>` + the mandatory dated `cal-api-version: 2026-05-01`.
- Credential-driven stub fallback (`credential is None -> None`); no ImportError branch since httpx is core.
- `event_type_id` for the write comes from `spec.resource_bindings`; the adapter reads no environment variable; `create_booking` performs no self-gating (approval-gated upstream, D-07).
- Default-lane tests (6, all green): creds-absent degrade, routing collision guard, **both ops send `cal-api-version: 2026-05-01`** (captured off a fake `httpx.request`), read output-schema conformance, and **write output-schema conformance** (the only place the create shape is checked this milestone).
- Opt-in live lane (`@pytest.mark.live`, inline skip without `CALCOM_API_KEY`) doing one real `calcom_list_bookings` through `gateway.execute(...)`, asserting non-stub + output-schema conformance.
- Credential doc with the API-key mint, the 400-on-wrong-version gotcha, the `event_type_id` binding, and the placeholder-binding live-lane operator note.

## Task Commits

1. **Task 1: Cal.com single dispatcher (read + approval-gated write) over httpx with cal-api-version + default & live tests + doc** — `b1c7c03` (feat)

## Files Created/Modified
- `src/agent_mesh/tools/adapters/calcom.py` - Cal.com direct adapter: one `calcom` dispatcher, `_CALCOM_OPS` routing, `_headers()` with pinned `_CAL_API_VERSION`, list/create ops over httpx, creds-absent->None.
- `tests/test_calcom_adapter.py` - default lane: registry isolation, creds-absent, routing collision guard, header-on-both-ops, read + write output-schema conformance, `get_adapter("calcom")` reachability.
- `tests/test_calcom_live.py` - opt-in live lane: `pytestmark = live`, inline `CALCOM_API_KEY` skip, real list through `gateway.execute`, non-stub + schema assertion.
- `docs/credentials/calcom.md` - key mint, mandatory `cal-api-version` header + 400 gotcha, `event_type_id` binding, placeholder-binding operator note.

## Decisions Made
- See `key-decisions` frontmatter: header capture via `httpx.request` monkeypatch; version pinned as a module constant on both ops; `event_type_id` from bindings not env; write shape validated in the default lane.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The full default suite (`pytest -m "not live"`) reports 5 collection errors + 19 failures in **pre-existing, unrelated** test modules (`test_tool_span`, `test_orchestration_graph`, `test_read_path`, `test_model_gateway_router`, etc.). All are `ModuleNotFoundError` for optional heavy deps (`opentelemetry`, `langgraph`) NOT installed in this minimal lane — the documented brownfield baseline (PROJECT.md: heavy deps lazy-imported). **Verified out of scope:** moving my 4 untracked files aside and re-running gave the identical 19-failure baseline; restoring them changed the count by exactly +6 passing (170→176) with zero new failures. None of my files import those modules. Per the executor SCOPE BOUNDARY, pre-existing failures in unrelated files are not auto-fixed here.

## Verification

- `PYTHONPATH=src python -m pytest -q -m "not live" tests/test_calcom_adapter.py -x` → **6 passed**.
- `PYTHONPATH=src python -m pytest -q -m live tests/test_calcom_live.py` → **1 skipped** (no `CALCOM_API_KEY`); `--co` collects 1.
- Acceptance greps all pass: `register(` count (non-#) = 1; `register("calcom"` = 1; op-name count = 5 (>=2); `cal-api-version` in adapter = 3 (>=1); `os.(getenv|environ)(`/`os.environ[` call form = 0; `cal-api-version` in doc = 4 (>=1).
- Delta vs pristine base = +6 passing tests, 0 regressions.

## User Setup Required

**External service requires manual configuration for the live lane only.** See `docs/credentials/calcom.md`:
- `CALCOM_API_KEY` — Cal.com -> Settings -> Developer -> API Keys (key prefixed `cal_`).
- Replace the manifest `resource_bindings.event_type_id` placeholder `REPLACE_WITH_EVENT_TYPE_ID` with a real numeric event-type id before any live write.
- The default suite stays creds-free; no setup needed for `make test`.

## Threat Flags

None - the write stays category `write` -> `approval_required: true` (manifest invariant, 05-01) and is reached only after the upstream approval gate; the key is passed as `credential`, never logged/returned, and the adapter reads no env. No new trust surface beyond the manifest-declared Cal.com v2 boundary.

## Next Phase Readiness
- Cal.com adapter ready; pairs with the other wave-2 direct adapters behind the shared Tool Gateway contract. No blockers.
- 05-07 (README/credential-docs guard) can index `docs/credentials/calcom.md`.

## Self-Check: PASSED
- FOUND: src/agent_mesh/tools/adapters/calcom.py
- FOUND: tests/test_calcom_adapter.py
- FOUND: tests/test_calcom_live.py
- FOUND: docs/credentials/calcom.md
- FOUND commit: b1c7c03

---
*Phase: 05-reference-adapter-breadth*
*Completed: 2026-06-07*
