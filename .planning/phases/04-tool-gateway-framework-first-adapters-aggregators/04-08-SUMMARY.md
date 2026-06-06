---
phase: 04-tool-gateway-framework-first-adapters-aggregators
plan: 08
subsystem: tool-gateway-aggregator-adapters
tags: [tool-gateway, aggregators, composio, nango, TOOL-04, D-04, D-09, D-11, D-12, SC-3]
requires:
  - "tools/adapters/__init__.py: register / get_adapter (lazy-import-on-miss) / adapter_key_for (04-03)"
  - "tools/gateway.py: ToolGateway.execute(call, *, resolver) — aggregate validation passes runtime_schema=None (04-03/04-02)"
  - "tools/validation.py: aggregate branch never blocks on a missing runtime schema (04-02, D-04)"
  - "pyproject aggregators extra: composio>=0.13,<1; Nango NO pip dep (04-01)"
provides:
  - "tools/aggregate_schema.py: fetch_runtime_schema(spec, *, session) + _SCHEMA_CACHE (D-04 runtime-schema seam)"
  - "tools/adapters/composio.py: composio_adapter registered under key 'composio' (lazy composio SDK)"
  - "tools/adapters/nango.py: nango_adapter registered under key 'nango' (httpx REST proxy, NO nango pip dep)"
  - "manifest seam: composio_gmail_list_messages (composio_aggregator) + nango_hubspot_list_contacts (nango_aggregator) READ tools"
  - "docs/credentials/composio.md + docs/credentials/nango.md (D-12)"
affects:
  - src/agent_mesh/tools/aggregate_schema.py
  - src/agent_mesh/tools/adapters/composio.py
  - src/agent_mesh/tools/adapters/nango.py
  - manifests/tool_pack_manifest.yaml
  - docs/credentials/composio.md
  - docs/credentials/nango.md
  - tests/test_aggregate_schema.py
  - tests/test_aggregator_adapters.py
  - tests/test_composio_live.py
  - tests/test_nango_live.py
  - tests/test_stack_and_toolpacks.py
tech-stack:
  added: []  # composio is an opt-in extra (04-01); NOT installed in the default lane
  patterns:
    - "module-global _SCHEMA_CACHE process-cache (orchestrator._PG_SAVER idiom); caches None too"
    - "register() at module top + LAZY SDK import inside the adapter fn (get_adapter import-on-miss reachability without the SDK installed — closes SC-3)"
    - "Nango via httpx REST /proxy only — NO nango python package (RESEARCH Pitfall 1)"
    - "live tests: SDK imports inside the test body so collection SKIPS (never ERRORS) creds/SDK-free"
key-files:
  created:
    - src/agent_mesh/tools/aggregate_schema.py
    - src/agent_mesh/tools/adapters/composio.py
    - src/agent_mesh/tools/adapters/nango.py
    - docs/credentials/composio.md
    - docs/credentials/nango.md
    - tests/test_aggregate_schema.py
    - tests/test_aggregator_adapters.py
    - tests/test_composio_live.py
    - tests/test_nango_live.py
  modified:
    - manifests/tool_pack_manifest.yaml
    - tests/test_stack_and_toolpacks.py
decisions:
  - "Adapters register under the bare aggregator name (composio/nango == module filename == adapter_key_for key), NOT the integration_style string — registering under 'composio_aggregator' would never be looked up and a creds-present call would silently stub (SC-3)"
  - "SDK import is LAZY (inside the adapter fn); register() is at module top. If the SDK import were at module top, get_adapter's ImportError swallow would return None and the registered adapter would be unreachable without the SDK installed — the exact SC-3 regression"
  - "fetch_runtime_schema is called from inside the Composio adapter (not from execute()); gateway.py is NOT edited — the engine already passes runtime_schema=None to the aggregate validation branch (04-03), which is permissive by design (D-04)"
  - "Nango credential is NANGO_SECRET_KEY but the proxy also needs NANGO_HOST/CONNECTION_ID/PROVIDER_CONFIG_KEY; the adapter returns None (degrade-to-stub) when any is absent, and the live test skips on the same 4-var precondition"
  - "_SCHEMA_CACHE caches None too, so tests snapshot/restore it per case (a stale None would mask a later positive fetch)"
