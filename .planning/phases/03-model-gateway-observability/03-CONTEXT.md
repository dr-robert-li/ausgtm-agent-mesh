# Phase 3: Model Gateway & Observability - Context

**Gathered:** 2026-06-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Stand up the **live model control plane** and the **observability plane** for the mesh:

- **LiteLLM-compatible gateway (GW-01)** — real routing + cascades/fallbacks + a USD $50/month
  budget, exercised against **real** Anthropic-direct and Vertex AI providers.
- **Cloudflare AI Gateway upstream (GW-02)** — agents/workers never call providers directly;
  upstream model traffic traverses the CF edge gateway when enabled.
- **Failure proof (GW-03)** — model fallback + budget-limit halt behave correctly.
- **Langfuse telemetry (OBS-01)** — every model/tool/approval event for a task correlates under
  shared request metadata.
- **Prompt/eval config (OBS-02)** — Langfuse prompt/version management + datasets/evals configured.

Maps to: GW-01, GW-02, GW-03, OBS-01, OBS-02.
Plans (from ROADMAP): 03-01 live LiteLLM gateway (GW-01); 03-02 CF upstream + failure test
(GW-02, GW-03); 03-03 Langfuse telemetry + prompt/eval (OBS-01, OBS-02).

**Layering reminder (P2 D-01):** Phase 2 proved topology/checkpointing/interrupts against a
*stubbed* model path. Phase 3 is where **real-model behaviour first runs end-to-end**. This is
the phase that lands the live gateway P2 deliberately did not pull forward.

</domain>

<decisions>
## Implementation Decisions

### Live local-validation ceiling (the master decision — shapes every other area)
- **D-01:** **Real Router → Real Provider is the live proof.** No faked provider boundary. A
  genuine LiteLLM router calling **real** Anthropic and Vertex AI is what proves "live". The
  user explicitly rejected a mock/fake-boundary approach.
- **D-02:** **Opt-in live lane.** Default `make test` / `make smoke` keep the **deterministic
  stub path** (green, no creds, CI-safe — preserves the CLAUDE.md "no cloud deps" invariant). A
  **separate marked lane** (`make test-live` / `pytest -m live`) drives the real router → real
  providers with the user's keys and a **tiny budget cap** (cents). This is the analog of P2's
  "real topology, deterministic boundary, skip-when-no-Docker" pattern.
- **D-03:** **Both providers live.** The live lane makes real calls to **both** Anthropic-direct
  **and** Vertex AI (user supplies Vertex/GCP creds: ADC or SA key). Cross-provider cascade
  (GW-03) is proven as **Vertex primary → real failure → Anthropic fallback**. A live Vertex
  *model call* is **not** GCP infra provisioning (no Cloud SQL / Cloud Run created) — it
  respects the milestone's "no live GCP provisioning" boundary.

