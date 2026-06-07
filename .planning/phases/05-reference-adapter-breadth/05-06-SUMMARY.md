---
phase: 05-reference-adapter-breadth
plan: 06
subsystem: tool-gateway
tags: [beehiiv, direct_api, httpx, publishing, approval-gated, tool-adapter]

# Dependency graph
requires:
  - phase: 04-tool-gateway
    provides: adapter registry (register/get_adapter/adapter_key_for), one-dispatcher-per-provider invariant, httpx-core adapter idiom (nango), credential-as-arg contract (D-02), stub-on-creds-absent (D-11)
  - phase: 05-01 (foundation)
    provides: beehiiv_create_post manifest entry (publishing/approval_required), input + nested {data:{id}} output JSON schemas
provides:
  - Beehiiv direct adapter — ONE beehiiv dispatcher routing create_post by spec.name via _BEEHIIV_OPS over httpx Bearer
  - status:draft forced on every create (never auto-publishes), even when caller passes status:confirmed
  - nested {data:{id}} output mapping (quarantine-avoidance) conforming to the 05-01 output schema
  - default-lane unit tests (MockTransport body-capture + nested-output + forced-draft) and opt-in conservative live test
  - docs/credentials/beehiiv.md (key mint, Bearer header, publication_id binding, draft-only guarantee, Enterprise-tier 403 caveat)
affects: [05-07 credential-docs guard, phase-05 verifier, tool-gateway adapters]

# Tech tracking
tech-stack:
  added: []  # no new dependency — httpx is core
  patterns:
    - "direct_api publishing adapter over core httpx (no SDK), credential-driven stub fallback (no ImportError branch)"
    - "always-force a safe field (status:draft) regardless of caller input — tamper-resistant write"
    - "MockTransport body-capture test to assert the exact request payload sent to a SaaS write surface"

key-files:
  created:
    - src/agent_mesh/tools/adapters/beehiiv.py
    - tests/test_beehiiv_adapter.py
    - tests/test_beehiiv_live.py
    - docs/credentials/beehiiv.md
  modified: []

key-decisions:
  - "ONE register('beehiiv', dispatcher) routing by spec.name via _BEEHIIV_OPS even though Beehiiv has a single op this phase — preserves the one-dispatcher-per-provider shape so a future second op cannot last-wins-collide (SC-1)"
  - "Stub fallback is purely credential-driven (if credential is None: return None) — httpx is core, so NO ImportError branch (unlike HubSpot's opt-in SDK)"
  - "status is ALWAYS overridden to 'draft' in the request body — the never-auto-publish guarantee (T-05-06-01), asserted by capturing the body sent through MockTransport"
  - "Output preserves the nested {data:{id}} shape (does NOT flatten to {id}) to conform to the 05-01 output schema and avoid output_quarantine"
  - "Live lane is conservative: verifies the create CALL SHAPE + forced-draft by default; only executes a real draft create when BEEHIIV_LIVE_PUBLICATION_ID is also set, treating a 403 (Enterprise-tier gate) as a skip"

patterns-established:
  - "Publishing-write adapter: force the safe status server-side; prove it by asserting the captured request body, not just the response"
  - "Conservative live lane for an approval-gated + tier-gated mutation: shape-only by default, opt-in real call behind a second explicit env binding, 403-as-skip"

requirements-completed: [TOOL-03]

# Metrics
duration: ~10min
completed: 2026-06-07
---

# Phase 5 Plan 06: Beehiiv Direct Adapter Summary

**Beehiiv `beehiiv_create_post` direct adapter over core httpx Bearer — ONE dispatcher, always `status:"draft"` (never auto-publishes), mapping the real nested `{data:{id}}` 201 body so a live create does not output_quarantine; degrades to the gateway stub without `BEEHIIV_API_KEY`.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-06-07T00:05Z
- **Completed:** 2026-06-07T00:15Z
- **Tasks:** 1
- **Files created:** 4

## Accomplishments
- Registered EXACTLY ONE `beehiiv` dispatcher (`register("beehiiv", beehiiv_adapter)`) routing `beehiiv_create_post` by `spec.name` via `_BEEHIIV_OPS` — the one-dispatcher-per-provider shape preserved for future ops.
- The create ALWAYS forces `status:"draft"` in the outgoing body, overriding any caller-supplied status (including `"confirmed"`) — the never-auto-publish guarantee, proven by capturing the MockTransport request body.
- Mapped the real HTTP 201 body to the NESTED `{"data": {"id": ...}}` output (not a flat `{id}`), conforming to `schemas/beehiiv_create_post.output.schema.json` — the canonical quarantine-avoidance case.
- Credential-driven stub fallback (`if credential is None: return None`) with no SDK and no ImportError branch — `make test` stays green and creds-free.
- Adapter reads no `os.getenv`; the API key arrives only via the `credential` arg and is never logged/returned (T-05-06-03).
- Shipped `docs/credentials/beehiiv.md` with the key-mint steps, `Authorization: Bearer` header, `publication_id` binding, draft-only guarantee, and the Enterprise-tier 403 caveat.

