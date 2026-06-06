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
- [ ] **Phase 4: Tool Gateway Framework + First Adapters + Aggregators** - Reusable Tool Gateway execution engine (execution-time credential resolution, JSON-Schema in/out validation, tool-event OTel spans), HubSpot + Google Workspace direct adapters proven live, Composio (primary) + Nango (fallback) aggregator styles end-to-end _(TOOL-01, TOOL-02, TOOL-04)_
- [ ] **Phase 5: Reference Adapter Breadth** - Remaining reference providers — Webflow, Bitscale, Cal.com, Clockify, Beehiiv direct adapters; Xero via aggregator _(TOOL-03)_
- [ ] **Phase 6: Self-Improvement** - Real evaluation harness replaces the stub; AI-BOM-on-promotion + controlled versioned (non-hot) promotion with rollback _(SI-01, SI-02)_
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
**Plans**: 3-4 plans (set at planning)

**Aggregator note**: `composio_aggregator` (MCP-native single Tool Router endpoint, ~982 toolkits / 20k tools) is **primary**; `nango_aggregator` (open-source unified-API, ~838 providers, self-hostable) is the peer **fallback**. TOOL-04 exercises both. Evidence: Spike 001 (`.planning/spikes/001-composio-vs-nango-coverage/`) — Composio wins on MCP-nativeness, near parity on raw connector count.

Plans:
- [ ] 04-01: Tool Gateway execution engine — execution-time credential resolution + JSON-Schema in/out validation + tool-event OTel spans (TOOL-01, TOOL-02, OBS-01 leftover)
- [ ] 04-02: HubSpot + Google Workspace direct adapters, live-proven via opt-in lane (TOOL-01)
- [ ] 04-03: Composio (primary) + Nango (fallback) aggregator integration styles end-to-end (TOOL-04)
- [ ] 04-0x: Per-provider credential/scope setup docs (supports all of the above)

### Phase 5: Reference Adapter Breadth
**Goal**: Fan out the remaining reference providers through the Phase-4 framework — Webflow, Bitscale, Cal.com, Clockify, Beehiiv as direct adapters, and Xero via the aggregator — each independently landable and testable, reusing the credential-resolution / schema-validation / OTel-span machinery without rearchitecture.
**Depends on**: Phase 4
**Requirements**: TOOL-03
**Success Criteria** (what must be TRUE):
  1. Each reference provider (Webflow, Bitscale, Cal.com, Clockify, Beehiiv) has a working direct adapter behind the gateway with schema validation
  2. Xero executes through the aggregator path (financial category, approval-gated for writes)
  3. Each provider is independently skippable in the live lane; default suite stays green and creds-free
  4. Per-provider credential/scope setup docs extended to cover the new providers
**Plans**: 2-3 plans (set at planning)

Plans:
- [ ] 05-0x: Direct adapters — Webflow, Bitscale, Cal.com, Clockify, Beehiiv (TOOL-03)
- [ ] 05-0x: Xero via aggregator + credential docs (TOOL-03)

### Phase 6: Self-Improvement
**Goal**: Replace the `evaluate_proposal` stub with a real evaluation harness, and wire AI-BOM-on-promotion with controlled, versioned (non-hot) promotion and retained rollback — with no runtime mutation of active instructions, permissions, or routing (Option C).
**Depends on**: Phase 5
**Requirements**: SI-01, SI-02
**Success Criteria** (what must be TRUE):
  1. A self-improvement proposal is scored by a real evaluation harness, not a stub
  2. Promotion generates an AI-BOM snapshot from the deployment + tool-pack manifests and records a versioned promotion with rollback
  3. No active instructions/permissions/routing are mutated at runtime; the promoted artifact is referenceable only via versioned, non-hot wiring read at next start/deploy
  4. Default suite stays green and creds-free; any LLM-judge scoring runs only in the opt-in lane
**Plans**: 2 plans (set at planning)

Plans:
- [ ] 06-01: Real evaluation harness replacing the `evaluate_proposal` stub (SI-01)
- [ ] 06-02: AI-BOM-on-promotion + controlled versioned (non-hot) promotion wiring + rollback (SI-02)

### Phase 7: E2E Validation & Deploy-Readiness
**Goal**: Assemble all layers and prove the platform end-to-end — a write-gated Slack action from evidence, an MCP-triggered long checkpointed job returning an artifact, and the failure modes — then validate that the `gcloud` and `wrangler` deployment scripts are idempotent and GCP-ready without provisioning live resources.
**Depends on**: Phase 6
**Requirements**: E2E-01, E2E-02, E2E-03, DEP-01, DEP-02
**Success Criteria** (what must be TRUE):
  1. An end-to-end run proves Slack request → evidence → write-gated SaaS action → approval → completion
  2. An MCP request runs a long checkpointed mesh job and returns an artifact
  3. A failure E2E demonstrates model fallback, job retry, and budget-limit halt together
  4. The `gcloud` bootstrap/deploy and Cloudflare `wrangler` scripts pass lint + dry-run/syntax checks, and their resource-detection branches are unit-tested with a mocked `gcloud` (idempotency *logic* proven locally — true end-to-end idempotency against a live project is deferred to DEP-03); the deployment + tool-pack manifests are schema-consistent
**Plans**: 2 plans

Plans:
- [ ] 07-01: End-to-end test suite — Slack write-gated action, MCP checkpointed artifact, failure modes (E2E-01, E2E-02, E2E-03)
- [ ] 07-02: Deploy-readiness validation — idempotent gcloud/wrangler scripts + manifest consistency (DEP-01, DEP-02)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Durable Core & Approval Security | 3/3 | Complete | 2026-06-05 |
| 2. Real Orchestration Engine | 3/3 | Complete | 2026-06-06 |
| 3. Model Gateway & Observability | 4/4 | Complete | 2026-06-06 |
| 4. Tool Gateway Framework + First Adapters + Aggregators | 0/4 | Not started | - |
| 5. Reference Adapter Breadth | 0/3 | Not started | - |
| 6. Self-Improvement | 0/2 | Not started | - |
| 7. E2E Validation & Deploy-Readiness | 0/2 | Not started | - |
