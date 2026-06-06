---
phase: 04-tool-gateway-framework-first-adapters-aggregators
plan: 06
subsystem: tool-gateway-google-workspace-adapter
tags: [tool-gateway, google-workspace, direct-adapter, oauth-refresh, D-08, D-11, D-12, TOOL-01]
requires:
  - "tools/adapters/__init__.py: register / get_adapter / adapter_key_for (04-03 seam)"
  - "tools/gateway.py: execute(call, *, resolver) engine + stub fallback (04-03)"
  - "tools/credentials.py: EnvCredentialResolver (04-03, D-02)"
  - "manifests/tool_pack_manifest.yaml GWS tool declarations + schemas/google_*.schema.json (04-01)"
provides:
  - "tools/adapters/google_workspace.py: shared _build_credentials + _service auth scaffold + ONE google_workspace dispatcher routing Drive/Gmail/Sheets by spec.name via _GWS_OPS (D-08 part 1)"
  - "_GWS_OPS extension point: 04-07 adds Calendar/Docs/Slides in the SAME file with NO new register() call"
  - "docs/credentials/google_workspace.md: OAuth client + refresh-token minting + per-product least-privilege scopes (D-12 GWS slice)"
  - "tests/test_gws_adapter.py (default lane) + tests/test_gws_live.py (opt-in, skips without GOOGLE_WORKSPACE_OAUTH)"
affects:
  - src/agent_mesh/tools/adapters/google_workspace.py
  - docs/credentials/google_workspace.md
  - tests/test_gws_adapter.py
  - tests/test_gws_live.py
tech-stack:
  added: []
  patterns:
    - "single-dispatcher-per-provider-key: one register('google_workspace', fn) routing by spec.name via _GWS_OPS (NOT one register per op — would last-wins-collide)"
    - "lazy-import + patchable seams: _build_credentials / _service wrap google imports so the module imports SDK-free and default-lane tests monkeypatch the seams (no SDK, no network)"
    - "credential-None -> None sentinel BEFORE any creds build -> execute() falls back to the deterministic stub (D-11)"
    - "strict-output mapping: rename google fields (id->file_id, mimeType->mime_type, modifiedTime->modified_at) + OMIT absent optionals (additionalProperties:false rejects null-typed strings)"
key-files:
  created:
    - src/agent_mesh/tools/adapters/google_workspace.py
    - docs/credentials/google_workspace.md
    - tests/test_gws_adapter.py
    - tests/test_gws_live.py
  modified: []
decisions:
  - "The three google packages (google-api-python-client>=2.190, google-auth>=2.40, google-auth-oauthlib>=1.2) were ALREADY declared in the `tools` optional extra by 04-01 (commit 78f9717); the package-legitimacy gate (T-04-06-SC) blesses them. No pyproject change in this plan; NOT installed into the default lane (extras opt-in; lazy import keeps the module importable creds-free)."
  - "Auth/service built as module-level patchable seams (_build_credentials, _service) so the Drive output-mapping unit test runs with the SDK NOT installed (monkeypatch both -> neither google import fires)."
  - "Drive output mapped to the STRICT google_drive_search.output schema: request fields=files(id,name,mimeType,modifiedTime), rename keys, OMIT absent optionals (mime_type:null would fail the string type under additionalProperties:false). Mapping test asserts via validate_output(_load(real_schema_ref), result)."
  - "Live lane gates on GOOGLE_WORKSPACE_OAUTH (NOT the shared live_creds fixture, which gates the Anthropic/Vertex/CF model lane); absence is a SKIP, never an error."
requirements: [TOOL-01]
metrics:
  duration: "~30m"
  completed: "2026-06-06"
  tasks: 1
  commits: 1
---

# Phase 4 Plan 06: Google Workspace direct suite (Drive/Gmail/Sheets) Summary

Shipped the first half of the full Google Workspace direct suite (D-08): the shared
OAuth/refresh **auth scaffold** plus the Drive (read), Gmail (external_send), and
Sheets (write) operations, as an own-file adapter module registered with the 04-03
registry. One OAuth client + a stored refresh token drives a single
`google-api-python-client` across all products via `google.oauth2.credentials.Credentials`
(auto-refresh). The adapter registers **EXACTLY ONE** dispatcher under the shared
`google_workspace` provider key, routing by `spec.name` through `_GWS_OPS`, and degrades
to the deterministic stub when `GOOGLE_WORKSPACE_OAUTH` is absent (D-11). Default suite:
**171 passed, 6 skipped, 5 deselected** (baseline 165/6/4; +6 adapter tests, +1
deselected live test). Creds-free; no provider SDKs installed.

## Package-Legitimacy Gate (audit evidence — T-04-06-SC)

> **package-legitimacy gate T-04-06-SC: `google-api-python-client>=2.190`,
> `google-auth>=2.40`, `google-auth-oauthlib>=1.2` approved by operator, verified
> official on PyPI 2026-06-06** — `google-api-python-client` 2.197, `google-auth` 2.53,
> `google-auth-oauthlib` 1.4 confirmed OFFICIAL Google packages (publisher Google LLC /
> Google Cloud Platform; homes `googleapis/google-api-python-client` and
> `googleapis/google-auth-library-python`). Approved to declare them in the `tools`
> optional extra for the live lane; resume-signal "approved".

