---
phase: 04-tool-gateway-framework-first-adapters-aggregators
plan: 02
subsystem: tool-gateway-schema-boundary
tags: [validation, jsonschema, schema-boundary, tool-gateway, D-04, D-06]
requires:
  - "jsonschema core dep (04-01)"
  - "schemas/hubspot_lookup_company.input.schema.json, schemas/gmail_send.output.schema.json (pre-existing)"
provides:
  - "tools/validation.py: validate_input / validate_output / validate_tool_input"
  - "InputSchemaViolation / OutputSchemaViolation / SchemaError exception hierarchy"
  - "D-04 fail-closed-for-direct-only dispatch seam the engine (04-03) calls"
affects:
  - src/agent_mesh/tools/validation.py
  - tests/test_schema_boundary.py
tech-stack:
  added: []
  patterns:
    - "Draft202012Validator at module top (jsonschema is a guaranteed core dep — not gated)"
    - "asymmetric failure (D-06): input raises, output returns quarantine messages"
    - "source-by-style fail-closed (D-04): direct BLOCKS on missing schema, aggregate is permissive"
key-files:
  created:
    - src/agent_mesh/tools/validation.py
    - tests/test_schema_boundary.py
  modified: []
decisions:
  - "Draft202012Validator imported at module top (not lazily) — jsonschema is a core dep since 04-01, so the boundary must never be an optional/degradable import"
  - "validate_output returns list[str] and never raises on a content violation — distinguishes 'ran but untrusted' (quarantine) from 'never ran' (input reject); OutputSchemaViolation exists for callers that prefer to raise on a non-empty list"
  - "_AGGREGATE_STYLES frozenset (composio/nango/aggregate_mcp/mcp_server) defines the permissive set; dispatch keys on integration_style == 'direct_api' for the BLOCK branch so any non-direct style is permissive-by-default"
  - "validate_tool_input is keyword-only (*,) so the engine call site is self-documenting and arg-order-safe"
requirements: [TOOL-02]
metrics:
  duration: "~12m"
  completed: "2026-06-06"
  tasks: 1
  commits: 2
---

# Phase 4 Plan 02: Tool Gateway Schema Boundary Summary

Built the creds-free JSON-Schema validation boundary (TOOL-02) as a standalone,
importable module the execution engine (04-03) will call input-pre-call and
output-post-call. `tools/validation.py` encodes the three locked decisions
exactly — D-04 source-by-style fail-closed (direct BLOCKS on a missing schema,
aggregate is permissive), D-05 permissive-by-design (the validator applies
whatever the schema declares), and D-06 asymmetric failure (input raises,
output quarantines). Default suite green (148 passed, +10) and creds-free, with
nothing installed.

## What Was Built

### Task 1 — Draft 2020-12 validator with asymmetric input/output failure (TDD)
- `SchemaError` base + `InputSchemaViolation` / `OutputSchemaViolation` subclasses
  (the D-06 asymmetric pair).
- `_load(ref)` reads + JSON-parses a schema file path.
- `validate_input(schema, params) -> None`: `None` schema raises; otherwise collects
  `Draft202012Validator(schema).iter_errors(params)` (sorted by error path for stable
  messages) and raises `InputSchemaViolation` joining the messages. Returns `None` on pass.
- `validate_output(schema, result) -> list[str]`: `None` schema returns `[]` (permissive);
  otherwise returns the list of `iter_errors` messages (`[]` == valid). **Never raises on a
  content violation** — the SaaS call already ran, so the caller quarantines.
- `validate_tool_input(*, integration_style, input_schema_ref, runtime_schema, params)`:
  the D-04 fail-closed DISPATCH, encoded EXACTLY and not generalized —
  `direct_api` + `input_schema_ref is None` -> raise `InputSchemaViolation` (BLOCK);
  `direct_api` + ref -> `validate_input(_load(ref), params)`;
  aggregate styles -> validate against `runtime_schema` when supplied, else return cleanly
  (NEVER block). `_AGGREGATE_STYLES` frozenset documents the permissive set.