requirements: [TOOL-04]
metrics:
  duration: "~30m"
  completed: "2026-06-06"
  tasks: 2
  commits: 3
---

# Phase 4 Plan 08: Composio + Nango Aggregator Adapters Summary

Proved BOTH aggregator integration styles end-to-end (TOOL-04, D-09): **Composio**
(primary, managed-auth Tool Router via the `composio` SDK) and **Nango** (fallback,
self-hosted OSS unified API via the REST proxy over `httpx` — NO `nango` pip dependency).
Each performs one real READ through `ToolGateway.execute()` in its own opt-in live lane.
Both adapters register under the exact aggregator-name keys `adapter_key_for` produces
(`composio` / `nango` — NOT the `*_aggregator` style string), closing the SC-3 half of
the dispatch contract: a registered adapter + creds reaches a live call, not the stub.
Added the runtime aggregate-schema fetch+cache the validator's aggregate branch consumes
(D-04: a missing runtime schema NEVER blocks). Default suite stays green and creds-free:
**175 passed, 6 skipped, 6 deselected** (baseline 165; +10 default-lane tests, +2 live
deselected).

## Package-Legitimacy Gate (T-04-08-SC) — Audit Record

The blocking-human checkpoint (Task 1 of the plan, `gate="blocking-human"`) was
pre-satisfied by the human operator with resume-signal **"approved"**. Recorded here for
the 12-month supply-chain audit:

> **package-legitimacy gate T-04-08-SC: `composio>=0.13,<1` approved (official, verified
> on PyPI 2026-06-06); PyPI `nango` confirmed unrelated/squatted — NOT installed, Nango
> via httpx REST proxy only.**

- **Composio:** `composio` 0.13.1 confirmed the current OFFICIAL Composio SDK (PyPI
  publisher Composio; home `github.com/composiohq/composio`; import is
  `from composio import Composio`, NOT `composio-core`). Approved to declare
  `composio>=0.13,<1` in the `aggregators` optional extra (already present from 04-01;
  NOT re-edited and NOT installed in the default lane).