These three packages were already declared in the `tools` optional extra by 04-01
(commit `78f9717`); this gate blesses them for the 12-month supply-chain audit. They
were **NOT** installed into the default lane (extras are opt-in; the lazy import keeps
the module importable creds-free).

## What Was Built

### Task 1 — GWS shared auth scaffold + single dispatcher (Drive/Gmail/Sheets) + tests + doc

- **`tools/adapters/google_workspace.py`**:
  - `_build_credentials(credential, scopes)` — lazy-imports `google.oauth2.credentials`,
    parses the `{client_id, client_secret, refresh_token}` blob, returns an
    auto-refreshing `Credentials(token=None, refresh_token=..., token_uri=
    "https://oauth2.googleapis.com/token", client_id=..., client_secret=...,
    scopes=...)`. **Shared by every op and reused unchanged by 04-07** — the only per-op
    variation is the scopes list.
  - `_service(product, version, creds)` — thin lazy-import seam over
    `googleapiclient.discovery.build`.
  - Three op functions `(spec, params, *, credential) -> dict | None`: `_drive_search`
    (read, `drive.readonly`), `_gmail_send` (external_send, `gmail.send`), `_sheets_append`
    (write, `spreadsheets`). Each guards `credential is None -> return None` BEFORE any
    creds build (D-11 defensive), and maps the google response to the authored output
    schema.
  - `_GWS_OPS = {"google_drive_search": ..., "gmail_send": ..., "google_sheets_append": ...}`
    + a single `google_workspace_adapter(spec, params, *, credential)` doing
    `_GWS_OPS.get(spec.name)(...)` (unknown name -> `None` -> stub).
  - **EXACTLY ONE** `register("google_workspace", google_workspace_adapter)` — one
    dispatcher per provider key (04-03 invariant). 04-07 extends `_GWS_OPS` in place
    with Calendar/Docs/Slides with NO new register call.
- **`tests/test_gws_adapter.py`** (default lane, 6 tests): module imports SDK-free;
  ONE dispatcher reachable via `get_adapter("google_workspace")` (proves registration,
  not just a source string); **routing regression guard** (Drive vs Sheets reach
  DIFFERENT ops — not last-wins); credential-None -> None BEFORE `_build_credentials`
  (monkeypatched to raise); unknown name -> None; Drive read maps a fake `Files.list`
  response to the strict output schema (validated via `validate_output(_load(real_ref))`,
  absent optionals omitted).
- **`tests/test_gws_live.py`** (opt-in): `pytestmark = pytest.mark.live` + own
  `GOOGLE_WORKSPACE_OAUTH` skip fixture (NOT `live_creds`); one real
  `google_drive_search` through `gateway.execute(call, resolver=EnvCredentialResolver())`,
  asserting a non-stub, non-quarantined, schema-conforming result.
- **`docs/credentials/google_workspace.md`** (D-12): OAuth client (Desktop) creation,
  one-time `InstalledAppFlow` consent (`access_type="offline", prompt="consent"`) to mint
  the refresh token, the `GOOGLE_WORKSPACE_OAUTH` blob shape, per-product least-privilege
  scopes for Drive/Gmail/Sheets, and a "Calendar/Docs/Slides — see 04-07" placeholder.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Escape single-quotes in the Drive `q` query**
- **Found during:** advisor review at completion (a latent live-lane crash the
  default suite could not catch — the read path runs only in the opt-in live lane).
- **Issue:** `_drive_search` f-string-interpolated the raw query into the Drive
  `q` grammar (`fullText contains '{query}'`). The grammar single-quotes the literal,
  so a query containing an apostrophe (common: "O'Brien", "client's deck") produced
  malformed query syntax and the real API call would error — breaking the plan's
  must-have "google_drive_search executes a real Drive call".
- **Fix:** escape backslashes then single-quotes
  (`query.replace("\\", "\\\\").replace("'", "\\'")`) before interpolation. Added a
  unit test (`test_drive_search_escapes_single_quote_in_query`) capturing the `q`
  kwarg and asserting the escaped form. No impact on the green suite or any acceptance
  grep.
- **Files modified:** src/agent_mesh/tools/adapters/google_workspace.py,
  tests/test_gws_adapter.py
- **Commit:** `c5cdc71`

### Note

The plan's `<verify>` block writes `python`; the environment requires
`.venv/bin/python` — used throughout, not a code deviation.

### Inspection-only coverage (within plan scope)

The plan scopes the mapping unit test to the Drive read only; `_gmail_send` /
`_sheets_append` mappings are inspection-verified (both write-class and approval-gated,
so unrunnable in this lane). Their output schemas are `additionalProperties: true`
(low-risk); the dangerous strict `additionalProperties: false` schema is Drive's, which
IS schema-validated in a unit test.

## Verification

