# Phase 5: Reference Adapter Breadth - Research

**Researched:** 2026-06-07
**Domain:** Extending the Phase-4 Tool Gateway with new direct adapters + Xero-via-aggregator
**Confidence:** HIGH (framework reuse; integration seams read from source) / MEDIUM-LOW (Bitscale public API)

## Summary

Phase 5 is **pure additive fan-out over the Phase-4 framework** — no rearchitecture. The
Tool Gateway execution engine (`gateway.py`), the adapter-dispatch registry
(`adapters/__init__.py`), the JSON-Schema validation boundary (`validation.py`), and the
two-lane test pattern are all already built and verified (215 tests green creds-free).
Each new provider is an own-file `adapters/<provider>.py` module that calls
`register('<provider>', dispatcher)` once and routes by `spec.name` — exactly the HubSpot
template.

**The manifest already declares every Phase-5 provider entry** (`webflow_create_cms_item`,
`bitscale_enrich`, `calcom_list_bookings`/`calcom_create_booking`,
`clockify_read_time_entries`, `beehiiv_create_post`, `xero_read_invoices`/`xero_create_invoice`).
But those entries carry **no `input_schema_ref`/`output_schema_ref`** and **no schema files
exist**. Because `validate_tool_input` BLOCKS a `direct_api` tool with no schema (D-04
fail-closed), every direct adapter is unreachable until its schema files + manifest refs
are added. This is the load-bearing foundation work, and — like Phase 4 — it lands on TWO
shared files (`manifests/tool_pack_manifest.yaml`, plus schema files under `schemas/`),
which is the tightest serialization constraint of the phase.

**Xero:** the manifest currently declares it `nango_aggregator`. Evidence below recommends
**flipping it to `composio_aggregator`** — the Nango adapter is hardcoded GET-only over
httpx, so a financial WRITE (POST create-invoice) through Nango would require editing the
SHARED `nango.py` file (breaking the isolated-adapter model), whereas Composio's
`session.execute(tool=..., arguments=...)` is verb-agnostic and already handles writes.

**Primary recommendation:** One **foundation plan** owns ALL shared-file edits (manifest
schema-refs + entry tweaks, every new schema file, `pyproject.toml` if any SDK extra,
the `test_credential_docs.py` guard-list extensions, and the Xero style flip). Then
**isolated per-adapter plans** each touch only their own `adapters/<provider>.py` + tests +
`docs/credentials/<provider>.md`. Prefer **httpx-direct** for every direct adapter (the
Phase-4 Nango precedent — no new pyproject extra, no SDK supply-chain gate). Bitscale has
**no public REST API** (early-access only) — recommend routing it through the aggregator or
shipping a deferred stub.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Webflow CMS item create (publishing write) | API / Backend (adapter) | — | Tool Gateway execution-time call; approval-gated upstream in worker |
| Bitscale enrichment (read) | API / Backend (adapter) | Aggregator | No public direct API → aggregator or deferred stub |
| Cal.com bookings read/write | API / Backend (adapter) | — | Direct REST; write approval-gated upstream |
| Clockify time-entries read | API / Backend (adapter) | — | Direct REST, X-Api-Key |
| Beehiiv post-create (publishing write) | API / Backend (adapter) | — | Direct REST; approval-gated upstream |
| Xero invoices read + create (financial) | API / Backend (Composio aggregator) | — | Managed-auth Tool Router; financial write approval-gated upstream |
| Credential resolution | Existing `CredentialResolver` | — | Reused unchanged; resolved only inside `execute()` (D-02) |
| Schema validation | Existing `validation.py` boundary | — | Reused unchanged; direct = fail-closed, aggregate = runtime/permissive |
| Approval gating (writes) | Existing worker approval ledger | — | Adapters are pure executors; NEVER self-gate (D-07) |
| OTel tool-event span | Existing `tool_event_span` in `execute()` | — | One span per call, reused unchanged |

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TOOL-03 | Reference-provider breadth: Webflow, Bitscale, Cal.com, Clockify, Beehiiv direct adapters + Xero via aggregator, each independently landable/testable, reusing the Phase-4 framework | Per-provider API/auth/op tables + plan split + integration-seam constraints below |

## Integration Seams — UNMISSABLE (Phase-4 lessons a fresh planner WILL miss)

These are read directly from Phase-4 source. Violating any one reproduces a real Phase-4
defect.