### Budget enforcement model
- **D-04:** **Durable ledger halts; gateway backs in prod.** The durable `budget_ledger`
  (Postgres, **tenant-scoped** per P1) is the local-provable enforcement point: worker
  **pre-call `check()`** reads month-to-date from the ledger → raises `BudgetExceeded` → the run
  **halts cleanly** + a `gateway_event` is recorded; **post-call `record()`** persists actual
  cost. The current in-memory `budget.py` `BudgetTracker` must be **persisted to the durable
  ledger** (survives restart, feeds 12-mo audit). **In the D-09 in-process Router runtime the
  durable ledger is the SOLE budget enforcer** — this IS the gateway control-plane enforcement
  GW-01 requires (the LiteLLM control plane lives in-process). LiteLLM
  `general_settings.max_budget:50` is **inert in the POC runtime** and becomes active **only if
  the deferred standalone-proxy scale-up path (D-09) is later deployed**; this phase only
  **asserts it via config**, never executes it. (Framing matters: GW-01's "gateway enforces
  budget" is satisfied deliberately by the ledger-as-control-plane, not left as a gap.)
- **D-05:** **Per-user halts; per-task attributes.** `$50/month per-user` (budget_owner) is the
  **hard cap that halts**. **Per-task = cost attribution**: every `gateway_event` / `budget_ledger`
  row tagged with `task_id` (for Langfuse correlation + audit), with an **optional `per_task_cap`**
  that defaults to the per-user cap. One number to configure per deployment.

### Cloudflare never-bypass proof (GW-02)
- **D-06:** **Structural egress chokepoint + config assertion.** ALL model construction flows
  through `model_gateway.get_chat_model()`, which **always** sets `api_base` to the gateway /
  CF-wrapper URL. A **guard test fails** if any code path builds a provider client without it
  ("agents never call providers directly" enforced at the code level, not just config). A
  **config test** asserts every route's `api_base` = the CF wrapper when CF is enabled. A
  `CF_ENABLED`-style flag flips `api_base` to the CF wrapper URL. **Real CF traversal is opt-in**
  in the live lane (when `CF_AIG_WRAPPER_URL` is set); otherwise the live call goes direct to the
  provider (CF disabled = a **valid POC state**). CF stays **integration-ready** per CLAUDE.md #6;
  deploying/`wrangler`-publishing the worker is **DEP-02 / Phase 5**, not this phase.

### Langfuse correlation (OBS-01)
- **D-07:** **OTel-first transport; Langfuse = default/required consumer; pluggable + parallel
  SIEM.** Model, tool, **and** approval events all emit **OpenTelemetry spans** with the shared
  request metadata (`tenant_id`, `task_id`, `session_id`, `requester_id`, `entrypoint`,
  `agent_role`, `model_route_profile`, `approval_state`) as **span attributes**. A single
  **`trace_id` per task** is **set on `OrchestrationResult`** (closes the P2 gap where `trace_id`
  was left unset). Spans export via **OTLP to a configurable endpoint**: **Langfuse is the default
  OTLP consumer and stays REQUIRED** (per CLAUDE.md — it is also the prompt/eval plane); the
  operator may **repoint OTLP at a replacement OR fan-out to a parallel SIEM** (multi-exporter).
  **"Replaceable / parallel" does NOT make Langfuse optional** — the required-stack guardrail
  holds. CI proof = an **in-memory OTel span exporter** asserting spans + attributes
  deterministically (no server, green suite); the live lane exports to **real Langfuse**.
- **OBS-01/OBS-02 split:** OTel covers the **tracing transport** (OBS-01). **OBS-02**
  (prompt/version management + datasets/evals) is **Langfuse-native** — OTel does not cover it, so
  OBS-02 stays bound to the Langfuse SDK regardless of the transport choice.

### Observability prompt/eval depth (OBS-02)
- **D-08:** **Thin / seeded.** Wire Langfuse **prompt/version management** with a local
  **fetch-with-fallback** (prompt pulled from Langfuse when reachable, else a **local default** —
  keeps `make test` green), register **≥1 versioned prompt**, and **seed one dataset** (e.g. from
  task evidence). An **example/trivial eval** is registered to prove the path. The **real eval
  harness (scoring engine) is Phase 4 (SI-01)** — do not pull it forward.

### Gateway deployment shape
- **D-09:** **In-process `litellm.Router` is the POC runtime; standalone proxy is a
  deploy-validated scale-up path.** A loader builds a **real `litellm.Router`** from
  `config/model_gateway.config.yaml`; **cascades + retries run in-process** inside the worker.
  `get_chat_model()` returns a Router-backed model. Rationale (per discussion): a self-run
  standalone LiteLLM **proxy server in front of CF would be a second, self-operated SPOF** —
  whereas **CF is the managed/HA edge chokepoint**, so an in-process Router avoids adding a SPOF
  the managed edge doesn't impose, and keeps routing/cascade/budget logic in testable Python
  (budget already in the durable ledger, D-04). **Path stays: worker Router → CF edge → provider**
  (D-06 chokepoint holds; agents still never call providers directly — the Router routes through
  CF). The **proxy yaml stays as deploy config** (schema/lint validated, `api_base` seam preserved
  so prod CAN front a real proxy service later for multi-tenant/centralized-budget/key-isolation).
  Proxy-only yaml fields (`master_key`, `general_settings.max_budget`) become **prod-proxy config
  asserted structurally**, not executed locally.

### Claude's Discretion (left to research + planning)
- `gateway_events` table schema/shape and whether it reuses an existing migration family or adds
  a new migration alongside `RepositorySQL` (`0001`/`0002`).
- Exact `litellm.Router` load/construction pattern from the yaml, and how `langchain_litellm` /
  `ChatLiteLLM` binds to an in-process Router vs. an `api_base` HTTP target.
- Token-cost **estimation method** for the pre-call budget `check()` (e.g. `max_tokens × route
  price`) vs. provider-returned usage on `record()`.
- OTel exporter/config surface (resource attributes, OTLP endpoint env wiring, multi-exporter
  fan-out shape).
- Cross-provider cascade trigger mechanics for the GW-03 failure test (how Vertex "real failure"
  is induced deterministically in the live lane).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Normative design & guardrails
- `CLAUDE.md` §1–§3 — required stack (LangChain + LangGraph + Deep Agents + **Langfuse REQUIRED**;
  LangSmith never a dependency); the **model-gateway separation of responsibilities** (LiteLLM =
  control plane: routing/budgets/cascades/provider abstraction; **Cloudflare AI Gateway** =
  model-traffic governance: logging/DLP/blocking/guardrails); **flow** LangChain → LiteLLM gateway
  → CF AI Gateway → providers; "gateway MUST route all upstream through CF when enabled; agents
  never call providers directly"; shared request metadata list.
- `CLAUDE.md` §6 Acceptance Criteria #5 (gateway-routed, never-direct), #6 (CF **integration-ready**,
  does not replace tool-write gates), #7 ($50 budget per-user/per-task), #8 (durable stores in AU;
  model processing may leave region), #16 (Langfuse-centered observability).
