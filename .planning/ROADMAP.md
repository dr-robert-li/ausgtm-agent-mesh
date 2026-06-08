# Roadmap: ausgtm-agent-mesh

## Overview

This milestone completes the existing runnable scaffold into a real, locally-validated
platform. Work proceeds by hardening technical layers in dependency order: first a
durable Postgres-backed core with an authenticated approval gate (the foundation
everything else relies on), then the real LangGraph + Deep Agents orchestration engine
with durable checkpoints, then the live model gateway and Langfuse observability plane,
then a reusable Tool Gateway execution engine proven across direct adapters and both
aggregator styles, broad reference-provider coverage, and a real self-improvement
evaluation loop. A final phase assembles all layers, proves the platform end-to-end
(Slack write-gated action, MCP checkpointed job, failure modes), and validates that the
deployment scripts are idempotent and GCP-ready — without provisioning any live cloud
resources.

> **Re-scope (2026-06-06):** POC reframed as MVP requiring viable general tool coverage,
> not a single-adapter proof. TOOL-03/04 promoted v2→v1; tool work split into a framework
> phase (4), an adapter-breadth phase (5), and self-improvement (6); E2E/deploy-readiness
> moved to Phase 7. Milestone grew 5→7 phases.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Durable Core & Approval Security** - Postgres-backed durable state, tenant-scoped reads, runtime dispatch, and an authenticated/replay-proof approval gate _(completed 2026-06-05)_
- [x] **Phase 2: Real Orchestration Engine** - Real LangGraph supervisor + Deep Agents roster, durable checkpointer, interrupt-based HITL resume, hardened sandbox
- [x] **Phase 3: Model Gateway & Observability** - Live LiteLLM gateway with budgets/cascades, Cloudflare AI Gateway upstream, Langfuse telemetry + prompt/eval management _(completed 2026-06-06; GW-01/02/03, OBS-01/02 — governed budget-halt closed via gap plan 03-04; OBS-01 tool-spans deferred to Phase 4)_
- [x] **Phase 4: Tool Gateway Framework + First Adapters + Aggregators** - Reusable Tool Gateway execution engine (execution-time credential resolution, JSON-Schema in/out validation, tool-event OTel spans), HubSpot + Google Workspace direct adapters, Composio (primary) + Nango (fallback) aggregator styles _(completed 2026-06-06; TOOL-01, TOOL-02, TOOL-04 + OBS-01 tool-spans; framework verified against source 5/5 must-haves + 8 invariants, 215 tests green creds-free; live SC-1/SC-3 lanes opt-in and deferred to operator per milestone deploy-ready-only scope — run `make test-live` with creds)_
- [x] **Phase 5: Reference Adapter Breadth** - Remaining reference providers — Webflow, Bitscale, Cal.com, Clockify, Beehiiv direct adapters; Xero via aggregator _(completed 2026-06-07; TOOL-03; 5 direct adapters + Xero-via-Composio (no new module) verified against source 4/4 success criteria, 242 tests green creds-free; live lanes opt-in/deferred to operator — `make test-live` with creds; code review 4 findings fixed in 80e6d4e, 1 by-design)_
- [x] **Phase 6: Self-Improvement (real loop)** _(completed 2026-06-08)_ - Real held-out evaluation harness + GEPA-style offline inert proposer & bounded loop; CycloneDX ML-BOM-on-promotion + controlled versioned (non-hot) promotion with rollback. Option-C-safe (inert, human-gated, no runtime mutation) _(SI-01 +a–d, SI-02 +a–b, SI-03; expanded 2026-06-07 by deep-research; memory/skill/topology → new "Self-Evolving Surfaces" milestone as SI-04/SI-05)_
- [ ] **Phase 7: E2E Validation & Deploy-Readiness** - Full end-to-end proofs + failure modes + idempotent deploy-script validation _(E2E-01/02/03, DEP-01/02)_

