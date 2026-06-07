---
phase: 05-reference-adapter-breadth
plan: 03
subsystem: Tool Gateway / direct adapters
tags: [tool-gateway, bitscale, direct_api, httpx, credit-safety, TOOL-03]
requires:
  - "04-03 adapter registry (register / get_adapter / adapter_key_for)"
  - "05-01 manifest entries (bitscale_list_grids/get_workspace/run_grid) + output schemas"
provides:
  - "src/agent_mesh/tools/adapters/bitscale.py — the 5th real direct adapter (one bitscale dispatcher)"
  - "reads-only opt-in live lane for Bitscale (list_grids + get_workspace)"
  - "Bitscale credential doc with the X-API-Key header + credit-safety note"
affects:
  - "Tool Gateway dispatch (additive own-file module; no edit to gateway.py or __init__.py)"
tech-stack:
  added: []
  patterns:
    - "single-dispatcher-per-provider routing by spec.name via _BITSCALE_OPS (hubspot.py template)"
    - "core httpx adapter (no SDK extra); creds-absent -> None is the sole degrade path (httpx is core, no ImportError branch)"
    - "credit-safety: write op proven via default-lane FAKE httpx + upstream approval gate, never a live call"
key-files:
  created:
    - "src/agent_mesh/tools/adapters/bitscale.py"
    - "tests/test_bitscale_adapter.py"
    - "tests/test_bitscale_live.py"
    - "docs/credentials/bitscale.md"
  modified: []
decisions:
  - "run_grid (write) is NEVER called in the live lane — its mapping is proven only via the default-lane fake-httpx test; the live file contains zero run_grid execution (credit-safety, LOCKED)"
  - "X-API-Key auth header (NOT Bearer); api-key/apikey 401, only X-API-Key/x-api-key 200 (live-curl verified, RESEARCH)"
  - "id fields coerced to str in list_grids + run_grid mappings to satisfy the schema's string type"
metrics:
  duration: "~12 min"
  completed: "2026-06-07"
  tasks: 1
  files: 4
---

# Phase 5 Plan 03: Bitscale Direct Adapter Summary

Bitscale ships as the FIFTH real direct adapter — an own-file `adapters/bitscale.py`
that registers EXACTLY ONE `bitscale` dispatcher routing the three manifest ops
(`bitscale_list_grids` + `bitscale_get_workspace` credit-free reads, `bitscale_run_grid`
approval-gated write) by `spec.name` via `_BITSCALE_OPS` over core `httpx` against
`https://api.bitscale.ai/api/v1` with `X-API-Key` auth. Credits are protected: `run_grid`
is never executed live — its write mapping is proven only through a default-lane fake-httpx
unit test plus the upstream approval gate.

## What Was Built

- **`src/agent_mesh/tools/adapters/bitscale.py`** — three op fns `(spec, params, *, credential) -> dict|None`,
  each returning `None` when `credential is None` (the sole D-11 degrade path; `httpx` is
  core so there is no opt-in-SDK ImportError branch). Shared `_headers()` emits
  `{"X-API-Key": credential, "Accept": "application/json"}`. `_list_grids` → `GET /grids`
  mapped to `{"grids":[...]}` with `id` coerced to `str`; `_get_workspace` → `GET /workspace`
  returned permissively; `_run_grid` → inferred `POST /grids/{grid_id}/run` with body
  `{"inputs": ...}` (grid_id from `resource_bindings` then `params`). ONE
  `register("bitscale", bitscale_adapter)`.
- **`tests/test_bitscale_adapter.py`** (default lane, network-free): creds-absent→None for
  all three ops; a 3-op collision guard proving the three spec.names reach DIFFERENT ops;
  `get_adapter("bitscale")` reachability; `_list_grids` output-schema mapping; and the
  `_run_grid` write mapping against a FAKE `httpx.request` (asserts `POST .../grids/grid-test-1/run`,
  the `{"inputs":...}` body, `X-API-Key` present, `Authorization` absent) — NO network, NO
  credit spend. This is the only place run_grid is exercised.
- **`tests/test_bitscale_live.py`** (opt-in `@pytest.mark.live`, READS ONLY): real
  `bitscale_list_grids` + `bitscale_get_workspace` through `gateway.execute(...,
  resolver=EnvCredentialResolver())`, asserting non-stub + output-schema conformance; inline
  skip when `BITSCALE_API_KEY` is unset. Contains NO run_grid call (credit-safety).
- **`docs/credentials/bitscale.md`** — dashboard key mint, the `X-API-Key` header (not Bearer),
  the `grid_id` resource binding (required only for run_grid), the placeholder-binding operator
  note (reads skip on a missing key but a grid-bound op errors on `REPLACE_WITH_BITSCALE_GRID_ID`),
  and the prominent CREDIT-SAFETY note.

## Verification

- `pytest -m "not live" tests/test_bitscale_adapter.py` → **5 passed**.
- `pytest -m live tests/test_bitscale_live.py --co` → collects 2; running it **SKIPS** cleanly
  without `BITSCALE_API_KEY`.
- Peer `tests/test_hubspot_adapter.py` still green (4 passed, 1 skipped) — the additive module
  did not disturb the shared registry/gateway.
- All 9 plan acceptance-criteria greps pass: `register(` non-comment ==1; `register("bitscale"` ==1;
  op names ==9 (≥3); `X-API-Key` ==4 (≥1); Bearer-auth form ==0; `os.getenv/environ` ==0; live
  run_grid exec form ==0; `credit` in doc ==9 (≥1); live test skips without the key.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. The adapter is a real httpx implementation. `run_grid` being stubbed in the live lane
is an intentional, plan-mandated credit-safety constraint (proven via default-lane fake-httpx +
upstream approval gate), not an unfinished stub.

## Environment Note (out of scope, not a regression)

The full `pytest -m "not live"` suite has pre-existing collection errors / failures in unrelated
modules (`test_tool_span`, `test_checkpointer_resume`, `test_observability_otel`,
`test_trace_propagation`, `test_budget_halt_governed`, `test_model_gateway_router`,
`test_orchestration_graph`, `test_read_path`, `test_sandbox`) caused by optional dependencies
absent in this lean worktree venv (`opentelemetry`, `langgraph`, `langchain`, docker). These files
predate this plan (present at base cd596d8) and are untouched by it — out of scope per the
executor deviation rules (logged here, not fixed). The Bitscale adapter + its tests are fully green
and creds-free.

**Acceptance criterion #9 / the plan's third `<automated>` verify command (`pytest -q -m "not live"`
exits 0) is ENVIRONMENT-blocked, not code-blocked.** The full suite is red in this lean worktree venv
solely because the optional deps above are not installed (every failure is a `ModuleNotFoundError` for
`opentelemetry`/`langgraph`/`langchain`/docker — none reference bitscale). Installing them is excluded
from auto-fix (Rule 3, package installs). Proof the Bitscale change is not the cause: the additive
own-file module leaves the shared registry/gateway intact, so the peer `test_hubspot_adapter.py` stays
green alongside the 5 Bitscale tests. In an environment with the optional deps present, criterion #9
passes.

## Self-Check: PASSED

- FOUND: src/agent_mesh/tools/adapters/bitscale.py
- FOUND: tests/test_bitscale_adapter.py
- FOUND: tests/test_bitscale_live.py
- FOUND: docs/credentials/bitscale.md
- FOUND commit: 958da12 (feat(05-03): Bitscale direct adapter)