- `CLAUDE.md` §8 "Guardrails that survive every phase" — required stack holds; Langfuse never
  dropped; no runtime autonomous self-modification.

### Phase scope & requirements
- `.planning/ROADMAP.md` §"Phase 3: Model Gateway & Observability" — goal, success criteria, 3 plans.
- `.planning/REQUIREMENTS.md` — GW-01, GW-02, GW-03, OBS-01, OBS-02 (verbatim acceptance).
- `.planning/STATE.md` — milestone posture: **deploy-ready only, no live GCP provisioning**;
  `make test`/`make smoke` green with no cloud deps.

### Config & deployment surface (this phase wires these to live)
- `config/model_gateway.config.yaml` — LiteLLM route list (low/medium/high tiers, Anthropic-direct
  + Vertex + Claude-on-Vertex), `router_settings.fallbacks` cascade, `num_retries`, `max_budget:50`,
  `budget_duration:30d`, `success_callback:[langfuse,otel]`. **Source of truth for routes/cascade/
  budget config** — D-09 loads a `litellm.Router` from it; proxy-only fields are deploy config.
- `cloudflare/ai-gateway-wrapper/wrangler.toml` (+ `src/index.ts`) — CF AI Gateway wrapper worker.
  Integration-ready; `wrangler` publish/dry-run is **Phase 5 / DEP-02**, not here.
- `manifests/deployment.manifest.yaml` — `model_routes`, budget, Langfuse/CF env keys; keep
  schema-consistent.

### Code seams to make live (this phase's surface area)
- `src/agent_mesh/worker/model_gateway.py` — `resolve_route()`, `DEFAULT_PROFILE`,
  `get_chat_model()` (the **D-06 egress chokepoint**; today sets `api_base` from settings). D-09
  in-process Router loader lives here / alongside.
- `src/agent_mesh/worker/budget.py` — `BudgetTracker` (in-memory `check()`/`record()`/
  `month_to_date()`). D-04 persists this to the durable `budget_ledger`; D-05 adds per-task
  attribution.
- `src/agent_mesh/observability.py` — `langfuse_available()`, `trace_metadata()` (already builds
  the shared metadata dict), `get_langchain_callback()`. D-07 adds OTel emission + OTLP export
  + the in-memory test exporter; keep the importable-without-deps degradation.
- `src/agent_mesh/worker/graph.py` — `_model_credentials_present()` gate + the four roster nodes
  (planner/researcher/code_writer/reviewer) currently take the deterministic path; Phase 3 wires
  real model delegation behind this gate (still degrades to stub when creds absent).
- `src/agent_mesh/worker/orchestrator.py` — `_run_langgraph()` leaves `OrchestrationResult.trace_id`
  unset (P2). D-07 sets it. `OrchestrationResult` contract must stay stable (consumed by runner,
  ledger, tests).
- `src/agent_mesh/services/approvals.py` — approval events must emit correlated OTel spans (D-07)
  without weakening SEC-01/SEC-02 (signed token, payload-hash, replay guard).
- `src/agent_mesh/settings.py` — `model_gateway_base_url`, `model_provider_mode`,
  `model_route_profile`, `model_max_tokens`, `model_monthly_budget_usd`, `langfuse_*`. New CF /
  OTLP / live-lane env wiring extends here.
- `pyproject.toml` — `runtime` extra (`litellm>=1.40`, `langchain-litellm>=0.1`, `langfuse>=2.0`).
  Add OTel SDK/exporter deps; keep optional-by-design so the stub path stays importable.
- `migrations/` — `budget_ledger` + `gateway_events` tables alongside `RepositorySQL` (`0001`/
  `0002`); tenant-scoped per DUR-02.

### Prior-phase context
- `.planning/phases/02-real-orchestration-engine/02-CONTEXT.md` — D-01 layering (model plane is
  Phase 3), stub-fallback degradation pattern, `trace_id` deferred to Phase 3 (OBS-01/OBS-02),
  real-model behaviour deferred to Phase 3/5.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `model_gateway.get_chat_model()` / `resolve_route()` / `DEFAULT_PROFILE` — the routing seam +
  the D-06 chokepoint already exist; extend rather than replace.
