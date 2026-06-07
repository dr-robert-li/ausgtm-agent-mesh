---
phase: 05-reference-adapter-breadth
plan: 02
subsystem: tools
tags: [webflow, direct_api, httpx, tool-gateway, publishing, jsonschema]

# Dependency graph
requires:
  - phase: 05-01
    provides: "tool_pack_manifest.yaml webflow entries (provider/op names/resource_bindings) + webflow_list_cms_items/webflow_create_cms_item input+output JSON schemas"
  - phase: 04-03
    provides: "adapter-dispatch registry (register/get_adapter/adapter_key_for) — the one-dispatcher-per-provider seam"
provides:
  - "Webflow direct adapter: ONE webflow dispatcher routing webflow_list_cms_items (read) + webflow_create_cms_item (approval-gated draft write) by spec.name over core httpx"
  - "Default-lane unit test (fake httpx transport, collision guard, output-schema conformance for read AND create, forced-isDraft assertion)"
  - "Opt-in live test (skips without WEBFLOW_API_TOKEN, real list through gateway.execute)"
  - "Webflow credential/scope doc (Site API token mint, CMS:read/CMS:write, site_id/collection_id bindings, isDraft/202 gotchas)"
affects: [05-07, tool-gateway, reference-adapter-breadth]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Direct_api publishing adapter on core httpx — no SDK, no opt-in extra; stub path = credential is None (NOT ImportError)"
    - "Draft-only write safety: create hardcodes isDraft:true and ignores caller-supplied isDraft:false (T-05-02-01)"
    - "Write output-quarantine guard: default-lane test validates the create's mapped 202 body against the output schema (live lane never exercises create)"

key-files:
  created:
    - src/agent_mesh/tools/adapters/webflow.py
    - tests/test_webflow_adapter.py
    - tests/test_webflow_live.py
    - docs/credentials/webflow.md
  modified: []

key-decisions:
  - "No ImportError branch/test: httpx is a core dep, so the ONLY stub path is credential is None (drops hubspot.py's SDK try/except template)"
  - "No os.getenv in the adapter: site_id/collection_id come from spec.resource_bindings; the token arrives as credential (drops nango.py's env-read template) — keeps the credential-docs os.getenv scan clean"
  - "isDraft forced true unconditionally in the POST body so a create can never publish, even on a caller-supplied isDraft:false"
  - "Null Webflow fields (lastPublished/pagination/fieldData) are dropped, not emitted as null, to stay schema-clean (object types are non-nullable)"

patterns-established:
  - "Pattern: own-file direct_api adapter registered ONCE under spec.provider, routing by spec.name via a _PROVIDER_OPS map — additive, parallel-safe (no gateway.py edit)"
  - "Pattern: fake httpx transport via monkeypatch httpx.get/httpx.post capturing the request to assert URL shape + forced-draft body"

requirements-completed: [TOOL-03]

# Metrics
duration: 18min
completed: 2026-06-07
---

# Phase 5 Plan 02: Webflow direct adapter (TOOL-03) Summary

**Webflow Data API v2 direct adapter — ONE `webflow` dispatcher over core httpx routing `webflow_list_cms_items` (read) and `webflow_create_cms_item` (approval-gated, always-draft publish) by `spec.name`, degrading to the gateway stub when `WEBFLOW_API_TOKEN` is absent.**

## Performance

- **Duration:** ~18 min
- **Tasks:** 1
- **Files modified:** 4 (all created)

## Accomplishments
- `webflow.py`: a single `register("webflow", webflow_adapter)` dispatching to `_list_cms_items` (GET `/v2/collections/{collection_id}/items` → `{items, pagination}`) and `_create_cms_item` (POST same path, body `{isDraft: True, fieldData}`, accept 202 → `{id, fieldData, ...}`). Bearer token via `credential`; bindings via `spec.resource_bindings`; `/v2` never doubled.
- Draft-only safety (T-05-02-01): `_create_cms_item` hardcodes `isDraft: True` and ignores any caller `isDraft: False` — proven by a default-lane assertion on the captured POST body.
- Default-lane test (5 tests): registry-isolation fixture, creds-absent→None for both ops, single-dispatcher collision guard (distinct ops), `get_adapter("webflow")` reachability, read+create output-schema conformance via `Draft202012Validator`.
- Live-lane test: `pytestmark = pytest.mark.live`, inline skip on `WEBFLOW_API_TOKEN` absence, real `webflow_list_cms_items` through `gateway.execute(call, resolver=EnvCredentialResolver())`, `stub is not True` + schema assertion; `agent_mesh` imports inside the test so `--co` stays clean.
- Credential doc: Site API token mint path (Settings → Apps & Integrations → API Access → Generate), exact `CMS:read`+`CMS:write` scopes, `site_id`/`collection_id` bindings, the placeholder-binding-errors-the-live-call operator note, and the isDraft-only / HTTP-202 gotchas.