- `Draft202012Validator` imported at module top — jsonschema is a core dep since 04-01,
  so the boundary is never an optional/degradable import (deliberately unlike
  `observability.py`'s `*_available()` guards, whose deps are optional).
- TDD: RED (collection error — module absent) -> GREEN (10 tests pass). No refactor needed.

## Deviations from Plan

None — plan executed exactly as written. (RESEARCH Pattern 2 supplied the verbatim
implementation shape; the plan's "module-top is preferred for jsonschema" guidance
was followed.)

## Verification

- `PYTHONPATH=src .venv/bin/python -m pytest -q -m "not live"` -> **148 passed, 6 skipped,
  4 deselected** (baseline 138 passed; +10 from the new boundary tests). Creds-free; no
  provider SDKs installed.
- `PYTHONPATH=src .venv/bin/python -m pytest -q -m "not live" tests/test_schema_boundary.py`
  exits 0 (10 passed).
- Acceptance criteria:
  - `grep -c "Draft202012Validator" src/agent_mesh/tools/validation.py` = 4 (>= 1) ✓
  - `grep -cE "class InputSchemaViolation|class OutputSchemaViolation"` = 2 ✓
  - `pytest -k "direct_no_schema and blocked"` selects 1 test; `pytest -k "aggregate and permissive"`
    selects 1 test ✓
  - reject test targets `hubspot_lookup_company` (schema-declaring tool, Pitfall 5 honoured),
    NOT a schema-less tool ✓
- All four D-04/D-06 cases asserted against schema-declaring tools:
  input reject (hubspot, missing `query`), input ok, direct no-schema BLOCK,
  aggregate no-schema PERMISSIVE, output quarantine (gmail_send, missing `message_id`),
  plus aggregate-with-runtime-schema enforced and direct-with-ref enforced.

## Must-Haves Coverage (from PLAN frontmatter)

- "direct schema-INVALID input is hard-rejected with no adapter call (D-06)" -> `validate_input`
  raises; `test_input_reject_missing_required_field_raises` ✓
- "direct output violating schema is flagged/quarantined, not silently trusted (D-06)" ->
  `validate_output` returns non-empty messages; `test_output_violation_returns_quarantine_messages` ✓
- "direct tool with NO schema is BLOCKED (D-04 fail-closed direct only)" ->
  `validate_tool_input` raises; `test_direct_no_schema_is_blocked` ✓
- "aggregate tool with no runtime schema is NOT blocked (D-04 NEVER for aggregate)" ->
  `validate_tool_input` returns cleanly; `test_aggregate_no_runtime_schema_is_permissive` ✓

## Threat Model Coverage

All three registered threats mitigated by this boundary:
- T-04-02-01 (malformed input -> SaaS write): `validate_input` hard-rejects pre-call (engine
  records a failed tool_call in 04-03).
- T-04-02-02 (unvalidated direct tool slipping through): D-04 fail-closed BLOCKS a direct tool
  with no schema; dedicated test asserts it.
- T-04-02-03 (poisoned SaaS response trusted downstream): `validate_output` quarantines
  non-conforming output.

No new threat surface introduced (pure validation logic; no network/auth/file-write paths).

## Commits

- `fd161f5` test(04-02): add failing schema-boundary tests for D-04/D-06 validator (RED)
- `715ea98` feat(04-02): implement Draft 2020-12 schema-boundary validator (GREEN)

## TDD Gate Compliance

Task 1 (`tdd="true"`): RED commit `fd161f5` (test only, verified failing — `ModuleNotFoundError`
on collection) precedes GREEN commit `715ea98` (implementation, 10 passed). No refactor commit
needed — the implementation matched RESEARCH Pattern 2 with no cleanup required.

## Self-Check: PASSED

- `src/agent_mesh/tools/validation.py` exists on disk and is committed.
- `tests/test_schema_boundary.py` exists on disk and is committed.
- Both commit hashes (`fd161f5`, `715ea98`) exist in git log.
- Working tree clean except the untracked `.venv` symlink (environment-only, never staged).