- `PYTHONPATH=src .venv/bin/python -m pytest -q -m "not live"` -> **172 passed, 6 skipped,
  5 deselected** (baseline 165/6/4; +7 adapter tests including the quote-escape guard).
  Creds-free; no provider SDKs installed.
- `PYTHONPATH=src .venv/bin/python -m pytest -q -m live tests/test_gws_live.py` -> **1
  skipped** when `GOOGLE_WORKSPACE_OAUTH` unset (SKIPS, does not error). Collects under
  `--co -q`.
- `import agent_mesh.tools.adapters.google_workspace` succeeds with
  `google-api-python-client` NOT installed (lazy import confirmed).
- `ruff check` on all three new files -> All checks passed.
- Acceptance greps:
  - `grep -c refresh_token …google_workspace.py` = 3 (>=1) ✓
  - `grep -v '^#' …google_workspace.py | grep -c 'register('` = 1 (==1), registers key
    `"google_workspace"` ✓
  - `grep -c 'google_drive_search\|gmail_send\|google_sheets_append' …` = 7 (>=3) ✓
  - routing test proves Drive vs Sheets reach DIFFERENT ops via the one dispatcher ✓
  - default-lane test asserts `get_adapter("google_workspace")` returns a callable via
    import-time registration ✓
  - live test SKIPS (not error) without `GOOGLE_WORKSPACE_OAUTH` ✓
  - `grep -c 'googleapis.com/auth/drive\|.../gmail.send\|.../spreadsheets' doc` = 7 (>=2) ✓
  - module imports WITHOUT the SDK installed ✓

## Must-Haves Coverage (from PLAN frontmatter)

- "google_drive_search executes a real Drive call through the gateway with OAuth resolved
  at execution time and auto-refreshed (TOOL-01, D-08)" -> `_drive_search` +
  `_build_credentials` (auto-refresh `Credentials`); live test runs it through
  `execute(call, resolver)` ✓
- "gmail_send + google_sheets_append stay approval-gated; reached only after the ledger
  approves (D-08)" -> both manifest-declared `approval_required: true` (unchanged by this
  plan); the gateway never dispatches a write-class call without approval; the adapter
  only implements the post-approval execution ✓
- "GOOGLE_WORKSPACE_OAUTH absent -> deterministic stub; make test green + creds-free
  (D-11)" -> credential-None -> None sentinel -> gateway stub fallback;
  `test_credential_none_degrades_to_stub_before_any_creds_build` ✓
- "one OAuth client + refresh token covers all six products via a single
  google-api-python-client (shared scaffold, D-08)" -> `_build_credentials` + `_service`
  shared across ops; 04-07 reuses them unchanged ✓
- "GWS registers EXACTLY ONE dispatcher under key google_workspace routing by spec.name —
  NOT one register per op" -> single `register("google_workspace", ...)`; routing
  regression guard test ✓

## Threat Model Coverage

- **T-04-06-01 (Information disclosure — refresh token / client secret leak)** —
  MITIGATED. `GOOGLE_WORKSPACE_OAUTH` is resolved only inside `execute()` (04-03), passed
  to the adapter by keyword, and never returned in the result, set as a span attribute, or
  logged. The doc instructs storing it as a secret env var, not in code.
- **T-04-06-02 (EoP — gmail_send / sheets_append without approval)** — MITIGATED. Both are
  write-class (`external_send` / `write`) -> `approval_required: true` in the manifest;
  reached only after the existing ledger approves. Reads (`google_drive_search`) are
  ungated by design (read category).
- **T-04-06-03 (Spoofing — over-broad OAuth scopes)** — MITIGATED. Least-privilege scopes
  per product (`drive.readonly` / `gmail.send` / `spreadsheets`), documented and requested
  explicitly; NOT the full `drive` scope (RESEARCH A7).
- **T-04-06-SC (Tampering — google client libs supply chain)** — MITIGATED. The
  blocking-human package-legitimacy gate was satisfied by the operator (verified official
  on PyPI 2026-06-06); audit line recorded above. Packages NOT installed into the default
  lane.

No high-severity threat left open.

## Known Stubs

The no-credential / no-adapter fallback returns the deterministic stub dict by design
(D-11) — the intended creds-free default-lane behavior, not an undelivered goal. The live
lane (opt-in, `GOOGLE_WORKSPACE_OAUTH` present) exercises the real Drive/Gmail/Sheets
paths. No unintended stubs.

## Self-Check: PASSED

- `src/agent_mesh/tools/adapters/google_workspace.py` exists on disk.
- `docs/credentials/google_workspace.md` exists on disk.
- `tests/test_gws_adapter.py` and `tests/test_gws_live.py` exist on disk.
- All four files committed in this plan's feat commit (hash recorded in Commits below).

## Commits

- `2e2b063` feat(04-06): Google Workspace direct suite — Drive/Gmail/Sheets dispatcher + auth scaffold
- `b53aa3e` docs(04-06): complete Google Workspace direct-suite plan (initial SUMMARY)
- `c5cdc71` fix(04-06): escape single-quotes in the Drive search query (Rule 1)
- `<docs>` docs(04-06): record Drive-quote-escape deviation + commit hashes in SUMMARY