> **Re-scope (2026-06-06):** POC reframed as MVP requiring viable general tool coverage. TOOL-03/04 promoted v2→v1; the old "Phase 4: Tools & Self-Improvement" split into a tool-framework phase (4), an adapter-breadth phase (5), and a self-improvement phase (6); E2E/deploy-readiness moved to Phase 7. Milestone grew 5→7 phases.

## Phase Details

### Phase 1: Durable Core & Approval Security
**Goal**: Replace the in-memory store with a durable Postgres-backed repository that survives restarts and enforces tenant isolation, wire runtime dispatch, and close the critical write-gate bypass by authenticating the approval callback.
**Depends on**: Nothing (first phase)
**Requirements**: DUR-01, DUR-02, DUR-03, SEC-01, SEC-02
**Success Criteria** (what must be TRUE):
  1. After the worker is killed and restarted mid-run, a queued/in-flight task resumes from Postgres with no lost state
  2. A read scoped to one tenant never returns another tenant's task events or evaluations
  3. A POST to `/v1/approvals` without a valid signed token is rejected; a self-asserted/forged `approver_id` cannot approve a task
  4. Editing a tool-call payload after approval invalidates that approval, and an approval cannot be replayed across tasks
**Plans**: 3 plans

Plans:
- [x] 01-01: Postgres-backed repository (`RepositorySQL` over `0001`/`0002` migrations) with tenant-scoped read methods (DUR-01, DUR-02)
- [x] 01-02: Runtime Pub/Sub dispatch with in-process fallback retained (DUR-03)
- [x] 01-03: Signed approval-token auth on `/v1/approvals` + replay/mutation test suite (SEC-01, SEC-02)

### Phase 2: Real Orchestration Engine
**Goal**: Replace the orchestration stub with a real LangGraph supervisor delegating to a bounded Deep Agents roster, persist graph state in a Postgres checkpointer so long runs resume after restart, express approvals as graph interrupts, and harden the prompt-to-code sandbox.
**Note**: The real graph runs against the *stubbed* model path until Phase 3 lands the live gateway — so the supervisor's topology, checkpointing, and interrupts are proven here; real agent *behaviour against real models* is first exercised end-to-end in Phase 3/5. (Layering is intentional: durability before orchestration before model plane. If exercising real model behaviour sooner matters, P2↔P3 can swap.)
**Depends on**: Phase 1
**Requirements**: ORCH-01, ORCH-02, ORCH-03, SBX-01
**Success Criteria** (what must be TRUE):
  1. A task runs through a real LangGraph supervisor that delegates to the four declared Deep Agents roster members; roster size is logged at startup
  2. A long-running (or simulated >60-min) run resumes from its durable Postgres checkpoint after a process restart
  3. A proposed write pauses the graph as a LangGraph interrupt and resumes from the checkpoint when the decision arrives
  4. The sandbox enforces its memory limit without failing open and executes via the hardened container path
**Plans**: 3 plans

Plans:
- [x] 02-01-supervisor-roster-PLAN.md — Real LangGraph supervisor graph + bounded Deep Agents roster (planner, researcher/tool-router, code-writer, reviewer); roster size logged (ORCH-01) [wave 1]
- [x] 02-02-checkpointer-interrupt-hitl-PLAN.md — Postgres checkpointer wiring + interrupt-based HITL pause/resume from checkpoint; ledger stays the decision authority (ORCH-02, ORCH-03) [wave 2, depends 02-01]
- [x] 02-03-hardened-sandbox-PLAN.md — Hardened sandbox isolation: non-fail-open memory limit + Docker cgroup container path (SBX-01) [wave 1]

