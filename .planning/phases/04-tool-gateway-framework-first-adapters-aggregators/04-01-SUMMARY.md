---
phase: 04-tool-gateway-framework-first-adapters-aggregators
plan: 01
subsystem: tool-gateway-foundation
tags: [contracts, migration, manifest, schemas, pyproject, tool-gateway]
requires: []
provides:
  - "ToolCall.integration_style / schema_validation / is_read additive fields"
  - "migrations/0003_tool_call_fields.sql (additive tool_calls columns)"
  - "all 9 Google Workspace direct-tool manifest entries with both schema refs"
  - "16 GWS input/output Draft 2020-12 schema files"
  - "jsonschema core dep + tools/aggregators optional extras"
affects:
  - src/agent_mesh/contracts/models.py
  - src/agent_mesh/services/repository.py
  - migrations/0003_tool_call_fields.sql
  - schemas/contracts/ToolCall.schema.json
  - manifests/tool_pack_manifest.yaml
  - pyproject.toml
  - tests/conftest.py
tech-stack:
  added:
    - "jsonschema>=4.18,<5 (core dep — schema boundary never optional)"
    - "tools extra: hubspot-api-client, google-api-python-client, google-auth, google-auth-oauthlib (declared, not installed)"
    - "aggregators extra: composio (declared, not installed); Nango via httpx, no pypi dep"
  patterns:
    - "additive-only contract evolution (extra=forbid + contract-parity test forbid rewrites)"
    - "idempotent ADD COLUMN IF NOT EXISTS migration (0002 precedent)"
    - "permissive-by-design schema authoring (D-05): additionalProperties open by default, tighten only cost/security-critical target IDs"
key-files:
  created:
    - migrations/0003_tool_call_fields.sql
    - tests/test_tool_call_contract.py
    - schemas/gmail_send.input.schema.json
    - schemas/gmail_send.output.schema.json
    - schemas/google_sheets_append.input.schema.json
    - schemas/google_sheets_append.output.schema.json
    - schemas/google_calendar_list_events.input.schema.json
    - schemas/google_calendar_list_events.output.schema.json
    - schemas/google_calendar_create_event.input.schema.json
    - schemas/google_calendar_create_event.output.schema.json
    - schemas/google_docs_get.input.schema.json
    - schemas/google_docs_get.output.schema.json
    - schemas/google_docs_create.input.schema.json
    - schemas/google_docs_create.output.schema.json
    - schemas/google_slides_get.input.schema.json
    - schemas/google_slides_get.output.schema.json
    - schemas/google_slides_create.input.schema.json
    - schemas/google_slides_create.output.schema.json
  modified:
    - src/agent_mesh/contracts/models.py
    - src/agent_mesh/services/repository.py
    - schemas/contracts/ToolCall.schema.json
    - manifests/tool_pack_manifest.yaml
    - pyproject.toml
    - tests/conftest.py
decisions:
  - "is_read modeled as a non-null bool default False (not optional) — every tool call is read-or-write, never undetermined"
  - "schema_validation kept as str | None with documented values (ok/input_rejected/output_quarantined) rather than an enum — keeps the contract additive and avoids a new enum import the engine plan can revisit"
  - "ON CONFLICT DO UPDATE SET updates all three new fields — schema_validation/is_read/integration_style are set/refined post-insert by the engine"
requirements: [TOOL-01, TOOL-02]
metrics:
  duration: "~25m"
  completed: "2026-06-06"
  tasks: 3
  commits: 4
---

# Phase 4 Plan 01: Tool Gateway Foundation Summary

Laid the contract, persistence, manifest, and dependency foundation every other Phase-4 plan builds on: additive `ToolCall` fields (`integration_style` / `schema_validation` / `is_read`) with an idempotent migration and the repository.py 4-place ripple; all 9 Google Workspace direct tools declared with both input/output schema refs and 16 Draft 2020-12 schema files; and `jsonschema` promoted to a core dep with opt-in `tools`/`aggregators` extras — default suite green (138 passed) and creds-free, with nothing installed.

## What Was Built

