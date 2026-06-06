# Roadmap: ausgtm-agent-mesh

## Overview

This milestone completes the existing runnable scaffold into a real, locally-validated
platform. Work proceeds by hardening technical layers in dependency order: first a
durable Postgres-backed core with an authenticated approval gate (the foundation
everything else relies on), then the real LangGraph + Deep Agents orchestration engine
with durable checkpoints, then the live model gateway and Langfuse observability plane,
then real SaaS tools and a real self-improvement evaluation loop. A final phase assembles
all layers, proves the platform end-to-end (Slack write-gated action, MCP checkpointed
job, failure modes), and validates that the deployment scripts are idempotent and
GCP-ready — without provisioning any live cloud resources.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Durable Core & Approval Security** - Postgres-backed durable state, tenant-scoped reads, runtime dispatch, and an authenticated/replay-proof approval gate _(completed 2026-06-05)_
- [x] **Phase 2: Real Orchestration Engine** - Real LangGraph supervisor + Deep Agents roster, durable checkpointer, interrupt-based HITL resume, hardened sandbox
- [x] **Phase 3: Model Gateway & Observability** - Live LiteLLM gateway with budgets/cascades, Cloudflare AI Gateway upstream, Langfuse telemetry + prompt/eval management _(completed 2026-06-06; GW-01/02/03, OBS-01/02 — governed budget-halt closed via gap plan 03-04; OBS-01 tool-spans deferred to Phase 4)_
- [ ] **Phase 4: Tools & Self-Improvement** - ≥1 real SaaS tool adapter with schema validation, real eval harness, AI-BOM-on-promotion with controlled versioned wiring
- [ ] **Phase 5: E2E Validation & Deploy-Readiness** - Full end-to-end proofs + failure modes + idempotent deploy-script validation

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

### Phase 4: Tools & Self-Improvement
**Goal**: Make at least one real SaaS tool adapter execute through the gated Tool Gateway with runtime credential resolution and boundary schema validation, and replace the self-improvement stubs with a real evaluation harness plus AI-BOM-generating, controlled, versioned promotion.
**Depends on**: Phase 3
**Requirements**: TOOL-01, TOOL-02, SI-01, SI-02
**Success Criteria** (what must be TRUE):
  1. A real SaaS tool adapter (Google Workspace or HubSpot) performs a real call locally through the Tool Gateway with credentials resolved at execution time
  2. A tool call with a schema-invalid input or output is rejected at the boundary
  3. A self-improvement proposal is scored by a real evaluation harness, not a stub
  4. Promotion produces an AI-BOM snapshot and a versioned promotion record with rollback; no live instructions/permissions/routing are mutated at runtime
**Plans**: 2 plans

**Aggregator note**: The generic MCP-aggregator integration style has two peer options — `nango_aggregator` (open-source unified-API, ~838 providers, self-hostable) and `composio_aggregator` (MCP-native single Tool Router endpoint, ~982 toolkits / 20k tools), either serving as fallback to the other. TOOL-04 (aggregator integration styles, currently in v2 scope) must exercise both. Evidence: Spike 001 (`.planning/spikes/001-composio-vs-nango-coverage/`) — Composio wins on MCP-nativeness, near parity on raw connector count.

Plans:
- [ ] 04-01: Real SaaS tool adapter behind Tool Gateway + JSON-Schema input/output validation (TOOL-01, TOOL-02)
- [ ] 04-02: Real eval harness + AI-BOM-on-promotion + controlled versioned promotion wiring (SI-01, SI-02)

### Phase 5: E2E Validation & Deploy-Readiness
**Goal**: Assemble all layers and prove the platform end-to-end — a write-gated Slack action from evidence, an MCP-triggered long checkpointed job returning an artifact, and the failure modes — then validate that the `gcloud` and `wrangler` deployment scripts are idempotent and GCP-ready without provisioning live resources.
**Depends on**: Phase 4
**Requirements**: E2E-01, E2E-02, E2E-03, DEP-01, DEP-02
**Success Criteria** (what must be TRUE):
  1. An end-to-end run proves Slack request → evidence → write-gated SaaS action → approval → completion
  2. An MCP request runs a long checkpointed mesh job and returns an artifact
  3. A failure E2E demonstrates model fallback, job retry, and budget-limit halt together
  4. The `gcloud` bootstrap/deploy and Cloudflare `wrangler` scripts pass lint + dry-run/syntax checks, and their resource-detection branches are unit-tested with a mocked `gcloud` (idempotency *logic* proven locally — true end-to-end idempotency against a live project is deferred to DEP-03); the deployment + tool-pack manifests are schema-consistent
**Plans**: 2 plans

Plans:
- [ ] 05-01: End-to-end test suite — Slack write-gated action, MCP checkpointed artifact, failure modes (E2E-01, E2E-02, E2E-03)
- [ ] 05-02: Deploy-readiness validation — idempotent gcloud/wrangler scripts + manifest consistency (DEP-01, DEP-02)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Durable Core & Approval Security | 3/3 | Complete | 2026-06-05 |
| 2. Real Orchestration Engine | 0/3 | Not started | - |
| 3. Model Gateway & Observability | 0/3 | Not started | - |
| 4. Tools & Self-Improvement | 0/2 | Not started | - |
| 5. E2E Validation & Deploy-Readiness | 0/2 | Not started | - |