## Task Commits

1. **Task 1: Webflow single dispatcher + default & live tests + doc** - `b955c98` (feat)

## Files Created/Modified
- `src/agent_mesh/tools/adapters/webflow.py` - The one `webflow` dispatcher (read + approval-gated draft write) over httpx
- `tests/test_webflow_adapter.py` - Default-lane: collision guard, creds-absent→None, read+create output-schema conformance, forced-isDraft
- `tests/test_webflow_live.py` - Opt-in live lane: real list through the gateway; skips without the token
- `docs/credentials/webflow.md` - Site API token + CMS scopes + bindings + isDraft/202 gotchas

## Decisions Made
- Dropped hubspot.py's `try/except ImportError` (httpx is core — no SDK to be absent; stub = `credential is None`) and dropped its ImportError test (acceptance forbids it).
- Dropped nango.py's `os.getenv` reads (acceptance greps for zero `os.getenv`/`os.environ`); bindings come from `spec.resource_bindings`, token from `credential`.
- `isDraft` is hardcoded true in the POST body, never read from params — so a create cannot publish.
- Null Webflow response fields are omitted from the mapped result (schema types `pagination`/`fieldData` as non-nullable objects).

## Deviations from Plan

None - plan executed exactly as written. The single task was implemented to spec across all four owned files; all acceptance-criteria greps and the prescribed verification commands pass.

## Issues Encountered

- The full `make test` / `pytest -m "not live"` suite has **pre-existing, environment-level** collection errors and failures in unrelated modules because the heavy optional deps (langgraph/litellm/opentelemetry/langchain/langfuse) are **not installed anywhere in this environment** — verified absent on all three available interpreters (python3.14, python3.11, python3.12; no `.venv` exists in the worktree or repo root, and `make test` itself fails with `python: command not found` under `/bin/sh` since the canonical interpreter is only aliased in interactive Bash). Affected modules: `test_observability_otel.py`, `test_tool_span.py`, `test_trace_propagation.py`, `test_checkpointer_resume.py`, `test_budget_halt_governed.py` (collection errors) and `test_model_gateway_router.py`, `test_orchestration_graph.py`, `test_read_path.py` (failures). This is the project's documented lazy-import/degrade design surfacing under an env without the optional extras installed — NOT a regression. Verified identical on the clean base commit (`19 failed, 170 passed` at base → `19 failed, 175 passed` with this plan's 5 new tests). Out of scope (SCOPE BOUNDARY: only auto-fix issues directly caused by this task), and none of the four Webflow-owned files touch those modules. The Webflow default lane (`tests/test_webflow_adapter.py`, run under python3.14 which has httpx+jsonschema+pytest) is fully green (5 passed) and the live lane collects + skips cleanly.

## User Setup Required

To exercise the live lane only: mint a Webflow **Site API token** (scopes `CMS:read` + `CMS:write`), set `WEBFLOW_API_TOKEN`, and replace the `REPLACE_WITH_SITE_ID` / `REPLACE_WITH_COLLECTION_ID` placeholders in `manifests/tool_pack_manifest.yaml` with real IDs. See `docs/credentials/webflow.md`. The default suite needs none of this and stays creds-free.

## Next Phase Readiness
- Webflow direct_api adapter proves the read + approval-gated draft-publish pattern on a publishing provider; reusable as a template for the remaining wave-2 adapters and 05-07 (credential-docs/README aggregation).
- No blockers introduced. The pre-existing unrelated optional-dep test failures are an environment condition (heavy deps lazy/uninstalled), not a regression from this plan.

## Self-Check: PASSED

- All four created files exist on disk.
- Task commit `b955c98` exists in git history.
- Acceptance greps pass: ONE `register(` (non-# lines), ONE `register("webflow"`, op-name count 6 (≥2), `isDraft` count 7 (≥1), `os.getenv/environ` count 0, doc `CMS:read|CMS:write` count 2 (≥1).
- Default lane `tests/test_webflow_adapter.py`: 5 passed. Live lane collects 1, skips cleanly without the token.

---
*Phase: 05-reference-adapter-breadth*
*Completed: 2026-06-07*