## Task Commits

Each task was committed atomically:

1. **Task 1: Beehiiv dispatcher (approval-gated draft create_post) over httpx Bearer + default & live tests + doc** - `07b0b99` (feat)

**Plan metadata:** SUMMARY committed separately (docs: complete plan)

## Files Created/Modified
- `src/agent_mesh/tools/adapters/beehiiv.py` - Beehiiv direct adapter: ONE `beehiiv` dispatcher, `_create_post` over httpx Bearer, `status:"draft"` forced, nested `{data:{id}}` mapping, creds-absent -> None.
- `tests/test_beehiiv_adapter.py` - Default lane: registry isolation, creds-absent -> None, `get_adapter("beehiiv")` reachability, dispatcher-routes-by-name, and the MockTransport body-capture test asserting nested output + forced draft + URL/Bearer.
- `tests/test_beehiiv_live.py` - Opt-in live lane: `pytest.mark.live`, inline skip on `BEEHIIV_API_KEY` absence, conservative create-shape verification by default, real draft create only behind `BEEHIIV_LIVE_PUBLICATION_ID`, 403-as-skip.
- `docs/credentials/beehiiv.md` - Key mint + Bearer header + `publication_id` binding + draft-only guarantee + Enterprise-tier 403 caveat + `BEEHIIV_API_KEY`.

## Decisions Made
None beyond the plan — all key choices (single dispatcher, forced draft, nested mapping, conservative live lane) were specified in the plan and followed as written.

## Deviations from Plan

None - plan executed exactly as written. The plan's `<action>` mentioned copying an optional `blocks` field, but the 05-01 input schema declares only `subtitle` and `body_content` as optional body fields, so the adapter copies exactly those two (the plan listed `blocks` as one of several "optional" examples; honoring the actual schema is consistent with the plan intent). This is a schema-alignment detail, not a behavioral deviation.

## Issues Encountered
- The minimal worktree environment lacks several optional heavy dependencies (`opentelemetry`, `litellm`, `langfuse`, `langgraph`, `fastapi`), so 5 unrelated test modules error at collection and ~19 unrelated tests fail on `ModuleNotFoundError`. These are pre-existing environment gaps, not caused by this plan (which adds only new files and touches no shared code). The adapter/tool-gateway test family (51 tests incl. the new Beehiiv suite) passes; the new default suite is green and creds-free, and the live test skips cleanly without the key.

## Verification
- `PYTHONPATH=src python -m pytest -q -m "not live" tests/test_beehiiv_adapter.py` -> 4 passed.
- `PYTHONPATH=src python -m pytest -q -m live tests/test_beehiiv_live.py --co` -> collects 1; without `BEEHIIV_API_KEY` -> 1 skipped.
- Adapter/tool-gateway family (`test_beehiiv_adapter`, `test_hubspot_adapter`, `test_gws_adapter`, `test_aggregator_adapters`, `test_gateway_engine`, `test_stack_and_toolpacks`, `test_tool_call_contract`) -> 51 passed, 1 skipped.
- Acceptance greps: ONE `register(` (non-comment) == 1; `register("beehiiv"` == 1; `beehiiv_create_post` x5; `draft` x7; `os.getenv|environ` reads == 0; doc `enterprise|draft` x7.

## User Setup Required
**External service requires manual configuration for the live lane only.** See [docs/credentials/beehiiv.md](../../../docs/credentials/beehiiv.md):
- `BEEHIIV_API_KEY` (mint in Beehiiv -> Settings -> Integrations -> API).
- `publication_id` resource binding in the tool-pack manifest.
- Optional `BEEHIIV_LIVE_PUBLICATION_ID` to opt into a real draft create.
- Note: `create-post` is Enterprise-tier-gated; a non-Enterprise key may 403 (live lane skips on 403). The default lane needs no key.

## Next Phase Readiness
- Beehiiv adapter ships behind the same Tool Gateway contract as the other reference adapters; the publishing-write integration style is proven end-to-end in the default lane with the nested-output quarantine case covered.
- No blockers. The credential doc satisfies the 05-07 credential-docs guard's expectation of `docs/credentials/beehiiv.md` with the Enterprise-tier + draft notes.

## Self-Check: PASSED
- Files: all 4 created files present on disk (beehiiv.py, test_beehiiv_adapter.py, test_beehiiv_live.py, docs/credentials/beehiiv.md).
- Commit: `07b0b99` present in git log.

---
*Phase: 05-reference-adapter-breadth*
*Completed: 2026-06-07*