### Task 1 — Additive ToolCall fields + migration 0003 + repository ripple (TDD)
- Added three additive fields to `ToolCall` (`contracts/models.py`): `integration_style: str | None`, `schema_validation: str | None` (values documented `ok` / `input_rejected` / `output_quarantined`), `is_read: bool = False`. Additive-only — `extra="forbid"` and the contract-parity test forbid a rewrite.
- `migrations/0003_tool_call_fields.sql`: idempotent `ADD COLUMN IF NOT EXISTS` x3, following the 0002 header/idempotency style. `is_read` is `BOOLEAN NOT NULL DEFAULT false` so historical rows stay valid (no backfill).
- `repository.py` 4-place ripple, with the discriminating invariant verified by eye (SELECT order === tuple-unpack order === constructor order; INSERT column list order === VALUES placeholder order — 16 columns / 16 placeholders): `_TOOL_CALL_COLS`, `_row_to_tool_call`, the INSERT (column list + VALUES + params + `ON CONFLICT DO UPDATE SET`). `InMemoryRepository` unchanged (stores the model whole).
- `conftest.py` `_MIGRATIONS` includes `0003_tool_call_fields.sql`.
- Regenerated `schemas/contracts/ToolCall.schema.json` via `export_schemas` (idempotent; `sort_keys=True` keeps it byte-stable on re-run; only this contract schema changed).
- TDD: RED (3 failing tests on `extra="forbid"` + missing schema props) → GREEN.

### Task 2 — All Google Workspace manifest entries + every GWS schema (D-08 x D-04)
- Backfilled `input_schema_ref`/`output_schema_ref` on the existing `gmail_send` and `google_sheets_append` entries (they had none — the D-08×D-04 fail-closed gap).
- Added 6 new entries: `google_calendar_list_events` (read), `google_calendar_create_event` (write), `google_docs_get` (read), `google_docs_create` (write), `google_slides_get` (read), `google_slides_create` (write). 9 GWS tools total.
- Authored 16 schema files (Draft 2020-12), copying the hubspot/drive template. Permissive-by-design (D-05): `additionalProperties` open on write inputs; tightened only the cost/security-critical target IDs (Gmail recipient `format: email`, Sheets `spreadsheet_id`, Calendar `calendar_id`, Docs/Slides `folder_id`). Reads use `additionalProperties:false`.
- Every GWS write-class entry has `approval_required: true` (else `ToolSpec.validate` raises at load — verified).

### Task 3 — pyproject tools/aggregators extras + jsonschema core dep (D-12 prep)
- `jsonschema>=4.18,<5` promoted to core `dependencies` (the schema boundary must never be an optional import). Confirmed it is NOT in any extra.
- New `tools` extra (HubSpot + Google API client/auth/oauthlib) and `aggregators` extra (composio), both with explanatory comments. Nango deliberately has NO pypi package (integrates via core `httpx`); a comment records the DO-NOT-INSTALL rationale.
- Installs nothing — every provider install is gated behind the per-adapter human-verify checkpoints in 04-05/06/07/08.

## Deviations from Plan

None — plan executed exactly as written.

## Verification

- `PYTHONPATH=src .venv/bin/python -m pytest -q -m "not live"` → **138 passed, 6 skipped, 4 deselected** (baseline was 135 passed; +3 from the new contract test). Creds-free; no provider SDKs installed.
- `export_schemas` regenerates `ToolCall.schema.json` idempotently (byte-identical on re-run); only that contract schema changed — no pre-existing drift staged.
- `load_tool_pack('manifests/tool_pack_manifest.yaml')` loads without raising the write-class invariant; 9 `google_workspace` tools, every one with both schema refs, every referenced schema file present and Draft 2020-12.
- Migration 0003 is additive + idempotent (`ADD COLUMN IF NOT EXISTS` x3).

Note: the repository.py SQL ripple is NOT exercised by the default lane — `test_repository_sql.py` is in the 6 skipped (no `TEST_DATABASE_URL`/Postgres). The three ordering invariants were verified by inspection and a placeholder-count check (16 == 16).

## Commits

- `9c8b21f` test(04-01): add failing contract test for additive ToolCall fields (RED)
- `3f442ce` feat(04-01): add additive ToolCall fields + migration 0003 + repo ripple (GREEN)
- `385b81c` feat(04-01): declare all Google Workspace tools + every GWS schema (D-08 x D-04)
- `78f9717` chore(04-01): jsonschema core dep + tools/aggregators optional extras (D-12 prep)

## TDD Gate Compliance

Task 1 (`tdd="true"`): RED commit `9c8b21f` (test only, verified failing) precedes GREEN commit `3f442ce` (implementation). No refactor commit needed.

## Self-Check: PASSED

- All created files exist on disk and are committed (16 schema files, migration 0003, test_tool_call_contract.py).
- All 4 commit hashes exist in git log.
- Working tree clean; no untracked/unstaged files.