### Phase 3: Model Gateway & Observability
**Goal**: Stand up the live LiteLLM-compatible model control plane with budget enforcement and cascades, route upstream through the Cloudflare AI Gateway governance plane, and wire Langfuse so every model/tool/approval event is traced and correlated.
**Depends on**: Phase 2
**Requirements**: GW-01, GW-02, GW-03, OBS-01, OBS-02
**Success Criteria** (what must be TRUE):
  1. Model calls route through the live LiteLLM gateway to Anthropic-direct/Vertex AI and halt cleanly when the USD $50 budget is exhausted
  2. When the primary model fails, the cascade falls back and the run continues; a budget breach halts the run
  3. Every model, tool, and approval event for a task appears correlated in Langfuse under shared request metadata
  4. Upstream model calls traverse the Cloudflare AI Gateway when enabled; agents never call providers directly
**Plans**: 3 plans

Plans:
- [x] 03-01-litellm-router-budget-PLAN.md — In-process litellm.Router from yaml + RouterChatLiteLLM binding + durable-ledger per-user/per-task budget; shared wave-2 scaffolding (GW-01) [wave 1]
- [x] 03-02-cf-chokepoint-failure-test-PLAN.md — D-06 CF-never-bypass structural guard + GW-03 two-lane fallback + cents-cap budget halt (GW-02, GW-03) [wave 2, depends 03-01]
- [x] 03-03-langfuse-otel-observability-PLAN.md — langfuse v2→v4 + OTel transport + trace_id + cross-process traceparent + prompt/dataset/eval seed (OBS-01, OBS-02) [wave 2, depends 03-01]
- [x] 03-04-governed-budget-halt-PLAN.md — gap-closure: governed/observable budget halt (budget_halt gateway_event + FAILED terminal state) (GW-03, OBS-01) [wave 3, gap_closure]

### Phase 4: Tool Gateway Framework + First Adapters + Aggregators
**Goal**: Turn the Tool Gateway stub into a real, reusable execution engine — execution-time credential resolution (Secret-Manager-shaped, env-backed locally; agents never receive raw creds), JSON-Schema input/output validation at the boundary, and tool-event OTel spans (closing the OBS-01 leftover) — then prove it across two integration styles: HubSpot + Google Workspace **direct** adapters making real calls, and the **Composio** (primary) + **Nango** (fallback) aggregator styles exercised end-to-end. Ship per-provider credential/scope setup docs.
**Depends on**: Phase 3
**Requirements**: TOOL-01, TOOL-02, TOOL-04
**Success Criteria** (what must be TRUE):
  1. A real direct adapter (HubSpot, and Google Workspace) performs a real call locally through the Tool Gateway with credentials resolved at execution time
  2. A tool call with a schema-invalid input or output is rejected at the boundary (deterministic test, default lane)
  3. Both aggregator styles (Composio primary, Nango fallback) execute at least one real tool call end-to-end through the gateway
  4. Default `make test` / `make smoke` stay green and creds-free; live calls run only in a per-provider opt-in lane, each independently skippable when its creds are absent
  5. A per-provider credential/scope setup doc exists (how to mint each token/OAuth app + exact scopes)
**Plans**: 9 plans

**Aggregator note**: `composio_aggregator` (MCP-native single Tool Router endpoint, ~982 toolkits / 20k tools) is **primary**; `nango_aggregator` (open-source unified-API, ~838 providers, self-hostable) is the peer **fallback**. TOOL-04 exercises both. Evidence: Spike 001 (`.planning/spikes/001-composio-vs-nango-coverage/`) — Composio wins on MCP-nativeness, near parity on raw connector count.