- **Nango:** CONFIRMED NOT to be installed. The PyPI `nango` package (0.1.2) is an
  UNRELATED third-party package (author "Nick Farrell", summary "Provide model integrity
  between requests") — it is NOT NangoHQ. The official Nango SDK is npm `@nangohq/node`;
  Python integrates via the REST proxy over `httpx` with NO `nango` pip dependency.

## What Was Built

### Task 1 — Runtime aggregate-schema fetch + cache (D-04 / RESEARCH Pattern 3)
- **`tools/aggregate_schema.py`**: `fetch_runtime_schema(spec, *, session=None) -> dict |
  None` keyed on `(spec.provider, spec.name)` in a module-global `_SCHEMA_CACHE` (copies
  the `orchestrator._PG_SAVER` process-cache idiom). For `composio_aggregator` specs with
  a live session it scans `session.tools()` for the tool matching `spec.name` and returns
  its input JSON Schema (probing `input_parameters` / `inputSchema` / … — RESEARCH A1 key
  churn handled defensively, default `None`). For Nango / any non-Composio style it returns
  `None` (permissive — the proxy exposes no per-tool schema). The result (INCLUDING `None`)
  is cached so a second call does NOT re-query. Import-safe with NO composio SDK (the SDK
  is never imported here; the caller-supplied session is duck-typed).
- **`tests/test_aggregate_schema.py`** (5 tests, default lane): fetch returns the schema +
  queries once; the cache prevents a second `.tools()` call (fetch-once); a Nango-style
  spec returns `None` without raising; a not-found tool caches `None`; the module imports
  without the composio SDK in `sys.modules`.

### Task 2 — Composio + Nango adapters under their aggregator keys, one real read each
- **`tools/adapters/composio.py`**: `composio_adapter(spec, params, *, credential)` —
  `register("composio", …)` at module top; **lazy** `from composio import Composio` inside
  the fn; builds `Composio(api_key=credential).create(user_id=…)`, fetches the runtime
  schema (D-04), and calls `session.execute(tool=<tool_slug>, arguments=params)`; maps to
  a result dict with `aggregator="composio"`. Returns `None` defensively when the
  credential is absent (the engine stubs before reaching it — D-11).
- **`tools/adapters/nango.py`**: `nango_adapter(...)` — `register("nango", …)` at module
  top; **NO `nango` import** — uses `httpx` to `GET {NANGO_HOST}/proxy/<endpoint>` with
  `Authorization: Bearer {NANGO_SECRET_KEY}`, `Connection-Id`, `Provider-Config-Key`
  headers; maps the JSON to a result dict with `aggregator="nango"`. Degrades to stub
  (returns `None`) when the credential or any of the three other env vars is absent.
- **Manifest seam** (`manifests/tool_pack_manifest.yaml`): added
  `composio_gmail_list_messages` (`composio_aggregator`, `COMPOSIO_API_KEY`, read) and
  `nango_hubspot_list_contacts` (`nango_aggregator`, `NANGO_SECRET_KEY`, read). Reads only
  (no approval-gate coupling); no `input_schema_ref` (runtime-schema'd per D-04).
- **`tests/test_aggregator_adapters.py`** (5 tests, default lane): the SC-3 guard. Forces a
  true re-import (`sys.modules.pop` + `importlib.import_module`) and asserts each module
  registers under its aggregator-name key (and NOT the `*_aggregator` string);
  `get_adapter("composio"/"nango")` returns a callable via import-on-miss WITHOUT the SDK
  installed (proves lazy SDK import); both modules import without the composio SDK; nango.py
  contains zero `nango` imports and the httpx proxy path.
- **Live tests** (`tests/test_composio_live.py`, `tests/test_nango_live.py`): each
  `pytest.mark.live`, skips on its own env (`COMPOSIO_API_KEY`; the four `NANGO_*`),
  performs one real read through `gateway.execute` and asserts the registered adapter ran
  (`stub is not True`, `aggregator` set). SDK imports are inside the test body so collection
  is SDK-free.
- **Docs** (`docs/credentials/composio.md`, `docs/credentials/nango.md`, D-12): Composio
  managed-auth (extra install, API key, `composio.create(user_id=…)`, the test read);
  Nango self-host via `docker compose`, provider config + connection, the four env vars,
  the proxy call shape.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Stale integration_style allow-set blocked composio_aggregator**
- **Found during:** Task 2 (full-suite run after the manifest edit).
- **Issue:** `tests/test_stack_and_toolpacks.py::test_every_tool_declares_an_integration_style`
  asserted every manifest tool's `integration_style` is in
  `{direct_api, mcp_server, aggregate_mcp, nango_aggregator}` — a stale set MISSING
  `composio_aggregator`, even though CLAUDE.md §3 (Tool Pack Contract) and Acceptance
  Criterion #13 list `composio_aggregator` as a supported peer aggregator style. Adding the
  Composio manifest seam (a legitimate, architecturally-mandated value) tripped it.
- **Fix:** Added `composio_aggregator` to the `allowed` set (all five contract styles).
- **Files modified:** tests/test_stack_and_toolpacks.py
- **Commit:** bd8b966

**Scope note (NOT a deviation):** The plan's Task-1 wording ("feeds the 04-02 aggregate
validation branch") could be read as an engine edit. It is not: `gateway.py` already passes
`runtime_schema=None` to `validate_tool_input` (04-03, permissive aggregate branch, D-04).
The `fetch_runtime_schema` seam is consumed INSIDE the Composio adapter, and `gateway.py` is
NOT in this plan's `files_modified` — left untouched to protect the green baseline.

## Verification

- `PYTHONPATH=src .venv/bin/python -m pytest -q -m "not live"` -> **175 passed, 6 skipped,
  6 deselected** (baseline 165 passed, 4 deselected; +10 default-lane tests, +2 live
  deselected). Creds-free; no provider SDKs installed.
- `ruff check` on all new/modified src + test files -> All checks passed.
- Acceptance criteria (Task 1):
  - `grep -c "_SCHEMA_CACHE" aggregate_schema.py` = 4 (>= 1) ✓
  - cache prevents a second `.tools()` call (fetch-once) — `test_composio_fetch_is_cached_does_not_requery` ✓
  - Nango-style spec returns `None` without raising — `test_nango_style_returns_none_without_raising` ✓
  - module imports WITHOUT the composio SDK (lazy) — `test_module_imports_without_composio_sdk` ✓
- Acceptance criteria (Task 2):
  - `grep -c 'register("composio"' composio.py` = 1; `grep -c 'register("nango"' nango.py` = 1 (NOT the `*_aggregator` strings) ✓
  - default-lane test asserts `get_adapter("composio"/"nango")` each return a callable via import-time registration — `test_get_adapter_resolves_aggregator_keys_via_import_on_miss` ✓
  - `grep -ci 'import nango|from nango' nango.py` = 0 (httpx proxy only) ✓
  - `grep -c "proxy" nango.py` = 8 (>= 1); headers include `Connection-Id` + `Provider-Config-Key` ✓
  - `pytest -m live tests/test_composio_live.py` SKIPS without `COMPOSIO_API_KEY`; `tests/test_nango_live.py` SKIPS without the `NANGO_*` set; both COLLECT SDK-free ✓
  - `grep -c "docker compose|docker-compose" nango.md` = 4 (>= 1) ✓
  - full `-m "not live"` suite exits 0 (neither adapter requires its client to import) ✓

## Must-Haves Coverage (from PLAN frontmatter)

- "Composio executes one real read end-to-end through the gateway (TOOL-04, D-09)" ->
  `composio.py` + `test_composio_live.py` (opt-in real read) ✓
- "Nango executes one real read via the REST proxy over httpx — NO nango PyPI package" ->
  `nango.py` (httpx only) + `test_nango_live.py`; `test_nango_adapter_has_no_nango_package_import` ✓
- "execute() routes aggregator tools to these adapters via adapter_key_for; the adapters
  register under those exact keys (closes SC-3)" -> register at module top under
  `composio`/`nango`; `test_aggregator_adapters.py` SC-3 guard ✓
- "Aggregate tools validate against a runtime provider schema fetched + cached; a missing
  runtime schema NEVER blocks (D-04)" -> `aggregate_schema.fetch_runtime_schema` +
  permissive `None`; the engine's aggregate branch is already permissive ✓
- "With aggregator creds absent both adapters degrade to the stub; make test stays green
  and creds-free (D-11)" -> both return `None` creds-absent; full suite green creds-free ✓

## Threat Model Coverage

- **T-04-08-SC (Tampering — composio 0.x supply chain)** — MITIGATED. Blocking-human
  checkpoint verified `from composio import Composio` + pin `composio>=0.13,<1`; audit
  record above. SDK is an opt-in extra, NOT installed in the default lane.
- **T-04-08-02 (Tampering — fake PyPI `nango` package)** — MITIGATED + test-asserted.
  DO-NOT-INSTALL confirmed; `nango.py` uses httpx only;
  `test_nango_adapter_has_no_nango_package_import` asserts zero `nango` imports.
- **T-04-08-01 (Information disclosure — aggregator credential / payload exfiltration)** —
  MITIGATED. Credentials resolved only inside `execute()` (04-03), passed as `credential`,
  never returned/logged; READS only this phase (D-09); the adapter result dicts carry no
  credential.
- **T-04-08-03 (Spoofing/Tampering — aggregate input unvalidated)** — MITIGATED BY DESIGN.
  D-04: Composio validates against the runtime provider schema when present; Nango is
  permissive (no schema) — reads only, so blast radius is read-not-write.

No high-severity threat left open.

## Threat Flags

None. No new security surface beyond the two declared aggregator trust boundaries
(gateway -> Composio Tool Router; gateway -> self-hosted Nango proxy), both READ-only and
already in the plan's threat model.

## Known Stubs

The credentials-absent / SDK-absent fallback returns the deterministic stub by design
(D-11) — the intended creds-free default-lane behavior, not an undelivered goal. Both
adapters reach a real call only in their opt-in live lanes when their env is exported. No
unintended stubs.

## Commits

- `cafced8` feat(04-08): runtime aggregate-schema fetch + process cache (D-04)
- `bd8b966` feat(04-08): Composio + Nango aggregator adapters (TOOL-04, D-09)
- (this) docs(04-08): complete Composio + Nango aggregators plan

## Self-Check: PASSED

- All 9 created files + the SUMMARY exist on disk.
- Commit hashes `cafced8` and `bd8b966` exist in git log.
- Full default suite green: 175 passed, 6 skipped, 6 deselected (creds-free, SDK-free).
- STATE.md and ROADMAP.md NOT modified (orchestrator owns those writes).
- Working tree clean except the untracked `.venv` symlink (environment-only, never staged).
