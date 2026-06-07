---
phase: 05-reference-adapter-breadth
plan: 07
subsystem: tools
tags: [xero, composio, credential-docs, drift-guard, pytest, tool-gateway]

# Dependency graph
requires:
  - phase: 05-01
    provides: manifest flip of xero_* entries to composio_aggregator (tool_slug/user_id/COMPOSIO_API_KEY); deferred shared-file edits
  - phase: 05-02..05-06
    provides: five direct adapters + their docs/credentials/<provider>.md + tests/test_<provider>_live.py (referenced by the guard lists)
  - phase: 04-08
    provides: existing composio.py adapter (registers under "composio"; verb-agnostic session.execute)
provides:
  - Xero default-lane resolution test (both flipped specs -> "composio" adapter, no new module)
  - Xero opt-in live read-only test through the gateway
  - docs/credentials/xero.md (Composio Xero-toolkit, draft-only financial write, reuses COMPOSIO_API_KEY)
  - docs/credentials/README.md credential index extended (6 new providers, 5 new env vars)
  - credential-docs drift guard extended atomically (10 live tests, 10 docs, 9 anchors, floor 12)
affects: [06-self-improvement, 07-e2e-deploy]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Aggregator-ride: a new provider (Xero) ships zero adapter code by flipping its manifest integration_style to composio_aggregator; adapter_key_for routes it to the existing composio dispatcher"
    - "Atomic drift-guard extension: hardcoded enumeration lists + derived floor extended in the SAME merge as the artifacts they reference, never reddening an intermediate merge"
    - "_NON_ENV carve-out for real-but-non-credential env reads (resource toggles) keeps the credential-completeness contract honest"

key-files:
  created:
    - tests/test_xero_live.py
    - docs/credentials/xero.md
  modified:
    - docs/credentials/README.md
    - tests/test_credential_docs.py

key-decisions:
  - "BEEHIIV_LIVE_PUBLICATION_ID excluded via _NON_ENV: it is a genuine os.getenv read but a non-secret resource toggle (real-create opt-in), not a credential to document — keeps the derived env-var floor at exactly 12"
  - "Xero rides the existing composio.py unchanged; no src/agent_mesh/tools/adapters/xero.py module exists by design"

patterns-established:
  - "Default-lane coverage for aggregator-ridden providers is proven by an adapter_key_for resolution assertion (not by a provider-specific tool), so 'coverage rides existing' is real and creds-free"

requirements-completed: [TOOL-03]

# Metrics
duration: ~15min
completed: 2026-06-07
---

# Phase 5 Plan 07: Xero-via-Composio + Credential Index + Drift-Guard Extension Summary

**Xero reads through the existing composio adapter (default-lane resolution proven, opt-in live read), and the shared credential index + drift guard are extended atomically (10 docs / 10 live tests / 9 anchors / floor 12) — default suite green and creds-free.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-06-07T00:23Z
- **Completed:** 2026-06-07T00:40Z
- **Tasks:** 2
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- Xero rides the EXISTING composio adapter with no new module: a default-lane parametrized test proves both flipped specs (`xero_read_invoices`, `xero_create_invoice`) resolve via `adapter_key_for` to `"composio"`, plus an opt-in live read-only test through the gateway.
- `docs/credentials/xero.md` documents the Composio Xero-toolkit connection, the reuse of `COMPOSIO_API_KEY` (no new env var), and the DRAFT-only / approval-gated financial-write guarantee.
- `docs/credentials/README.md` extended with 6 new per-provider matrix rows (Webflow, Bitscale, Cal.com, Clockify, Beehiiv, Xero) and 5 new env-var enumeration rows; Xero reuses `COMPOSIO_API_KEY`.
- The credential-docs drift guard extended atomically: `_LIVE_TEST_FILES` 4→10, `_PROVIDER_DOCS` 4→10, `_ANCHOR_ENV_VARS` 4→9, `_MIN_ENV_VARS` 7→12 — all five assertions (incl. the non-vacuity self-test) pass on this merge.

## Task Commits

Each task was committed atomically:

1. **Task 1: Xero live test (via existing composio) + default-lane resolution + xero.md** - `e1d47df` (feat)
2. **Task 2: README index update + credential-docs guard extension** - `b0e928e` (feat)

**Plan metadata:** (this commit) (docs: complete plan)

## Files Created/Modified
- `tests/test_xero_live.py` - default-lane resolution assertions (both specs → "composio", no module) + opt-in live read-only test; only env literal is `COMPOSIO_API_KEY`
- `docs/credentials/xero.md` - Composio Xero-toolkit connection, reuses `COMPOSIO_API_KEY`, DRAFT-only approval-gated financial write
- `docs/credentials/README.md` - 6 new matrix rows + 5 new env-var rows + extended closing doc links
- `tests/test_credential_docs.py` - 4 enumeration lists extended (4→10 / 4→10 / 4→9), floor 7→12, `_NON_ENV` carve-out + honest comment, docstrings de-hardcoded ("four" → "all")

## Decisions Made
- **`BEEHIIV_LIVE_PUBLICATION_ID` excluded via `_NON_ENV`:** the beehiiv live test reads it via `os.getenv`, so the guard's shape-scan would push the derived set to 13 and flag it undocumented. It is a non-secret resource toggle (opts the beehiiv live lane into a real create vs shape-only), not a credential — excluding it keeps the derived floor at exactly 12 and matches the guard's "every CREDENTIAL is documented" contract. Comment made explicit so the exclusion is legible (not mistaken for a shape false-positive). Advisor-confirmed as the only path to a green guard given the plan's hardcoded `_MIN_ENV_VARS = 12`.
- **Xero ships no adapter module:** it rides `composio.py` unchanged; default-lane proof is an `adapter_key_for` resolution assertion.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `_NON_ENV` carve-out for `BEEHIIV_LIVE_PUBLICATION_ID`**
- **Found during:** Task 2 (guard extension)
- **Issue:** `test_beehiiv_live.py` reads `BEEHIIV_LIVE_PUBLICATION_ID` via `os.getenv`, so the guard's shape-scan derived 13 env vars (not the planned 12) and would have flagged it undocumented — reddening the guard's own non-vacuity self-test against floor 12.
- **Fix:** Added `BEEHIIV_LIVE_PUBLICATION_ID` to `_NON_ENV` (the plan's sanctioned mechanism for exactly this case) with an honest comment distinguishing it from a shape false-positive — it is a real but non-credential resource toggle.
- **Files modified:** tests/test_credential_docs.py
- **Verification:** `pytest -m "not live" tests/test_credential_docs.py` → 5 passed; derived set is exactly 12.
- **Committed in:** b0e928e (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** The carve-out was anticipated by the plan ("if the derived scan picks up an unexpected extra literal... add it to `_NON_ENV` rather than lowering the floor"). No scope creep; the guard's credential-completeness contract is preserved and made more legible.

## Issues Encountered
None — both tasks executed as planned; the one blocking item (above) was the plan-sanctioned `_NON_ENV` path.

## User Setup Required
None new. Xero reuses the existing `COMPOSIO_API_KEY` and the Xero toolkit connection in the Composio dashboard (documented in `docs/credentials/xero.md`). Live lane stays opt-in.

## Next Phase Readiness
- Phase 5 (reference-adapter breadth, TOOL-03) is complete: all five direct adapters + Xero-via-Composio shipped with per-provider docs and an atomically-consistent drift guard enforcing doc completeness (success criterion 4).
- Default suite green and creds-free (242 passed, 6 skipped, 16 deselected via `make test`).
- Ready for Phase 6 (self-improvement, SI-01/02).

## Self-Check: PASSED

- FOUND: tests/test_xero_live.py
- FOUND: docs/credentials/xero.md
- FOUND: .planning/phases/05-reference-adapter-breadth/05-07-SUMMARY.md
- FOUND: commit e1d47df (Task 1)
- FOUND: commit b0e928e (Task 2)

---
*Phase: 05-reference-adapter-breadth*
*Completed: 2026-06-07*
