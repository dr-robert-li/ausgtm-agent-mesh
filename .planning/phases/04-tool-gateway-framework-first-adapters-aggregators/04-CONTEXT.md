# Phase 4: Tool Gateway Framework + First Adapters + Aggregators - Context

**Gathered:** 2026-06-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Turn the **Tool Gateway stub** (`tools/gateway.py` — today a pure echo) into a **real,
reusable execution engine**, and prove it across both integration styles:

- **Execution engine (TOOL-01):** execution-time credential resolution (Secret-Manager-shaped,
  env-backed locally; **agents never receive raw creds**), the loader carrying `integration_style`
  + schema refs it currently drops, and a real `execute()` path.
- **Schema boundary (TOOL-02):** JSON-Schema input/output validation at the tool boundary —
  permissive-by-design, fail-closed for direct tools, runtime-schema'd for aggregate tools.
- **Direct adapters (TOOL-01):** **HubSpot** (read + approval-gated write) and the **full Google
  Workspace suite** (Gmail, Calendar, Drive, Sheets, Docs, Slides) making **real local calls**.
- **Aggregators (TOOL-04):** **Composio** (primary, managed auth / MCP Tool Router) + **Nango**
  (fallback, self-hosted OSS) each exercised **end-to-end** with one real read call.
- **Observability:** close the **OBS-01 tool-event-span leftover** (deferred from Phase 3 because no
  adapters existed) — the engine emits tool-event OTel spans.
- **Deliverable:** **per-provider credential/scope setup docs** so the user can mint and supply creds.

Maps to: **TOOL-01, TOOL-02, TOOL-04** (and closes the OBS-01 tool-span gap).

**Re-scope origin (this session):** the user reframed the POC as an **MVP** — "I don't just want to
prove it works, I want viable general functionality." TOOL-03/04 were promoted **v2→v1**; the old
single "Phase 4: Tools & Self-Improvement" was split into **Phase 4 (this — tool framework + flagship
adapters + aggregators)**, **Phase 5 (reference-adapter breadth, TOOL-03)**, and **Phase 6
(self-improvement, SI-01/02)**; E2E/deploy moved to **Phase 7**. Milestone grew 5→7 phases. See the
updated `.planning/ROADMAP.md` and `.planning/REQUIREMENTS.md`.

**NOT this phase:** the 6 reference providers (Webflow, Bitscale, Cal.com, Clockify, Beehiiv, Xero)
→ Phase 5. The eval harness + AI-BOM-on-promotion (SI-01/02) → Phase 6. Ingress (Slack + Claude/MCP)
is **already built** (`api/app.py` `/slack/events`, `/mcp`, `/v1/approvals`) — not re-opened.

</domain>

<decisions>
## Implementation Decisions

### Master scope (the re-scope that shapes everything)
- **D-01:** **POC = MVP, full tool coverage in v1.** This phase delivers a genuinely reusable tool
  spine + the two flagship direct providers + both aggregator styles — **not** a one-adapter proof.
  Every provider must be **independently landable and testable**; the long tail (Phase 5) must be
  thin-adapter-plus-config on top of this engine, never a rearchitecture. (See memory
  [[poc-is-mvp-full-tool-coverage]].)

### Tool Gateway execution engine (TOOL-01)
- **D-02:** **Credential resolution at execution time, Secret-Manager-shaped, env-backed locally.**
  A `CredentialResolver` abstraction resolves by the manifest's `credential_secret_name` at
  `execute()` time; prod swaps the backing to real Secret Manager. **Agents never receive raw
  credentials** (CLAUDE.md §2/§5) — the gateway resolves them at call time only. The deterministic
  stub lane resolves nothing (stays creds-free).
- **D-03:** **Loader carries what it currently drops.** `ToolSpec` / `load_tool_pack` must surface
  `integration_style` and `input_schema_ref` / `output_schema_ref` (today silently discarded). The
  existing write-class invariant (`category ∈ WRITE_CATEGORIES ⇒ approval_required`) stays.

### Schema validation boundary (TOOL-02)
- **D-04:** **Validate against *a* schema, source depends on integration style.** Direct adapters
  validate against **our** manifest-declared schemas (files already exist in `schemas/`). Aggregate
  tools validate against the **aggregator/provider-supplied schema fetched at runtime** (Composio/Nango
  expose per-tool JSON Schemas — we cannot hand-author ~982 of them). **Fail-closed applies to direct
  tools only:** a direct tool with no declared schema is **blocked**. Fail-closed **never** applies to
  aggregate tools (their schema arrives at runtime).
