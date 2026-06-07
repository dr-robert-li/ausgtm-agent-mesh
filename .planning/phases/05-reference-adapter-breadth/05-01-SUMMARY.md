---
phase: 05-reference-adapter-breadth
plan: 01
subsystem: tool-gateway
tags: [manifest, schemas, foundation, json-schema, composio, bitscale]
requires:
  - Phase-4 Tool Gateway engine (gateway.py, validation.py, adapters/__init__.py, composio.py) — reused unchanged
provides:
  - schema-backed, op-name-exact manifest surfaces for all six Phase-5 providers (wave-2 isolation contract)
  - 18 Draft-2020-12 schema files for every Phase-5 direct op
  - Xero flipped to composio_aggregator (rides existing composio.py, no new module)
affects:
  - wave-2 per-adapter plans 05-02..05-06 (consume the frozen op-name set + schema refs)
  - wave-3 plan 05-07 (Xero live test + guard extension, deferred)
tech-stack:
  added: []   # NO new pyproject extra — all five direct providers use core httpx; Xero rides existing composio extra
  patterns:
    - "schema-satisfiable shared edits front-loaded into foundation (04-01 pattern); guard enumeration deferred to final plan"
    - "aggregate (composio) tools carry NO schema refs (D-04 permissive/runtime); direct tools carry both (D-04 fail-closed)"
key-files:
  created:
    - schemas/webflow_list_cms_items.input.schema.json
    - schemas/webflow_list_cms_items.output.schema.json
    - schemas/webflow_create_cms_item.input.schema.json
    - schemas/webflow_create_cms_item.output.schema.json
    - schemas/bitscale_list_grids.input.schema.json
    - schemas/bitscale_list_grids.output.schema.json
    - schemas/bitscale_get_workspace.input.schema.json
    - schemas/bitscale_get_workspace.output.schema.json
    - schemas/bitscale_run_grid.input.schema.json
    - schemas/bitscale_run_grid.output.schema.json
    - schemas/calcom_list_bookings.input.schema.json
    - schemas/calcom_list_bookings.output.schema.json
    - schemas/calcom_create_booking.input.schema.json
    - schemas/calcom_create_booking.output.schema.json
    - schemas/clockify_read_time_entries.input.schema.json
    - schemas/clockify_read_time_entries.output.schema.json
    - schemas/beehiiv_create_post.input.schema.json
    - schemas/beehiiv_create_post.output.schema.json
  modified:
    - manifests/tool_pack_manifest.yaml
decisions:
  - "Xero rides composio_aggregator (verb-agnostic session.execute) — zero new adapter code, nango.py untouched"
  - "Bitscale reconciled from stale bitscale_enrich to three live-verified ops (list_grids/get_workspace reads + run_grid write)"
  - "Webflow gains a read op (webflow_list_cms_items) to round out the read+write breadth"
  - "Clockify output object-wraps {entries:[...]} instead of a bare array so result.get('stub') stays safe in every lane"
metrics:
  duration: ~25 min
  completed: 2026-06-07
  tasks: 2
  files: 19
---

# Phase 5 Plan 01: Reference-Adapter Foundation Summary

Front-loaded ALL Phase-5 shared-file edits into one foundation plan so wave-2 per-adapter
plans are genuinely isolated: reconciled `manifests/tool_pack_manifest.yaml` (bitscale real
ops, webflow read op, Xero→Composio flip, schema refs on every direct entry) and authored 18
Draft-2020-12 schema files whose output shapes mirror the real provider responses — default
suite green and creds-free, no new dependency, guard untouched.

## What Was Built

### Task 1 — Manifest reconcile (`manifests/tool_pack_manifest.yaml`, commit `a0df2b0`)
- **Bitscale:** replaced the stale single `bitscale_enrich` entry with the three frozen
  live-verified ops — `bitscale_list_grids` (read), `bitscale_get_workspace` (read),
  `bitscale_run_grid` (write, `approval_required: true`). `grid_id` resource binding on
  list_grids + run_grid.
- **Webflow:** added the `webflow_list_cms_items` read op; both webflow entries gained
  `input_schema_ref` + `output_schema_ref`.
- **Xero flip:** both `xero_read_invoices` / `xero_create_invoice` changed from
  `nango_aggregator` → `composio_aggregator`, `credential_secret_name: COMPOSIO_API_KEY`,
  `resource_bindings.tool_slug` (`XERO_LIST_INVOICES` / `XERO_CREATE_INVOICE`) + `user_id`.
  No schema refs (D-04 aggregate = permissive/runtime). `xero_create_invoice` keeps
  `approval_required: true` (financial). Xero now rides the existing `composio.py` — no new
  module, no `nango.py` edit.
- **Cal.com / Clockify / Beehiiv:** added both schema refs to every direct entry. Clockify
  read also gained a `user_id` binding (its read needs workspaceId + userId).