Plans:
- [x] 04-01-PLAN.md — Contract + manifest + deps foundation: ToolCall additive fields + migration 0003 + repo ripple; all GWS manifest entries + schemas; pyproject tools/aggregators extras + jsonschema core (TOOL-01, TOOL-02) [wave 1]
- [x] 04-02-PLAN.md — JSON-Schema validation boundary: Draft 2020-12, asymmetric input-reject/output-quarantine, fail-closed-direct-only (TOOL-02) [wave 2, depends 04-01]
- [x] 04-03-PLAN.md — Tool Gateway execution engine: ToolSpec D-03 fields + CredentialResolver + adapter-dispatch registry + real execute(call) + D-10 tool-event span (TOOL-01, TOOL-02, OBS-01 leftover) [wave 3, depends 04-01]
- [x] 04-04-PLAN.md — Read-execution seam (item A) + worker gateway wiring: proposed_reads ungated post-run, runner/main/graph wiring; read path never touches the approval gate (TOOL-01) [wave 4, depends 04-01/04-03]
- [x] 04-05-PLAN.md — HubSpot direct adapter: lookup_company (read) + create_deal (approval-gated write, sandbox), live-proven (TOOL-01) [wave 3, depends 04-01/04-03]
- [x] 04-06-PLAN.md — Google Workspace adapters part 1: shared refresh-token auth scaffold + Drive/Gmail/Sheets, live-proven (TOOL-01) [wave 3, depends 04-01/04-03]
- [x] 04-07-PLAN.md — Google Workspace adapters part 2: Calendar/Docs/Slides completing the full six-product suite (TOOL-01) [wave 4, depends 04-06]
- [x] 04-08-PLAN.md — Composio (primary) + Nango (fallback, httpx REST proxy) aggregators end-to-end + runtime aggregate-schema fetch/cache (TOOL-04) [wave 3, depends 04-01/04-03]
- [x] 04-09-PLAN.md — Per-provider credential/scope setup index + live-lane matrix + completeness guard (TOOL-01, TOOL-04) [wave 5, depends 04-05/06/07/08]

### Phase 5: Reference Adapter Breadth
**Goal**: Fan out the remaining reference providers through the Phase-4 framework — Webflow, Bitscale, Cal.com, Clockify, Beehiiv as direct adapters, and Xero via the aggregator — each independently landable and testable, reusing the credential-resolution / schema-validation / OTel-span machinery without rearchitecture.
**Depends on**: Phase 4
**Requirements**: TOOL-03
**Success Criteria** (what must be TRUE):
  1. Each reference provider (Webflow, Bitscale, Cal.com, Clockify, Beehiiv) has a working direct adapter behind the gateway with schema validation
  2. Xero executes through the aggregator path (financial category, approval-gated for writes)
  3. Each provider is independently skippable in the live lane; default suite stays green and creds-free
  4. Per-provider credential/scope setup docs extended to cover the new providers
**Plans**: 7 plans

Plans:
- [x] 05-01-PLAN.md — Foundation: all shared-file edits — schema_refs + 18 schema files for every direct op, bitscale ops reconciled, webflow read op added, Xero flipped to composio_aggregator (wave 1) (TOOL-03)
- [x] 05-02-PLAN.md — Webflow direct adapter (list + draft create) (wave 2) (TOOL-03)
- [x] 05-03-PLAN.md — Bitscale direct adapter (grids/workspace reads + run_grid write; reads-only live lane) (wave 2) (TOOL-03)
- [x] 05-04-PLAN.md — Cal.com direct adapter (list + create bookings, mandatory cal-api-version header) (wave 2) (TOOL-03)
- [x] 05-05-PLAN.md — Clockify direct adapter (read time entries) (wave 2) (TOOL-03)
- [x] 05-06-PLAN.md — Beehiiv direct adapter (draft create_post, nested {data:{id}} output) (wave 2) (TOOL-03)
- [x] 05-07-PLAN.md — Xero via Composio (existing adapter) + shared credential index + credential-docs guard extension (wave 3) (TOOL-03)