1. **Manifest + schema files + pyproject are SHARED-FILE serialization points.** Each
   provider op needs: (a) a manifest entry with `input_schema_ref`+`output_schema_ref` in
   `manifests/tool_pack_manifest.yaml`, (b) two schema files under `schemas/`, and possibly
   (c) a `pyproject.toml` extra. Phase 4 solved parallel-adapter collisions by front-loading
   ALL of this into ONE foundation plan (04-01) so per-adapter plans touched only their own
   `adapters/<provider>.py` + tests + doc. **Do the same.** `[VERIFIED: 04-01-PLAN.md files_modified]`

2. **D-04 fail-closed BLOCKS a direct tool with no schema at EXECUTE time.**
   `validation.validate_tool_input` raises `InputSchemaViolation("direct tool with no schema
   is BLOCKED")` for any `direct_api` spec whose `input_schema_ref is None`. The manifest
   entries exist today but are dormant precisely because they have no refs (so the engine
   never reaches them — they'd block). **Adding the schema refs + files is what makes each
   direct adapter reachable.** `[VERIFIED: validation.py:102-105]`

3. **ONE `register('<provider>', dispatcher)` per provider, routing by `spec.name`.** NOT one
   `register()` per op — last-wins collision makes ops unreachable (the real HubSpot defect
   the test `test_single_dispatcher_routes_distinct_ops` guards). Cal.com (2 ops) MUST use a
   single dispatcher with an internal `_CALCOM_OPS = {name: fn}` map, exactly like HubSpot's
   `_HS_OPS`. `[VERIFIED: hubspot.py:121-138, adapters/__init__.py:17-20]`

4. **Dispatch key derivation (`adapter_key_for`):** `direct_api` → `spec.provider`;
   `composio_aggregator` → `"composio"`; `nango_aggregator` → `"nango"`. So a direct
   adapter module filename + `register()` key + `spec.provider` must all match (`webflow`,
   `bitscale`, `calcom`, `clockify`, `beehiiv`). Xero-via-Composio reuses the EXISTING
   `composio.py` adapter — **no new Xero adapter module** — it just needs a manifest entry
   with `integration_style: composio_aggregator` + `resource_bindings.tool_slug`. `[VERIFIED: adapters/__init__.py:95-101, composio.py:55-67]`

5. **Lazy-import-on-miss + stub fallback (D-11).** `get_adapter(key)` does
   `importlib.import_module(f"agent_mesh.tools.adapters.{key}")` on a registry miss and
   swallows `ImportError` → `None` → engine stubs. Adapter modules must `register()` at
   module top, lazy-import any SDK INSIDE the function, and return `None` on
   `credential is None` / `ImportError`. **Prefer httpx (a core dep) → no ImportError risk at
   all.** `[VERIFIED: adapters/__init__.py:80-92, nango.py:89-91]`

6. **Credential resolved ONLY inside `execute()`; never logged/returned/span'd (D-02).** The
   adapter receives `credential` by keyword, uses it, and the engine drops it on return. Do
   NOT put it in the result dict or read it from a span. `[VERIFIED: gateway.py:176-211]`

7. **Writes stay approval-gated UPSTREAM in the worker — adapters NEVER self-gate (D-07).** A
   `category: write/financial/publishing/external_send` tool reaches the adapter only after
   the payload-hash-bound approval ledger approves. The adapter is a pure executor.
   `spec.validate()` enforces `approval_required: true` for write-class categories at load.
   `[VERIFIED: gateway.py:47-53 (ToolSpec.validate), hubspot.py:79-118]`

8. **Output schema mismatch QUARANTINES (does not discard).** `execute()` runs
   `validate_output` post-call; a violation returns `{"outcome":"output_quarantined", ...}`
   with the result preserved. **Shape each output schema to what the API REALLY returns** or
   real calls quarantine. `[VERIFIED: gateway.py:213-233]`

9. **The credential-docs guard (`tests/test_credential_docs.py`) is a SHARED FILE Phase 5
   must extend.** Its `_LIVE_TEST_FILES`, `_PROVIDER_DOCS`, `_ANCHOR_ENV_VARS`,
   `_MIN_ENV_VARS=7` are HARDCODED and deliberately exclude Phase-5 providers (the source
   comment names them). Success criterion 4 (docs extended) has **zero enforcement** unless
   these lists grow. **Assertion direction (verified):** it derives the live-lane env-var
   union from `os.getenv(...)` reads in ADAPTER SOURCE + literals in the four live-test
   files. Phase-4 direct adapters resolve creds via the manifest resolver (NO `os.getenv` —
   e.g. `hubspot.py`), so a Phase-5 direct adapter that does the same will NOT trip the
   "must be documented" union — meaning the guard won't auto-fail, BUT it also won't enforce
   the new docs unless you extend `_PROVIDER_DOCS`/`_LIVE_TEST_FILES`/`_MIN_ENV_VARS`. Treat
   extending these four lists + the floor as a shared-file edit owned by the foundation (or
   final-docs) plan. `[VERIFIED: tests/test_credential_docs.py:44-67, 70-112]`

10. **`docs/credentials/README.md` index/matrix is a serialization point; per-provider
    `<provider>.md` files are isolated.** Mirror Phase 4: per-adapter plans append their own
    `docs/credentials/<provider>.md`; a final docs plan updates the shared README index +
    matrix + the guard. `[VERIFIED: docs/credentials/README.md, hubspot.md]`

## Standard Stack

### Core (reused, unchanged — DO NOT re-architect)
| Component | Location | Purpose |
|-----------|----------|---------|
| Tool Gateway engine | `src/agent_mesh/tools/gateway.py` | resolve→validate→dispatch→span chokepoint |
| Adapter registry | `src/agent_mesh/tools/adapters/__init__.py` | `register()` / `get_adapter()` / `adapter_key_for()` |
| Validation boundary | `src/agent_mesh/tools/validation.py` | Draft 2020-12; direct=fail-closed, aggregate=runtime |
| Credential resolver | `src/agent_mesh/tools/credentials.py` | `EnvCredentialResolver` local; SecretManager in prod |
| Composio adapter | `src/agent_mesh/tools/adapters/composio.py` | REUSED for Xero (verb-agnostic `session.execute`) |
| HubSpot adapter | `src/agent_mesh/tools/adapters/hubspot.py` | the DIRECT-adapter TEMPLATE (single dispatcher / `_HS_OPS`) |

### Supporting (new code per provider)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `httpx` | already a CORE dep | REST calls for all 5 direct adapters | **Default choice** — no new extra, no SDK gate |
| `composio` | `>=0.13,<1` (already in `aggregators` extra) | Xero via Composio | Already declared; opt-in; no new dep needed |

### Alternatives Considered (SDKs — REJECTED in favor of httpx)
| Instead of httpx | Could Use | Tradeoff / Provenance |
|------------------|-----------|------------------------|
| Webflow httpx | `webflow` PyPI 2.0.0 | `[ASSUMED]` — registry-exists only; not confirmed official via Webflow docs. httpx avoids the supply-chain gate. |
| Beehiiv httpx | `beehiiv` PyPI 0.2 | `[ASSUMED]` — v0.2, single release, unverified publisher → SLOP-risk. **Do NOT install.** Use httpx. |
| Clockify httpx | `clockify-api-client` PyPI | `[ASSUMED]` — third-party, low maturity. Use httpx. |
| Cal.com httpx | (no official Python SDK found) | httpx is the only sane path. |

**Installation:** No new dependencies required if all direct adapters use httpx. The
`composio` extra for Xero already exists. If a planner insists on any SDK, it MUST pass the
Package Legitimacy Gate first and be tagged accordingly.

## Package Legitimacy Audit

> Recommendation is **httpx-direct for all 5 direct adapters → no new package installs**.
> The only optional SDK in play (`composio`) was already audited + operator-approved in
> Phase 4. The table below records the SDKs considered-and-rejected so a planner does not
> re-propose them without the gate.

| Package | Registry | Notes | slopcheck | Disposition |
|---------|----------|-------|-----------|-------------|
| `httpx` | PyPI (core dep) | already installed, used by `nango.py` | n/a (existing) | Approved (reuse) |
| `composio` | PyPI `>=0.13,<1` | already in `aggregators` extra, Phase-4 approved | n/a (existing) | Approved (reuse for Xero) |
| `webflow` | PyPI 2.0.0 | provenance unconfirmed via official docs | not run | REJECTED — use httpx; `[ASSUMED]` if reconsidered |
| `beehiiv` | PyPI 0.2 | single release, SLOP-risk | not run | REJECTED — use httpx |
| `clockify-api-client` | PyPI | third-party, low maturity | not run | REJECTED — use httpx |

**Packages removed due to [SLOP] verdict:** none run (httpx-direct avoids the gate entirely).
**Packages flagged [SUS]:** the three SDKs above are pre-emptively rejected; if any is later
adopted, the foundation plan MUST run slopcheck + register an SDK extra in `pyproject.toml`
and gate install behind a `checkpoint:human-verify` task (Phase-4 precedent for
`hubspot-api-client` / `composio`).

## Per-Provider API Reference

> READ ops are `category: read`, `approval_required: false`. WRITE/publishing/financial ops
> are approval-gated upstream. Output schemas must match the REAL response shape (quarantine
> risk). Inputs: permissive-with-required (Phase-4 `gmail_send` style).

### Webflow (`provider: webflow`, direct_api, httpx)
- **API base:** `https://api.webflow.com/v2` `[CITED: developers.webflow.com/data/reference/authentication]`
- **Auth:** Bearer token (Site Token simplest for single-site internal use). Header:
  `Authorization: Bearer <WEBFLOW_API_TOKEN>`, `Accept: application/json`. `[CITED]`
- **Existing manifest entry:** `webflow_create_cms_item` (publishing write). **Add a READ
  op** `webflow_list_cms_items` to satisfy the read+write breadth goal.
- **READ — `webflow_list_cms_items`:** `GET /v2/collections/{collection_id}/items`, scope
  `CMS:read`. Response: `{ "items": [ {id, isDraft, fieldData{...}, lastPublished, ...} ], "pagination": {...} }`. `[CITED: developers.webflow.com/data/reference]`
- **WRITE — `webflow_create_cms_item`:** `POST /v2/collections/{collection_id}/items`, scope
  `CMS:write`, body `{ "isDraft": true, "fieldData": { "name": <str>, "slug": <str>, ... } }`.
  Response HTTP 202 `{ id, lastPublished, lastUpdated, createdOn, fieldData{...} }`.
  **Keep `isDraft: true`** (never publish). `[CITED: developers.webflow.com/data/reference/cms/collection-items/staged-items/create-item]`
- **Cred doc:** mint a **Site Token** (Webflow site → Settings → Apps & Integrations → API
  Access → Generate token) with scopes `CMS:read` + `CMS:write`. `resource_bindings`:
  `site_id`, `collection_id`. Env: `WEBFLOW_API_TOKEN`.
- **Gotcha:** create returns 202 (accepted, async stage), not 200. Rate limit 60–120 req/min
  by plan.

### Bitscale (`provider: bitscale`, direct_api **AT RISK**)
- **No public REST API.** Bitscale's API is "coming soon / early-access program only" — no
  public endpoint, auth model, or schema is documented. `[VERIFIED: WebSearch — docs.bitscale.ai shows only a custom-API *integration* ingredient + an early-access waitlist; no enrichment REST endpoint]`
- **Existing manifest entry:** `bitscale_enrich` (read). It is enrichment/scraping — a
  read-only adapter is legitimate; **do NOT invent a write op.**
- **Recommendation (decision #2 / Bitscale):** **Two viable fallbacks, pick one in
  planning:**
  1. **Keep it a deterministic gateway stub** (the entry stays, no adapter module ships,
     `get_adapter('bitscale')` import-misses → stub). Lowest risk; success criterion 1
     ("working direct adapter … with schema validation") is then only PARTIALLY met for
     Bitscale → flag to orchestrator/user.
  2. **Route via the aggregator** if Composio/Nango lists Bitscale (NOT confirmed —
     Composio toolkit search did not surface Bitscale). If chosen, re-style the manifest
     entry `composio_aggregator` and add a `tool_slug`.
- **My recommendation:** ship the **schema + manifest ref + a thin httpx adapter scaffold
  guarded to stub** so the schema-validation criterion is met deterministically, and
  surface to the user that Bitscale has no live direct API yet. This is a genuine
  user-surfaceable decision.

### Cal.com (`provider: calcom`, direct_api, httpx)
- **API base:** `https://api.cal.com/v2` `[CITED: cal.com/docs/api-reference/v2]`
- **Auth:** `Authorization: Bearer <CALCOM_API_KEY>` (key prefixed `cal_`). **REQUIRED
  header:** `cal-api-version: 2026-05-01` for bookings. `[CITED: cal.com/docs/api-reference/v2/bookings/get-all-bookings]`
- **Existing manifest entries:** `calcom_list_bookings` (read) + `calcom_create_booking`
  (write) — both already declared. Cal.com is the one provider with a natural read+write
  pair.
- **READ — `calcom_list_bookings`:** `GET /v2/bookings` (+ `cal-api-version` header).
  Response: `{ "status": "success", "data": [ {id, uid, title, status, start, end, attendees[...], eventTypeId, ...} ], "pagination": {nextCursor, hasMore} }`. `[CITED]`
- **WRITE — `calcom_create_booking`:** `POST /v2/bookings` (+ `cal-api-version` header),
  body includes `start`, `eventTypeId` (from `resource_bindings.event_type_id`),
  `attendee{name,email,timeZone}`. Response `{status, data:{id, uid, ...}}`. OAuth scope
  `BOOKING_READ`/`BOOKING_WRITE` if OAuth instead of API key. `[CITED]`
- **Cred doc:** mint API key — Cal.com → Settings → Developer → API Keys. Env:
  `CALCOM_API_KEY`. `resource_bindings.event_type_id` for create.
- **Gotcha:** the `cal-api-version` header is mandatory and version-dated; pin
  `2026-05-01` and document it (a missing/wrong version 400s).

### Clockify (`provider: clockify`, direct_api, httpx)
- **API base:** `https://api.clockify.me/api/v1` `[CITED: docs.clockify.me]`
- **Auth:** header `X-Api-Key: <CLOCKIFY_API_KEY>` (NOT Bearer). `[CITED]`
- **Existing manifest entry:** `clockify_read_time_entries` (read only). Read-only is fine;
  **optionally add** `clockify_create_time_entry` (write) for breadth — decide in planning
  (each op = a manifest entry + schema files).
- **READ — `clockify_read_time_entries`:**
  `GET /workspaces/{workspaceId}/user/{userId}/time-entries`. Response: array of
  `{id, description, timeInterval:{start,end,duration}, projectId, ...}`. `[CITED]`
- **WRITE (optional) — `clockify_create_time_entry`:**
  `POST /workspaces/{workspaceId}/time-entries`, body `{start, end, description, projectId?}`.
- **Cred doc:** mint API key — Clockify → Profile Settings → API → Generate. **Subdomain
  workspaces need a subdomain-specific key.** Env: `CLOCKIFY_API_KEY`.
  `resource_bindings.workspace_id` (+ a `user_id` for the read path — `GET /user` returns
  the caller's id, or bind it). `[CITED]`
- **Gotcha:** the read endpoint needs BOTH workspaceId and userId; resolve userId via
  `GET /user` once or add it to `resource_bindings`.

### Beehiiv (`provider: beehiiv`, direct_api, httpx)
- **API base:** `https://api.beehiiv.com/v2` `[CITED: developers.beehiiv.com]`
- **Auth:** `Authorization: Bearer <BEEHIIV_API_KEY>`. `[CITED]`
- **Existing manifest entry:** `beehiiv_create_post` (publishing write). **Optionally add a
  READ** `beehiiv_list_posts` (`GET /v2/publications/{publicationId}/posts`, scope
  `posts:read`) for breadth — decide in planning.
- **WRITE — `beehiiv_create_post`:** `POST /v2/publications/{publicationId}/posts`, scope
  `posts:write`, body **required `title`**, set `"status": "draft"` (never auto-publish),
  optional `body_content`/`blocks`, `subtitle`. Response HTTP 201
  `{ "data": { "id": <prefixed-post-id> } }`. `[CITED: developers.beehiiv.com/api-reference/posts/create]`
- **Cred doc:** mint API key — Beehiiv → Settings → Integrations → API (Developers →
  Create an API Key). Env: `BEEHIIV_API_KEY`. `resource_bindings.publication_id`.
- **Gotcha:** create-post is **beta / Enterprise-tier-gated**; a non-Enterprise key may
  403. Document this caveat. Response nests under `data` (output schema must match
  `{data:{id}}`, NOT a flat `{id}`).

### Xero (`provider: xero`, **flip to composio_aggregator**, financial)
- **DECISION #1 RESOLVED → Composio (primary).** `[VERIFIED: source nango.py:97-107 is hardcoded GET; composio.py:67 session.execute is verb-agnostic]`
  - Composio's Xero toolkit lists a **Create Invoice** action + List Invoices. `[CITED: composio.dev/toolkits/xero, composio.dev/tools/xero/all]`
  - Nango also supports Xero invoices `[CITED: nango.dev/docs/api-integrations/xero]`, BUT the
    repo's `nango.py` adapter issues only `httpx.request("GET", ...)`. A financial WRITE
    (POST create-invoice) through Nango would require editing the **shared** `nango.py`
    aggregator file — breaking the isolated-adapter model and touching a file other
    aggregator tools depend on. Composio's `session.execute(tool=..., arguments=...)` handles
    writes with **zero adapter code change** (reuse the existing `composio.py`).
- **Action:** in `manifests/tool_pack_manifest.yaml`, change `xero_read_invoices` and
  `xero_create_invoice` from `integration_style: nango_aggregator` →
  `composio_aggregator`, add `resource_bindings.tool_slug` (e.g. `XERO_LIST_INVOICES` /
  `XERO_CREATE_INVOICE` — confirm exact slugs against Composio's catalog at impl) and a
  `user_id` binding, and change `credential_secret_name` to `COMPOSIO_API_KEY` (Composio
  brokers the Xero OAuth). No `input_schema_ref` (aggregate tools validate against the
  runtime provider schema — D-04 permissive).
- **READ — `xero_read_invoices`:** Composio `XERO_LIST_INVOICES`. `category: read`.
- **WRITE — `xero_create_invoice`:** Composio `XERO_CREATE_INVOICE`, **draft only** (never
  auto-finalise — `Status: DRAFT`). `category: financial`, `approval_required: true` — gated
  upstream by the existing ledger.
- **Cred doc:** Composio dashboard → connect the Xero toolkit (Composio handles the Xero
  OAuth handshake + tenant). Env: `COMPOSIO_API_KEY` (already documented in `composio.md` —
  Xero rides the SAME key, so no NEW env var; the cred doc just needs a Xero-toolkit note).
- **Flag to orchestrator/user:** this overrides the manifest's current `nango_aggregator`
  declaration. Surface as a confirmable decision — the rationale is code-structural, but the
  user owns the financial-write provider choice.

## Recommended Plan Split

**Constraint that dictates the split:** the manifest, every schema file, `pyproject.toml`,
and `tests/test_credential_docs.py` are SHARED. Per-adapter `adapters/<provider>.py`,
per-provider tests, and per-provider `docs/credentials/<provider>.md` are ISOLATED.

### Plan 05-01 — Foundation (shared-file edits ONLY) [wave 1]
**Owns (may touch ONLY these):**
- `manifests/tool_pack_manifest.yaml` — add `input_schema_ref`/`output_schema_ref` to every
  Phase-5 direct entry; add any NEW op entries decided (webflow read; optional clockify
  write / beehiiv read); **flip Xero entries to `composio_aggregator` + `tool_slug` +
  `COMPOSIO_API_KEY`**.
- `schemas/<provider>_<op>.input.schema.json` + `.output.schema.json` for every direct op
  (Draft 2020-12, inputs permissive-with-required, outputs matching the real response
  shapes documented above). Aggregate (Xero) tools get NO schema files.
- `pyproject.toml` — ONLY if an SDK extra is adopted (recommended: none; httpx-direct).
- `tests/test_credential_docs.py` — extend `_LIVE_TEST_FILES`, `_PROVIDER_DOCS`,
  `_ANCHOR_ENV_VARS`, raise `_MIN_ENV_VARS` to cover the new providers (so success
  criterion 4 is actually enforced).
**Success:** `make test` green creds-free; every Phase-5 direct manifest entry has both
schema refs and on-disk schema files; Xero styled `composio_aggregator`.

### Plans 05-02 … 05-06 — Isolated per-direct-adapter [wave 2, all depend on 05-01, mutually parallel]
One plan per provider. Each **may touch ONLY:**
- `src/agent_mesh/tools/adapters/<provider>.py` (single `register('<provider>', dispatcher)`,
  routes by `spec.name`, httpx, lazy/stub fallback)
- `tests/test_<provider>_adapter.py` (default lane — fake httpx, schema-shape assert,
  collision guard if 2 ops) + `tests/test_<provider>_live.py` (opt-in, skips on missing env)
- `docs/credentials/<provider>.md` (isolated; mint steps + scopes + env var)

Providers: `webflow`, `calcom`, `clockify`, `beehiiv`, and `bitscale` (bitscale ships the
stub-guarded scaffold per the Bitscale decision). **Cal.com is the only 2-op dispatcher**
(use `_CALCOM_OPS`).

### Plan 05-07 — Xero-via-Composio + shared docs index [wave 2 or 3]
**Owns:**
- `tests/test_xero_live.py` (opt-in; exercises `xero_read_invoices` through the EXISTING
  `composio.py` adapter — no new adapter module). Default-lane coverage rides the existing
  `test_aggregator_adapters.py` registry assertions.
- `docs/credentials/xero.md` (Composio-toolkit connection note; reuses `COMPOSIO_API_KEY`).
- `docs/credentials/README.md` — the SHARED index/matrix update (link all new
  per-provider docs + skip matrix rows). Since README is shared, give it to exactly ONE
  plan (this one) to avoid serialization collisions.

**Wave ordering:** 05-01 (foundation) → {05-02..05-06 parallel} → 05-07 (docs index +
Xero). 05-07's README edit must be the sole owner of that file. If the credential-docs
guard extension (in 05-01) references new live-test filenames, ensure those filenames match
what the per-adapter plans create (name them in 05-01's contract).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Credential resolution | per-adapter env reads | existing `CredentialResolver` passed into `execute()` | D-02 leak-safety; resolved once in the chokepoint |
| Schema validation | bespoke per-adapter checks | existing `validation.py` boundary (manifest refs) | D-04/D-06 fail-closed/quarantine semantics already correct |
| Approval gating | adapter-level gates | existing upstream worker ledger | D-07; adapters are pure executors |
| OTel spans | manual span per adapter | the single `tool_event_span` in `execute()` | one span per call, already correlated |
| Adapter registration plumbing | edits to `gateway.py` | own-file `adapters/<provider>.py` + `register()` | keeps Wave-2 parallel; no shared-file edit |
| Xero write transport | new Nango POST path in shared `nango.py` | existing `composio.py` `session.execute` | verb-agnostic; zero shared-adapter edit |

**Key insight:** Phase 5 should add ZERO lines to `gateway.py`, `adapters/__init__.py`,
`validation.py`, `credentials.py`, `composio.py`, `nango.py`. If a plan proposes editing any
of those, it has misread the framework.

## Common Pitfalls

### Pitfall 1: Direct adapter ships without schema files → silently stubs/blocks
**What goes wrong:** an adapter module is added but its manifest entry still has no
`input_schema_ref`, so `validate_tool_input` BLOCKS (input_rejected) before dispatch — the
adapter never runs and a live test "passes" by stubbing.
**Avoid:** foundation plan 05-01 lands ALL schema refs+files FIRST; per-adapter live tests
assert `result.get("stub") is not True` (Phase-4 `test_hubspot_live.py:63`).

### Pitfall 2: Output schema doesn't match real response → quarantine
**What goes wrong:** Beehiiv returns `{data:{id}}` not `{id}`; Cal.com wraps in
`{status,data,pagination}`; Webflow create returns 202 with `{id, fieldData, ...}`. A naive
flat output schema quarantines every real call.
**Avoid:** copy the documented response shapes above into the output schemas; set
`additionalProperties:false` only on keys you actually emit (map the SDK/HTTP response into
the declared shape in the adapter, like `hubspot._lookup_company` does).

### Pitfall 3: register-per-op collision (Cal.com)
**What goes wrong:** `register('calcom', list_fn)` then `register('calcom', create_fn)` —
last wins, the read becomes unreachable.
**Avoid:** ONE `calcom_adapter` dispatcher + `_CALCOM_OPS = {name: fn}` (HubSpot template).

### Pitfall 4: Editing shared `nango.py`/`composio.py` for Xero write
**What goes wrong:** adding a POST branch to `nango.py` to support Xero create-invoice
couples Xero to a shared aggregator file and risks other aggregator tools.
**Avoid:** route Xero through Composio (verb-agnostic); leave `nango.py` untouched.

### Pitfall 5: Credential-docs guard not extended → criterion 4 unenforced
**What goes wrong:** new docs are written but `_PROVIDER_DOCS` still lists only the four
Phase-4 providers, so `test_credential_docs.py` never checks the new docs exist.
**Avoid:** 05-01 extends the four hardcoded lists + `_MIN_ENV_VARS`.

## Runtime State Inventory

> Phase 5 is additive code/config — no rename/migration. Still inventoried for completeness.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no datastore keys reference new providers. Verified: providers are new manifest entries only. | none |
| Live service config | None for the POC (no live SaaS provisioned this milestone — deploy-ready-only). New env vars (`WEBFLOW_API_TOKEN`, `CALCOM_API_KEY`, `CLOCKIFY_API_KEY`, `BEEHIIV_API_KEY`) are opt-in live-lane only. | document in cred docs |
| OS-registered state | None — no OS registrations involve these providers. | none |
| Secrets/env vars | New live-lane env var NAMES only (above). Xero reuses `COMPOSIO_API_KEY` (no new var). No real secrets in repo (T-04-09-01). | extend cred docs + guard |
| Build artifacts | None — no new compiled artifacts; httpx-direct adds no installed package. (If an SDK extra is wrongly adopted, a stale `.egg-info` could result — another reason to prefer httpx.) | none |

## State of the Art

| Old Approach | Current Approach | When | Impact |
|--------------|------------------|------|--------|
| Cal.com API v1 (`api.cal.com/v1`) | v2 (`api.cal.com/v2`) + dated `cal-api-version` header | v2 GA | use v2; pin `cal-api-version: 2026-05-01` |
| Webflow API v1 | Data API v2 (`api.webflow.com/v2`) | v1 deprecated | use v2; `CMS:read`/`CMS:write` scopes |
| Manifest Xero = `nango_aggregator` | recommend `composio_aggregator` | this phase | financial write needs verb-agnostic aggregator |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Bitscale has NO public direct REST API (early-access only) | Bitscale | If a public API exists, a real direct adapter is possible — re-check at impl; low risk (searched, found only waitlist) |
| A2 | Composio Xero `tool_slug`s are `XERO_LIST_INVOICES` / `XERO_CREATE_INVOICE` | Xero | Wrong slug → call fails; confirm against live Composio catalog at impl |
| A3 | `webflow`/`beehiiv`/`clockify-api-client` PyPI packages are non-authoritative (httpx preferred) | Standard Stack | Only matters if a planner adopts an SDK; httpx avoids it |
| A4 | Cal.com `cal-api-version: 2026-05-01` is the current bookings version | Cal.com | Wrong/stale version → 400; pinned per current docs, re-confirm at impl |
| A5 | Beehiiv create-post may be Enterprise-gated (403 on lower tiers) | Beehiiv | Affects live-lane only; default lane stubs regardless |

## Open Questions

1. **Bitscale direct vs stub vs aggregator** (decision #2). Recommendation: ship
   schema + stub-guarded scaffold and surface "no live direct API" to the user. Orchestrator
   may want to confirm.
2. **Optional complementary ops** (clockify write, beehiiv read, webflow read). Webflow read
   is recommended (rounds out the publishing provider); clockify-write / beehiiv-read are
   optional breadth. Each adds a manifest entry + 2 schema files to 05-01. Planner decides.
3. **Xero provider flip confirmation** (decision #1). Recommendation Composio is
   evidence-backed; user owns the financial-provider choice.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `httpx` | all 5 direct adapters | ✓ (core dep) | installed | — |
| `composio` SDK | Xero live lane | ✗ (opt-in `aggregators` extra) | `>=0.13,<1` | stub when absent (D-11) |
| Live provider creds | live lane only | ✗ (operator-supplied) | — | default lane stubs creds-free |

**Missing with no fallback:** none — default lane is creds-free and stubs everything.
**Missing with fallback:** all live creds + composio SDK — per-provider opt-in (D-11).

## Project Constraints (from CLAUDE.md)

- LangChain + LangGraph + Deep Agents + Langfuse remain REQUIRED; LangSmith never a dep
  (unaffected — no model/orchestration change this phase).
- **Human-in-the-loop write-approval gate holds for every write-class tool (payload-hash
  bound).** Xero financial write + Webflow/Beehiiv publishing writes + any Cal.com/Clockify
  writes stay `approval_required: true`, gated upstream. Adapters NEVER self-gate.
- No runtime autonomous self-modification (unaffected).
- Deep Agents roster stays bounded (unaffected).
- Durable stores in `australia-southeast1`; model processing may leave AU (unaffected — no
  new durable store).

## Sources

### Primary (HIGH confidence) — repo source verified this session
- `src/agent_mesh/tools/gateway.py`, `adapters/__init__.py`, `adapters/hubspot.py`,
  `adapters/composio.py`, `adapters/nango.py`, `validation.py`
- `manifests/tool_pack_manifest.yaml`, `pyproject.toml`,
  `tests/test_hubspot_adapter.py`, `tests/test_hubspot_live.py`,
  `tests/test_credential_docs.py`, `docs/credentials/README.md`, `docs/credentials/hubspot.md`
- `.planning/phases/04-.../04-01-PLAN.md` (shared-file ownership model), `.planning/ROADMAP.md`

### Secondary (MEDIUM confidence) — official provider docs
- Webflow: developers.webflow.com/data/reference/authentication + .../cms/collection-items/staged-items/create-item
- Cal.com: cal.com/docs/api-reference/v2/bookings/get-all-bookings
- Clockify: docs.clockify.me
- Beehiiv: developers.beehiiv.com/api-reference/posts/create
- Composio Xero: composio.dev/toolkits/xero, composio.dev/tools/xero/all
- Nango Xero: nango.dev/docs/api-integrations/xero

### Tertiary (LOW confidence) — flag for validation
- Bitscale: docs.bitscale.ai / bitscale.co.uk/documentation (early-access; NO public API surfaced)

## Metadata

**Confidence breakdown:**
- Framework reuse / integration seams: HIGH — read directly from Phase-4 source
- Plan split / shared-file constraints: HIGH — confirmed against 04-01-PLAN + the guard test
- Provider APIs (Webflow/Cal.com/Clockify/Beehiiv): MEDIUM — official docs, exact slugs/version
  to reconfirm at impl
- Xero-via-Composio decision: MEDIUM-HIGH — code-structural evidence + catalog confirmation
- Bitscale: LOW — no public API; fallback recommended

**Research date:** 2026-06-07
**Valid until:** ~2026-07-07 (provider APIs stable; Cal.com dated version header may roll)