### Task 2 — 18 schema files (commit `c4f6e5a`)
All Draft 2020-12, copying the `hubspot_lookup_company` template (`$schema`, `title`,
`x-tool-category`, `x-approval-required`). Inputs permissive-by-design (D-05); writes tighten
the cost/security-critical field (`grid_id`, `start`, `title`). Output schemas mirror the REAL
provider responses to avoid `output_quarantine`:
- Beehiiv: `{data:{id}}` nested (NOT flat `{id}`)
- Clockify: object-wrapped `{entries:[...]}` (NOT a bare top-level array — a bare list breaks
  the live-lane `result.get("stub")` assertion)
- Bitscale list_grids: `{grids:[...]}` (live-curl-verified shape)
- Cal.com: `{status, data:[...], pagination}` (list) and `{status, data:{...}}` (create)
- Webflow create: 202 body `{id, fieldData, ...}`

## Verification Results

- `load_tool_pack` loads the manifest (24 tools); all four new ops present; `bitscale_enrich`
  gone; both Xero entries `composio_aggregator` with `COMPOSIO_API_KEY`.
- All 18 schema files validate via `Draft202012Validator.check_schema`; all reference
  `json-schema.org/draft/2020-12/schema`.
- Beehiiv nests `data`, Clockify wraps `entries`, Bitscale has top-level `grids`.
- `PYTHONPATH=src .venv/bin/python -m pytest -q -m "not live"` → **215 passed, 6 skipped** (same as baseline).
- `tests/test_credential_docs.py` UNCHANGED and still passing (5 passed) — guard deferred to 05-07.
- `pyproject.toml` UNCHANGED — no new `[project.optional-dependencies]` extra.

## Deviations from Plan

### Acceptance-criterion correction (no code change)
**Task 1 acceptance criterion stated `grep -c "composio_aggregator" >= 4` ("2 existing
composio reads + 2 flipped xero").** The manifest had only **one** pre-existing composio entry
(`composio_gmail_list_messages`), so the correct post-flip count is **3**, not ≥4. This is a
miscount in the written criterion, not a code defect — inventing a fourth composio entry would
corrupt the foundation every wave-2 plan inherits, so the entry set was left correct (3). The
Task-1 automated python `<verify>` does not assert this count and passes. The `nango == 1` half
of the criterion (only `nango_hubspot_list_contacts` remains) is satisfied exactly. No fix
required; flagged for the verifier.

### Environment note (no plan impact)
The repo's `Makefile`/plan acceptance strings invoke bare `python`, which is absent in this
shell (only homebrew `python3` + a project `.venv`). All verification was run with
`.venv/bin/python` (which has the full dep set incl. `opentelemetry`). No commit hooks present,
so commits did not shell `python`.

No Rule 1/2/3 auto-fixes were needed; no architectural (Rule 4) changes.

### State-tracking corrections
- **ROADMAP.md:** `roadmap.update-plan-progress 05` returned `"no matching checkbox found"`
  (known issue, observation 5636 — the per-plan stubs use a `- [ ] 05-01-PLAN.md — ...` format
  the SDK matcher does not target). The 05-01 plan checkbox at ROADMAP line 127 was therefore
  marked `[x]` manually.
- **TOOL-03:** the SDK's `requirements.mark-complete TOOL-03` flipped the checkbox to `[x]`
  AND split its line (`**TOOL-03\n**:`). Reverted to `[ ]` + single-line — TOOL-03 reads
  "adapters *functional*," which is FALSE after only the foundation lands (wave-2 adapters
  pending). 05-07 lists TOOL-03 in its frontmatter, so it is not orphaned and will be marked
  when the adapters are actually functional.

### Foundation contract proven (not just inferred)
Direct manifest-ref → on-disk-file resolution verified end-to-end:
`for every input/output_schema_ref in the manifest, os.path.exists(ref)` → all resolve. This
is THE D-04 reachability invariant every wave-2 plan inherits.

## Known Stubs

None. This plan adds no execution code — it only declares manifest surfaces and JSON schemas.
The wave-2 adapters (05-02..05-06) supply the executors; until then each direct tool degrades
cleanly to the import-miss stub (schema ref points at an on-disk file, adapter module absent →
`get_adapter` returns `None` → engine stubs).

## For Wave-2 / Wave-3 Consumers

- The FROZEN op-name set is now on disk and matches each adapter's required `_<PROVIDER>_OPS`
  dispatch keys exactly: webflow (`webflow_list_cms_items`, `webflow_create_cms_item`),
  bitscale (`bitscale_list_grids`, `bitscale_get_workspace`, `bitscale_run_grid`), calcom
  (`calcom_list_bookings`, `calcom_create_booking`), clockify (`clockify_read_time_entries`),
  beehiiv (`beehiiv_create_post`), xero via Composio (`xero_read_invoices`,
  `xero_create_invoice`).
- 05-07 still owns the `tests/test_credential_docs.py` guard extension and the
  `docs/credentials/README.md` index — both deliberately untouched here (boxed-warning rule).
- 05-05 (clockify) must map the raw Clockify array into `{"entries": [...]}` to match the
  declared output schema.

## Self-Check: PASSED
- All 18 schema files + modified manifest exist on disk (verified).
- Commits `a0df2b0` (manifest) and `c4f6e5a` (schemas) exist in git history (verified below).