- `observability.trace_metadata()` — already assembles the full shared-metadata dict OBS-01 needs;
  becomes the OTel span-attribute source (D-07).
- `budget.BudgetTracker` (`check`/`record`/`month_to_date`, RLock) — the API shape D-04 keeps;
  swap the in-memory `_spent` dict for durable-ledger reads/writes.
- `langfuse_available()` / `langchain_available()` / `_model_credentials_present()` import+cred
  gates — reuse for the stub-fallback degradation, don't reinvent.
- `RepositorySQL` over `0001`/`0002` migrations (tenant-scoped, durable) — the home for
  `budget_ledger` + `gateway_events`.

### Established Patterns
- **Stub-fallback degradation** (CLAUDE.md): every heavy seam degrades to a deterministic path
  when the optional dep/cred is absent so `make test`/`make smoke` run with no cloud deps. D-02's
  opt-in live lane is the Phase-3 expression of this.
- **Tenant scoping on all reads** (DUR-02) — `budget_ledger` / `gateway_events` reads stay
  tenant-scoped.
- **Approval ledger is decision authority** (P1, SEC-01/02) — observability OBSERVES approval
  events (D-07), never gates on them; budget halt (D-04) is a run-control concern, not an approval.

### Integration Points
- `graph.py` roster nodes ↔ `get_chat_model()` (in-process Router) ↔ CF edge ↔ providers — the
  live delegation path behind `_model_credentials_present()`.
- Worker run loop ↔ `budget.check()`/`record()` ↔ `budget_ledger` (pre-call halt, post-call record).
- `orchestrator.OrchestrationResult.trace_id` ↔ OTel root trace ↔ model/tool/approval spans.
- LiteLLM `success_callback:[langfuse,otel]` (yaml) ↔ in-process callback/OTel exporter.

</code_context>

<specifics>
## Specific Ideas

- **"Real Router → Real Provider"** is a hard user directive — the live proof must make genuine
  Anthropic AND Vertex calls; a faked provider boundary was explicitly rejected.
- **OTel-first with Langfuse as default-but-replaceable consumer + parallel-SIEM fan-out** is a
  hard user directive — emit vendor-neutral, let an operator add/replace a consuming backend
  (e.g. SIEM) without dropping Langfuse.
- **SPOF reasoning** drove D-09: avoid a self-operated proxy chokepoint in front of the managed CF
  edge; in-process Router is "more viable and more controllable" for the 5-user POC.

**Research foci for gsd-phase-researcher (resolve before/within planning):**
1. **In-process `litellm.Router` construction from the proxy yaml** — how to load `model_list` /
   `router_settings.fallbacks` / `num_retries` into a `litellm.Router`, and how `langchain_litellm`
   binds to it (Router object vs `api_base`). Confirm cascades + retries execute in-process.
2. **Pre-call cost estimation for the budget halt** — deterministic estimate for `check()` vs
   provider-returned usage for `record()`; how the live lane proves a clean halt with a tiny cap.
3. **OTel → Langfuse OTLP wiring + multi-exporter fan-out** — exporter/endpoint config, resource
   attributes, in-memory exporter for CI, and the parallel-SIEM seam. Confirm Langfuse OTLP ingest.
4. **GW-03 cross-provider cascade trigger** — how to induce a real Vertex failure deterministically
   so the Anthropic fallback is exercised in `make test-live`.
5. **`gateway_events` + `budget_ledger` schema** alongside existing migrations (tenant-scoped).
6. **`deepagents` / `litellm` / `langfuse` / OTel version pins** — confirm the runtime-extra
   surface needed is stable; pin versions.

</specifics>

<deferred>
## Deferred Ideas

- **Standalone LiteLLM proxy server runtime** — deploy-validated scale-up path only (D-09); not the
  POC runtime. Centralized cross-worker budget hard-stop, provider-key isolation (workers holding
  only a gateway key), and proxy HA come with it — **prod hardening, deferred**.
- **`wrangler` publish / dry-run of the CF worker + true idempotency** — Phase 5 / DEP-02.
- **Real evaluation harness (LLM-judge scoring engine)** — Phase 4 / SI-01. Phase 3 only seeds
  prompt versions + a dataset + an example eval (D-08).
- **Live GCP infra provisioning** (Cloud SQL / Cloud Run / Secret Manager) — deferred to v2 (DEP-03/04).
  Phase 3's live Vertex *model call* is creds-only, not provisioning.
- **Data-residency enforcement** — model processing may leave AU for the POC (CLAUDE.md #8); durable
  stores stay in AU. No residency gating this phase.

None beyond the above — discussion stayed within phase scope.

</deferred>

---

*Phase: 3-model-gateway-observability*
*Context gathered: 2026-06-06*