- **D-05:** **Permissive-by-design authoring.** Schemas validate required fields + types and **allow
  additional properties by default**; tighten (`additionalProperties:false`, enums, bounds) only on
  cost/security-critical fields (e.g. a write tool's target IDs). This keeps the gate safe without
  being brittle — gate width is an authoring choice, not a property of validation.
- **D-06:** **Asymmetric input/output failure actions.** **Input** violation → **hard reject, no SaaS
  call made**, record a failed `tool_call`. **Output** violation → the call already happened, so
  **flag/quarantine** the result + record it and **halt downstream trust** rather than pretend it
  didn't run; validate primarily the output fields the agent consumes. The deterministic reject test
  (success criterion #2, default lane) uses a tool that **does** declare schemas.

### Direct adapters this phase (TOOL-01)
- **D-07:** **HubSpot = read + approval-gated write, on a dev/test sandbox.** `hubspot_lookup_company`
  (read, unconditional live call) **and** `hubspot_create_deal` (write, **approval-gated** through the
  existing ledger). Single bearer private-app token. Live writes hit a **HubSpot developer/test
  sandbox** so nothing mutates production data.
- **D-08:** **Google Workspace = full suite live.** User directive: prove the path **and** that all of
  Workspace works — **Gmail, Calendar, Drive, Sheets, Docs, Slides** as live direct adapters this
  phase (not a starter subset). Reads run unconditionally in the live lane; **writes/sends are
  approval-gated** (`external_send`/`write`/`publishing` categories). OAuth app + refresh-token;
  per-product scopes documented (D-12). Planner sets the per-product operation set (read + key writes).
  **Scope flag (D-08 × D-04):** "full GWS suite live" + "fail-closed for direct tools" means **every**
  GWS tool needs a manifest entry **and** input/output schemas. Today only `google_drive_search` has
  schemas; `gmail_send` / `google_sheets_append` have none, and Calendar/Docs/Slides aren't in the
  manifest at all — so this phase implies authoring ~6 products' worth of new manifest entries +
  schemas. Sizeable; the planner should treat adapter+manifest+schema as one unit per product (a
  candidate per-product plan split).

### Aggregators (TOOL-04)
- **D-09:** **Composio primary + Nango fallback; one real read each, end-to-end.** Composio (managed
  auth, MCP-native single Tool Router endpoint — Spike 001 winner) and Nango (self-hosted OSS unified
  API) each make **one real read call** through the gateway this phase. A **read** avoids approval-gate
  coupling and proves the **integration style** works end-to-end. The heavy provider matrix and any
  **write-through-aggregator** are **Phase 5**. Nango requires standing up a local/self-hosted Nango
  instance for its live lane.

### Observability (closes the OBS-01 leftover)
- **D-10:** **Tool-event OTel spans land here.** The engine emits an OTel span per tool call
  (`tool`, `provider`, `category`, `integration_style`, latency, `approval_state`, outcome) using the
  shared request metadata from `observability.trace_metadata()`, over the Phase-3 OTel transport. This
  closes the OBS-01 Gap-2 deferral ("no tool adapters existed until Phase 4"). It is an in-scope
  *consequence* of a real adapter existing — not new OBS scope.

### Live-lane discipline (carried from Phase 3 D-02)
- **D-11:** **Per-provider opt-in live-lane matrix.** Default `make test` / `make smoke` stay **green
  and creds-free** on the deterministic stub path. Real calls run only in a marked live lane, and
  **each provider (and each aggregator) is independently skippable when its creds are absent** —
  HubSpot, Google Workspace, Composio, and Nango each gate on their own credential presence.

### Credential setup docs (deliverable)
- **D-12:** **Per-provider credential/scope setup doc is a real Phase-4 deliverable.** For each
  provider requiring creds, document **how to mint the token/OAuth app and the exact scopes required**
  (HubSpot private-app token + scopes; Google Workspace OAuth client + per-product scopes for
  Gmail/Calendar/Drive/Sheets/Docs/Slides; Composio managed-auth setup; Nango self-host + connection
  setup). This is what lets the user supply creds for the live lane.

### Claude's Discretion (left to research + planning)
- Exact `CredentialResolver` interface + env-var naming convention; JSON-Schema validation library
  (`jsonschema`) and Draft version; where/how runtime aggregator schemas are fetched + cached.
- `ToolGateway.execute()` signature evolution and the failed-`tool_call` row shape.
- Per-product Google Workspace operation granularity (which read/write ops per product) within the
  "full suite live" boundary.
- Composio SDK-vs-MCP-endpoint binding into the gateway; depth of the Nango self-host setup for the
  live lane.
- OAuth refresh-flow mechanics for the Google Workspace live lane (how the refresh token is supplied/
  rotated in test).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Normative design & guardrails
- `CLAUDE.md` §3 "Tool Pack Contract" — tool manifest fields (name, category, integration style,
  scopes/creds, approval requirement, input/output JSON schema, resource identifiers); "loads tool
  manifests into the AI-BOM snapshot and exposes only approved tools; **agents never receive raw
  credentials; the Tool Gateway resolves credentials at execution time**."
- `CLAUDE.md` §2 — toolpacks are replaceable; integration styles `direct_api` / `mcp_server` /
  `aggregate_mcp` / `nango_aggregator` / `composio_aggregator`.
- `CLAUDE.md` §6 Acceptance Criteria — #11 (all write-class tools require approval via shared ledger,
  payload-hash bound), #12 (toolpack declares the providers each with an integration style), #13
  (direct / individual-MCP / aggregate-MCP / Nango / Composio styles; Composio & Nango peer options),
  #16 (Langfuse-centered observability — tool spans).
- `CLAUDE.md` §8 "Guardrails that survive every phase" — write-approval gate holds; bounded roster;
  required stack (LangChain/LangGraph/Deep Agents/**Langfuse**).

### Phase scope & requirements (UPDATED THIS SESSION)
- `.planning/ROADMAP.md` §"Phase 4: Tool Gateway Framework + First Adapters + Aggregators" — goal,
  success criteria, plan stubs; **plus the re-scope note** (5→7 phases). Also §Phase 5 (breadth) and
  §Phase 6 (self-improvement) for what was split out.
- `.planning/REQUIREMENTS.md` — **TOOL-01, TOOL-02, TOOL-04** (Phase 4) verbatim; **TOOL-03** (Phase 5);
  SI-01/02 (Phase 6). Traceability table re-phased; coverage now 25 v1.
- `.planning/STATE.md` — milestone posture: **deploy-ready only, no live GCP provisioning**;
  `make test`/`make smoke` green with no cloud deps.
- `.planning/spikes/001-composio-vs-nango-coverage/README.md` — Composio-vs-Nango evidence behind D-09
  (Composio wins on MCP-nativeness, near parity on connector count).

### Config & manifest surface (this phase wires these to live)
- `manifests/tool_pack_manifest.yaml` — provider list, `integration_style`, `category`,
  `approval_required`, `credential_secret_name`, `resource_bindings`, `input_schema_ref` /
  `output_schema_ref`. **Source of truth** for which tools/styles exist; D-03 makes the loader honour
  the fields it currently drops. (Xero already declared `nango_aggregator` — that's Phase 5.)
- `schemas/google_drive_search.*.schema.json`, `schemas/hubspot_lookup_company.*.schema.json`,
  `schemas/hubspot_create_deal.*.schema.json` — **direct-tool schemas already exist**; TOOL-02 loads +
  enforces them. `schemas/contracts/ToolCall.schema.json` — the tool-call record shape.
- `manifests/deployment.manifest.yaml` — keep schema-consistent with the tool pack (DEP-02 later).

### Code seams to make real (this phase's surface area)
- `src/agent_mesh/tools/gateway.py` — `ToolGateway` / `ToolSpec` / `load_tool_pack` / `execute()`
  (today a stub). The execution engine, credential resolver, schema validator, and adapter dispatch
  live here / alongside.
- `src/agent_mesh/contracts/enums.py` — `ToolCategory`, `WRITE_CATEGORIES` (write-class set driving
  approval). `src/agent_mesh/contracts/models.py` — `ToolCall` record (durable evidence of execution).
- `src/agent_mesh/worker/runner.py` — already holds a `ToolGateway` (`tool_gateway=` ctor arg); the
  worker↔gateway wiring extends here. Roster's researcher/tool-router node is the agent-facing caller.
- `src/agent_mesh/observability.py` — `trace_metadata()` + the Phase-3 OTel transport; D-10 tool-event
  spans reuse these. Keep importable-without-deps degradation.
- `src/agent_mesh/services/approvals.py` — write-class tool calls bind to the existing approval ledger
  (payload-hash) before `execute()` runs; do not weaken SEC-01/SEC-02.
- `src/agent_mesh/services/repository.py` — `tool_calls` persistence (tenant-scoped per DUR-02).
- `pyproject.toml` — add `jsonschema`, provider SDKs (HubSpot, Google API client), Composio + Nango
  client deps as **optional/runtime extras** so the stub path stays importable + creds-free.

### Prior-phase context
- `.planning/phases/03-model-gateway-observability/03-CONTEXT.md` — **D-02 opt-in live lane** (the
  pattern D-11 extends to a per-provider matrix), **D-07 OTel transport** (the tool-span transport
  D-10 reuses), and the **stub-fallback degradation** invariant.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tools/gateway.py` `ToolGateway` / `ToolSpec` / `load_tool_pack` — extend, don't replace. The
  manifest→registry→`execute()` shape and the write-class `validate()` invariant already exist.
- `observability.trace_metadata()` + Phase-3 OTel transport + in-memory test exporter — the home for
  D-10 tool-event spans; no new transport needed.
- The Phase-3 **opt-in live lane** (`pytest -m live` / `make test-live`, skip-when-no-creds) — D-11's
  per-provider matrix is this pattern parameterized per provider.
- `RepositorySQL` `tool_calls` (tenant-scoped) — durable record for executions + schema-reject rows.
- Existing `schemas/*.json` for the three direct candidate tools — TOOL-02 enforcement targets.
- Approval ledger (`services/approvals.py`, payload-hash bound) — write-class tools gate through it,
  already proven in P1/P2.

### Established Patterns
- **Stub-fallback degradation** (CLAUDE.md): every heavy seam degrades to a deterministic, creds-free
  path so `make test`/`make smoke` stay green. The tool engine, each adapter, and each aggregator must
  honour this (D-11).
- **Tenant scoping on all reads** (DUR-02) — `tool_calls` reads stay tenant-scoped.
- **Write-class ⇒ approval_required** invariant enforced at load (`ToolSpec.validate`) and at the gate.
- **Agents never hold credentials** — the gateway resolves at execution time (D-02).

### Integration Points
- researcher/tool-router roster node ↔ `ToolGateway.execute()` ↔ `CredentialResolver` ↔ provider SDK
  (direct) or Composio/Nango client (aggregate).
- `execute()` ↔ schema validator (input pre-call, output post-call) ↔ `tool_calls` record.
- write-class `execute()` ↔ approval ledger (must be APPROVED + payload-hash match before the call).
- `execute()` ↔ OTel tool-event span (D-10) ↔ Phase-3 trace_id / shared metadata.

</code_context>

<specifics>
## Specific Ideas

Hard user directives from this discussion:
- **POC = MVP, viable general functionality** — not a single-adapter proof (D-01).
- **Full Google Workspace suite live this phase** (Gmail, Calendar, Drive, Sheets, Docs, Slides) (D-08).
- **Composio primary + Nango fallback** (D-09), per Spike 001.
- **Fail-closed for direct tools without a schema**; permissive/runtime-schema for aggregate (D-04/05).
- **Per-provider credential/scope setup docs** so the user can supply creds (D-12).
- The user pushed back hard on over-narrow schema gating → drove the permissive + runtime-schema +
  asymmetric-failure model (D-04/05/06). Keep schemas loose by default.

**Research foci for gsd-phase-researcher (resolve before/within planning):**
1. **HubSpot** — private-app token + scopes for `lookup_company` (read) and `create_deal` (write);
   dev/test sandbox setup; Python client choice; per-tool JSON shapes vs existing `schemas/*.json`.
2. **Google Workspace** — single OAuth client covering Gmail+Calendar+Drive+Sheets+Docs+Slides;
   exact per-product scopes; refresh-token flow for an unattended live lane; google-api-python-client
   vs per-product libs; which ops per product land as adapters.
3. **Composio** — managed-auth + MCP Tool Router binding into the gateway; how per-tool JSON Schemas
   are fetched at runtime (feeds D-04); minimal real read to prove the style.
4. **Nango** — self-host footprint for a local live lane; unified-API call shape; runtime schema
   retrieval; minimal real read.
5. **Schema validation** — `jsonschema` draft + how runtime (aggregator) schemas are cached; the
   asymmetric input-reject / output-quarantine mechanics + `tool_call` failure-row shape.
6. **Dependency pins** — HubSpot/Google/Composio/Nango/`jsonschema` as optional runtime extras that
   keep the stub path importable and creds-free.

</specifics>

<deferred>
## Deferred Ideas

- **Reference-adapter breadth → Phase 5 (TOOL-03):** Webflow, Bitscale, Cal.com, Clockify, Beehiiv as
  direct adapters; **Xero via aggregator** (already `nango_aggregator` in the manifest). Plus the heavy
  aggregator provider matrix and any **write-through-aggregator** proof.
- **Self-improvement → Phase 6 (SI-01/02):** real eval harness replacing `evaluate_proposal`;
  AI-BOM-on-promotion + controlled versioned (non-hot) promotion + rollback. (The `AIBOMSnapshot` model
  + `promote_proposal(ai_bom_snapshot_id=…)` seam already exist, awaiting a generator there.)
- **Deeper Slack interaction surface** (slash commands, richer approval UX) — possible separate
  *ingress* item; ingress is already functionally built, so not in scope now. Note for backlog if the
  user wants it.
- **v2 / production hardening:** live GCP provisioning + FinOps (DEP-03/04); immutable ledger, egress
  controls, signed images, HA (caveats).

### Reviewed Todos (not folded)
None — no pending-todo matches for this phase.

</deferred>

---

*Phase: 04-tool-gateway-framework-first-adapters-aggregators*
*Context gathered: 2026-06-06*
