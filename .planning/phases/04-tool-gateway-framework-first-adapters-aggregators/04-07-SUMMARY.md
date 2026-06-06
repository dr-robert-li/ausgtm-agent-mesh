---
phase: 04-tool-gateway-framework-first-adapters-aggregators
plan: 07
subsystem: Tool Gateway / Google Workspace direct adapter
tags: [google-workspace, calendar, docs, slides, direct-api, D-08, TOOL-01]
requires:
  - "04-06: shared _build_credentials + _service auth scaffold and the single google_workspace dispatcher"
  - "04-01: manifest entries + input/output schemas for the six new GWS tools"
  - "04-03: registry contract (one adapter per provider key, dispatch by spec.name)"
provides:
  - "Full six-product GWS direct suite (Drive/Gmail/Sheets/Calendar/Docs/Slides) reachable through the single dispatcher (D-08 satisfied)"
  - "Calendar/Docs/Slides per-product read+write scopes documented (D-12 GWS slice complete)"
affects:
  - "src/agent_mesh/tools/adapters/google_workspace.py"
  - "docs/credentials/google_workspace.md"
tech-stack:
  added: []
  patterns:
    - "Thin-op-plus-map-entry: long-tail products are added to _GWS_OPS on the shared auth scaffold, never a rearchitecture (D-01)"
    - "Nested-response-to-flat-schema mapping per read op (Calendar items[]/start objects, Docs body.content text-run tree, Slides pageElements walk)"
key-files:
  created: []
  modified:
    - "src/agent_mesh/tools/adapters/google_workspace.py (six Calendar/Docs/Slides ops added to _GWS_OPS; module docstring updated to full-suite)"
    - "docs/credentials/google_workspace.md (full six-product scope table incl. readonly scopes; consent SCOPES + enabled-APIs updated)"
    - "tests/test_gws_adapter.py (routing-no-collision guard, twelve-op registration, three nested-response mapping tests, one write-id mapping test, cred-None loop extended to all twelve)"
    - "tests/test_gws_live.py (one new live Calendar read; skips without GOOGLE_WORKSPACE_OAUTH)"
decisions:
  - "Representative ops per product: Calendar list_events(read)/create_event(write), Docs get(read)/create(write), Slides get(read)/create(write) — per RESEARCH Open Question #1"
  - "Docs/Slides create accept title only; folder placement / body content (extra Drive-move / batchUpdate calls) deferred — writes aren't in the live read lane, so minimal-correct is acceptable (documented in op docstrings)"
metrics:
  duration: "~25 min"
  completed: 2026-06-06
  tasks: 1
  files: 4
---

# Phase 04 Plan 07: Complete the Google Workspace Direct Suite (Calendar/Docs/Slides) Summary

Completed the full six-product Google Workspace direct suite (D-08 "full suite live,
not a starter subset") by adding Calendar, Docs, and Slides ops to the SAME
`google_workspace.py` from 04-06 — six thin op functions reusing the shared
`_build_credentials` + `_service` auth scaffold, added to the SAME `_GWS_OPS` dispatch
map with NO second `register()` call, so all twelve ops stay reachable through the one
google_workspace dispatcher routed by `spec.name`.

## What Was Built

- **Six new ops** in `_GWS_OPS` (TOOL-01, D-08):
  - `_calendar_list_events` (read; `calendar.readonly`; `build("calendar","v3")`; `events().list`)
  - `_calendar_create_event` (write; `calendar.events`; `events().insert`)
  - `_docs_get` (read; `documents.readonly`; `build("docs","v1")`; `documents().get`)
  - `_docs_create` (write; `documents`; `documents().create`)
  - `_slides_get` (read; `presentations.readonly`; `build("slides","v1")`; `presentations().get`)
  - `_slides_create` (write; `presentations`; `presentations().create`)
- **Response-shape mappings** (the load-bearing detail): each read flattens the nested
  Google response to its flat output schema — Calendar's `items[]` key (not `events`)
  with `start`/`end` objects flattened to `dateTime or date` strings; Docs walks
  `body.content[].paragraph.elements[].textRun.content` into the required `text` field;
  Slides walks `slides[].pageElements[].shape.text.textElements[].textRun.content` and
  maps `objectId` -> `slide_id`. Writes map the created id (`event_id`/`document_id`/
  `presentation_id`, plus `html_link` for calendar).
- **Stub fallback (D-11):** every new op returns `None` on `credential is None` before
  any creds build / SDK import.
- **Credential doc (D-12 GWS slice):** replaced the "see 04-07" placeholder with a full
  six-product scope table including the new readonly scopes; updated the Step-2 consent
  `SCOPES` list and the Step-1 enabled-APIs list so the single OAuth client covers the
  union of all six products' read+write scopes.
- **Tests:** routing regression guard (a new spec.name reaches its own op, not Drive),
  twelve-op registration assertion, three nested-response mapping tests (Calendar/Docs/
  Slides) and one write-id mapping test — each tied to its real schema file via
  `validate_output`; the cred-None guard test extended to all twelve ops; one new live
  Calendar read in the opt-in live lane.

## Dispatch Invariant Held

Exactly ONE `register("google_workspace", ...)` call (verified: `grep` count == 1 over
non-comment lines). The six new ops are entries in the existing `_GWS_OPS` map; the
single dispatcher routes the full twelve-op suite by `spec.name`. No per-op
registration (which would last-wins-collide and silently make most ops unreachable).

## Verification

- `PYTHONPATH=src .venv/bin/python -m pytest -q -m "not live"` -> **210 passed, 6
  skipped, 9 deselected** (baseline 204 passed + 6 new unit tests; 1 new live test
  deselected). Green and creds-free; module imports without the google SDK.
- `pytest -q -m live tests/test_gws_live.py` -> **2 skipped** when
  `GOOGLE_WORKSPACE_OAUTH` is unset (skips, does not error).
- Acceptance greps: `register(` count == 1; new-op-names >= 6 (7); `_build_credentials`
  count >= 7 (12); doc scope-key count >= 3 (10).
- `ruff check` on all four touched files -> clean.

## Deviations from Plan

None — plan executed exactly as written. The plan explicitly invited planner discretion
on the representative ops (RESEARCH Open Question #1); the create ops accept title-only
(folder/body deferred) which the plan's RESEARCH note flagged as acceptable for the
representative writes — documented in the op docstrings rather than silently dropping
inputs.

## Threat Flags

None. This plan adds ops on the already-mitigated 04-06 auth path; writes stay
approval-gated by the manifest + ledger (no new gating bypass); no new credential
surface (T-04-07-01/02/03 all mitigated as planned). No new network surface beyond the
Calendar/Docs/Slides API boundaries already declared in the threat model.

## Self-Check: PASSED

- `src/agent_mesh/tools/adapters/google_workspace.py` — FOUND (modified)
- `docs/credentials/google_workspace.md` — FOUND (modified)
- `tests/test_gws_adapter.py`, `tests/test_gws_live.py` — FOUND (modified)
- Commit `d08fde8` — FOUND