### Phase 6: Self-Improvement (real loop)
**Goal**: Replace the `evaluate_proposal` stub with a real **held-out** evaluation harness; add a
GEPA-style offline reflective proposer + bounded improvement loop; and wire
**CycloneDX ML-BOM-on-promotion** with controlled, versioned (non-hot) promotion and retained
rollback — Option-C-safe: proposals stay inert, promotion is the single human-gated chokepoint,
and no active instructions/permissions/routing are mutated at runtime.
**Depends on**: Phase 5
**Requirements**: SI-01 (+SI-01a–d), SI-02 (+SI-02a–b), SI-03
**Scope note**: Expanded 2026-06-07 from a 2-plan stub-replacement following a deep-research
review of 2025–2026 self-evolving-agent SOTA (see `06-CONTEXT.md` → Canonical References).
Memory/skill/topology evolution (SI-04/SI-05) deferred to a new **"Self-Evolving Surfaces"**
milestone; this milestone is re-scoped to a governed self-evolving build (PROJECT.md + new
milestone via `/gsd:new-milestone` as a follow-up).
**Success Criteria** (what must be TRUE):
  1. A proposal is scored by a real Langfuse-experiment harness over a versioned **held-out**
     dataset (deterministic frozen-context snapshots) **distinct from any signal the proposer
     optimized against** — not a stub (SI-01, SI-01a, SI-01c)
  2. Promotion-eligibility requires candidate ≥ baseline on aggregate metrics AND no item-level
     regression beyond threshold (SI-01b)
  3. A GEPA-style offline proposer mines traces and emits **inert** prompt/workflow diffs only;
     the loop caps iterations and re-validates on the held-out set each round (held-out protected
     from proposer visibility) (SI-03)
  4. Promotion generates a **CycloneDX ML-BOM** snapshot from the deployment + tool-pack manifests
     bound to a versioned promotion with rollback (SI-02, SI-02a)
  5. No active instructions/permissions/routing mutated at runtime; promoted artifact referenceable
     only via versioned non-hot wiring read at next start/deploy; rollback re-points to
     `previous_version` (both proven by tests) (SI-02b)
  6. Default suite stays green and creds-free; any LLM-judge scoring + judge calibration
     (TPR/FPR, Type-I gate, order-swap) runs only in the `live` opt-in lane (SI-01d)
**Plans**: 6 plans

Plans:
- [x] 06-01-PLAN.md — Foundation (all shared-file edits): migration 0004 active-version pointer + ai_bom_snapshots + repository.py current_active_version/set_active_version + upsert_ai_bom/get_ai_bom (3 layers) + conftest stub-reflector/frozen-item fixtures + [aibom] extra (cyclonedx 11.8.0 vetted) + blocking cyclonedx supply-chain checkpoint (SI-02b) [wave 1] _(completed 2026-06-07)_
- [x] 06-02-PLAN.md — Real held-out evaluation harness: creds-free Langfuse run_experiment over versioned frozen items + pure-Python item+run no-regression gate + evaluate_proposal body swap (SI-01, SI-01a, SI-01b, SI-01c) [wave 2, depends 06-01]
- [x] 06-03-PLAN.md — GEPA-style offline inert reflective proposer + bounded re-validated loop; held-out zero-overlap test (SI-03, SI-01a) [wave 3, depends 06-01/06-02]
- [x] 06-04-PLAN.md — Opt-in `live`-lane LLM-judge: order-swap position-bias control + TPR/FPR calibration + finite-sample Type-I gate + close-margin non-sole-arbiter guard (SI-01d) [wave 3, depends 06-01/06-02]
- [x] 06-05-PLAN.md — CycloneDX ML-BOM (V1_7) generator on promotion from the deployment + tool-pack manifests → AIBOMSnapshot (SI-02, SI-02a) [wave 2, depends 06-01]
- [x] 06-06-PLAN.md — Versioned non-hot promotion wiring (boot-time set-once version loader) + ML-BOM fill + rollback re-point to previous_version (SI-02b) [wave 3, depends 06-01/06-02/06-05]

