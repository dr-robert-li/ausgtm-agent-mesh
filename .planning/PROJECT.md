# ausgtm-agent-mesh

## What This Is

A reusable, governed autonomous agent mesh — a reference platform for small
consultancies and client delivery teams to run long-lived, supervisor-orchestrated
AI agents against client SaaS systems with human-in-the-loop approval on every write.
It is built on the **LangChain + LangGraph + Deep Agents + Langfuse** stack, separates
a stable reusable platform boundary from deployment-specific client/SaaS bindings, and
targets GCP Sydney (`australia-southeast1`) for its first MVP/POC. This milestone
completes the existing runnable scaffold — replacing every stubbed component with a
real, locally-validated implementation — so the platform is end-to-end testable and
ready for GCP deployment configuration.

## Core Value

A long-running agent mesh can take a real client request through ingress, durable
orchestration, and a write-gated tool action — with that write blocked until a human
approves it — and the entire run is observable and auditable. If everything else fails,
**the human-in-the-loop write-approval gate must hold and the run must be durable.**

## Requirements

### Validated

<!-- Inferred from the existing scaffold (.planning/codebase/*); coded and tested without cloud deps. -->

- ✓ Canonical Task contract + lifecycle state machine normalizing Slack/MCP/API ingress — existing
- ✓ Write-action approval gating with payload-hash replay binding — existing
- ✓ Tenant-partitioned data contracts (Pydantic v2 + JSON Schema export) — existing
- ✓ FastAPI ingress (health/tasks/Slack-events/MCP/approvals) + Slack signature verify — existing
- ✓ Self-improvement loop (Option C) as inert proposals → evaluate → approve → versioned promotion → rollback — existing
- ✓ GUI admin read-model (Streamlit) + tool-pack manifest loader — existing
- ✓ Model-gateway routing profile config + Langfuse observability seam (interfaces only) — existing
- ✓ Prompt-to-code sandbox skeleton (isolated subprocess, resource limits) — existing
- ✓ Cloud SQL + pgvector migrations (`0001_init.sql`, `0002_self_improvement.sql`) — existing

### Active

<!-- This milestone: complete every stub to real + locally validated. Hypotheses until shipped. -->

- [ ] Postgres-backed repository replaces in-memory singleton; state survives restart
- [ ] Tenant-scoped reads enforced across all repository read paths
- [ ] Pub/Sub dispatch wiring at runtime (in-process fallback retained)
- [ ] `/v1/approvals` authenticated (signed approval token / HMAC); forged approvals rejected
- [ ] Replay + payload-mutation tests prove the approval gate holds
- [ ] Real LangGraph supervisor graph with bounded Deep Agents roster (planner, researcher/tool-router, code-writer, reviewer)
- [ ] LangGraph Postgres checkpointer wired; >60-min runs resume from durable checkpoint
- [ ] Interrupt-based HITL approval pause/resume from the checkpoint
- [ ] Hardened prompt-to-code sandbox isolation (no fail-open memory limit; container path)
- [ ] Live LiteLLM-compatible gateway (Anthropic-direct + Vertex AI) with USD $50/mo budget enforcement + cascades
- [ ] Cloudflare AI Gateway integrated as upstream governance plane (logging/DLP/guardrails)
- [ ] Budget-limit halt + model fallback validated under failure test
- [ ] Langfuse telemetry wired (spans, token/cost, task/tool/approval correlation via shared metadata)
- [ ] Langfuse prompt/version management + datasets/evals configured
- [ ] ≥1 real SaaS tool adapter functional locally behind the Tool Gateway contract
- [ ] Tool input/output JSON-schema validation enforced at the tool boundary
- [ ] Real self-improvement evaluation harness replaces the stub
- [ ] AI-BOM snapshot generation on promotion + controlled (versioned, non-hot) promotion wiring
- [ ] E2E: Slack request → write-gated SaaS action from evidence with approval (green)
- [ ] E2E: MCP request → long-running checkpointed mesh job → returned artifact (green)
- [ ] Failure E2E: model fallback, job retry, budget-limit halt
- [ ] `gcloud` bootstrap/deploy + `wrangler` scripts validated idempotent via dry-run/local checks

### Out of Scope

<!-- Explicit boundaries for THIS milestone. -->

- Live GCP deployment (provisioning real Cloud SQL / Cloud Run) — **deploy-ready only** this cycle; defers infra + token cost until scripts are validated locally
- Cloud SQL HA / multi-region — non-critical POC; documented as production hardening (caveat §13)
- Immutable / hash-chained approval ledger — production hardening (caveat §4); POC keeps mutable `approval_records`
- Default-deny egress controls, kill switches, signed images / SBOM / dependency scanning — production hardening (caveats §6, §8, §10)
- External immutable audit archive + GDPR deletion workflows — production hardening (caveats §5, §12)
- Full SaaS tool-pack coverage (Xero/Webflow/Bitscale/Cal.com/Clockify/Beehiiv) — only ≥1 real adapter this milestone; remainder stay manifest-declared stubs
- Temporal durable-workflow engine — Task contract stays Temporal-ready; not introduced now
- Runtime autonomous self-modification of active instructions/permissions/routing — permanently excluded by the Option C safety model

## Context

- **Brownfield.** A runnable Python-first scaffold already exists (`src/agent_mesh/`), exercised by `make test` / `make smoke` with no cloud deps. Heavy deps (langchain, langgraph, deepagents, langfuse, streamlit, pubsub, mcp) are lazy-imported and degrade to in-process stubs. This milestone turns stubs into real implementations.
- **Architecture is mapped** in `.planning/codebase/` (ARCHITECTURE.md, CONCERNS.md, STACK.md, etc.). The normative design pattern is `CLAUDE.md`; hardening backlog is `docs/production-readiness-caveats.md` (15 items).
- **Known critical gap addressed this milestone:** `/v1/approvals` currently accepts a self-asserted `approver_id` with no signature — anyone can forge an approval and bypass the core write gate (CONCERNS.md, Critical #1). Fixing it is an Active requirement.
- **Prior GSD phases** (May 2026 Phase 1/2 persistence + LangGraph skeleton) predate the stack switch to the LangChain variant and are not in current `main` history; this initialization re-establishes the roadmap over the current scaffold.
- **Data residency:** durable stores stay in `australia-southeast1`; model inference may leave Australia for the POC.

## Constraints

- **Tech stack**: LangChain + LangGraph + Deep Agents + Langfuse are REQUIRED and non-negotiable — LangSmith is optional-only, never a dependency. Python-first core, TypeScript only at the Cloudflare edge.
- **Security**: every write-class tool (write, external_send, financial, publishing, admin, code) must remain approval-gated through the shared ledger with payload-hash binding.
- **Budget**: USD $50/month configurable model budget enforced at the gateway, per-user/per-task attribution. POC infra target ~USD $40–65/mo (not incurred this milestone — deploy-ready only).
- **Region**: durable data stores in `australia-southeast1`; model processing may leave AU for the POC.
- **Execution duration**: long mesh runs may exceed 60 minutes and must survive via LangGraph checkpoints + durable task records.
- **Governance**: model traffic governed by Cloudflare AI Gateway (DLP/blocking/guardrails); SaaS tool-write governance stays in the Tool Gateway approval ledger. Neither gateway substitutes for the other.
- **Redeployability**: reusable platform components stay separate from client-specific adapters, credentials, SaaS schemas, and approval policies; deployment scripts must be idempotent.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Full-vertical milestone scope (complete all stubs to local-validated) | The `/goal` is "all functions" E2E-tested + deploy-ready; partial completion leaves the mesh unprovable end-to-end | — Pending |
| Deploy-ready only (no live GCP provisioning) | Keep POC cost at zero until scripts validate idempotent locally; live deploy is a separate decision | — Pending |
| Fix `/v1/approvals` auth this milestone | Critical finding bypasses the core write-approval gate — the platform's Core Value — so it cannot wait for a hardening milestone | — Pending |
| Coarse granularity, standard (horizontal-layer) phasing | Work replaces real technical layers (durability → orchestration → model/observability → tools/SI) over a working E2E scaffold; a final phase assembles + validates | — Pending |
| Quality model profile (Opus for planning agents) | Real framework-integration wiring (LangGraph checkpointer, Deep Agents, Cloudflare) rewards deeper planning | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-05 after initialization*