### Phase 7: E2E Validation & Deploy-Readiness
**Goal**: Assemble all layers and prove the platform end-to-end — a write-gated Slack action from evidence, an MCP-triggered long checkpointed job returning an artifact, and the failure modes — then validate that the `gcloud` and `wrangler` deployment scripts are idempotent and GCP-ready without provisioning live resources.
**Depends on**: Phase 6
**Requirements**: E2E-01, E2E-02, E2E-03, DEP-01, DEP-02
**Success Criteria** (what must be TRUE):
  1. An end-to-end run proves Slack request → evidence → write-gated SaaS action → approval → completion
  2. An MCP request runs a long checkpointed mesh job and returns an artifact
  3. A failure E2E demonstrates model fallback, job retry, and budget-limit halt together
  4. The `gcloud` bootstrap/deploy and Cloudflare `wrangler` scripts pass lint + dry-run/syntax checks, and their resource-detection branches are unit-tested with a mocked `gcloud` (idempotency *logic* proven locally — true end-to-end idempotency against a live project is deferred to DEP-03); the deployment + tool-pack manifests are schema-consistent
**Plans**: 5 plans (4 + 1 gap-closure)

> **Plan-count note (2026-06-08):** the ROADMAP stub proposed 2 plans (one E2E suite, one deploy). Planning split the E2E suite into three per-proof plans (each E2E criterion is a distinct subsystem with its own ~50% context budget). 07-01 owns the `tests/e2e/__init__.py` package marker (tests/ is a real package, pytest prepend import mode), so 07-02/07-03 depend on it (wave 2); 07-04 owns `tests/deploy/__init__.py` and is independent (wave 1) and kept deploy-readiness standalone. The three open design decisions surfaced by the pattern-mapper are resolved in-plan: (1) E2E-03's "job retry" leg = litellm in-cascade recovery (07-03) PLUS Pub/Sub `--max-delivery-attempts=5` deploy-config consistency (07-04), no new fault harness (honors D-05); (2) E2E-02 MCP entry = in-process `request_from_mcp` (no `/mcp` HTTP route exists); (3) D-11 manifest-consistency = a NEW dedicated validator (export_schemas only does Pydantic→JSON-Schema, never reads YAML manifests).

Plans:
- [x] 07-01-PLAN.md — E2E-01: Slack write-gated action through the real FastAPI TestClient (default lane) + reversible draft/sandbox live variant (E2E-01) [wave 1, D-01/02/03/07]
- [x] 07-02-PLAN.md — E2E-02: MCP in-process request → durable checkpointed job (sqlite drop/reopen restart-resume; Postgres opt-in lane) returning a surviving artifact (E2E-02) [wave 2, depends 07-01, D-01/02/03/04]
- [x] 07-03-PLAN.md — E2E-03: single combined failure run — fallback + in-cascade retry-recovery → governed budget_halt → FAILED; cents-cap live variant (E2E-03) [wave 2, depends 07-01, D-05/06/08]
- [x] 07-04-PLAN.md — Deploy-readiness: PATH-shim gcloud/wrangler idempotency-logic harness + bash -n floor + loud-skip lint + NEW manifest-consistency validator + Pub/Sub redelivery-config assertion (DEP-01, DEP-02) [wave 1, D-09/10/11]
- [x] 07-05-PLAN.md — Gap-closure (SC-2/CR-01): rewrite E2E-02 default lane to drive the production Worker/orchestrator restart-resume wiring via set_checkpointer_override + file-backed sqlite (bare production thread_id; discriminating checkpoint-survival read); fold in WR-01 (registered FastMCP tool) + WR-02 (Postgres-lane negative assertion + make test-pg / RUNBOOK hook) (E2E-02) [wave 1, gap_closure]

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Durable Core & Approval Security | 3/3 | Complete | 2026-06-05 |
| 2. Real Orchestration Engine | 3/3 | Complete | 2026-06-06 |
| 3. Model Gateway & Observability | 4/4 | Complete | 2026-06-06 |
| 4. Tool Gateway Framework + First Adapters + Aggregators | 9/9 | Complete | 2026-06-06 |
| 5. Reference Adapter Breadth | 7/7 | Complete | 2026-06-07 |
| 6. Self-Improvement (real loop) | 6/6 | Complete | 2026-06-08 |
| 7. E2E Validation & Deploy-Readiness | 0/4 | Planned | - |
