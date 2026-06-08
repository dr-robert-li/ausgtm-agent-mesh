# Requirements: ausgtm-agent-mesh

**Defined:** 2026-06-05
**Core Value:** A long-running agent mesh takes a real client request through ingress, durable orchestration, and a write-gated tool action — the write blocked until a human approves it — and the whole run is observable and auditable.

## v1 Requirements

Requirements for this completion milestone: replace every stubbed component in the
existing scaffold with a real, locally-validated implementation, then prove the
platform end-to-end and validate deploy-readiness. Each maps to a roadmap phase.

### Durability

- [x] **DUR-01**: Postgres-backed repository replaces the in-memory singleton; tasks, sessions, approvals, and tool-calls survive a worker restart
- [x] **DUR-02**: All repository read paths are tenant-scoped (e.g. `list_events`, `list_evaluations` require `tenant_id`); a cross-tenant read returns nothing
- [x] **DUR-03**: Pub/Sub dispatch is wired at runtime with the in-process dispatcher retained as fallback

### Security

- [x] **SEC-01**: `/v1/approvals` verifies a signed approval token (HMAC/JWT) issued at request time; a forged or self-asserted `approver_id` is rejected
- [x] **SEC-02**: The approval gate has replay and payload-mutation tests proving a mutated payload invalidates a prior approval and an approval cannot be reused across tasks

### Orchestration

- [x] **ORCH-01**: A real LangGraph supervisor graph delegates to a bounded Deep Agents roster (planner, researcher/tool-router, code-writer, reviewer); roster is declared and its size logged at startup
- [x] **ORCH-02**: The LangGraph Postgres checkpointer is wired; a >60-minute run resumes from its durable checkpoint after a process restart
- [x] **ORCH-03**: A write approval is a LangGraph interrupt that pauses the graph and resumes from the checkpoint when the decision arrives

### Sandbox

- [x] **SBX-01**: The prompt-to-code sandbox enforces memory limits without failing open and executes via a hardened container path (Docker/Cloud Run Job)

### Model Gateway

- [x] **GW-01
**: A live LiteLLM-compatible gateway routes to Anthropic-direct and Vertex AI with cascades and enforces a USD $50/month per-user/per-task budget
- [x] **GW-02
**: The gateway routes all upstream model calls through the Cloudflare AI Gateway (logging/DLP/guardrails) when enabled; agents never call providers directly
- [x] **GW-03
**: A failure test proves model fallback and budget-limit halt behave correctly

### Observability

- [x] **OBS-01
**: Langfuse telemetry is wired so spans, token/cost, and task/tool/approval events correlate via shared request metadata (`tenant_id`, `task_id`, `session_id`, `requester_id`, `approval_state`)
- [x] **OBS-02
**: Langfuse prompt/version management and datasets/evals are configured

### Tools

- [ ] **TOOL-01**: At least one real SaaS tool adapter (Google Workspace or HubSpot) executes a real call locally behind the Tool Gateway with credential resolution at execution time
- [ ] **TOOL-02**: Tool input and output are validated against JSON Schema at the tool boundary
- [x] **TOOL-03
**: Remaining reference tool adapters functional — Webflow, Bitscale, Cal.com, Clockify, Beehiiv as direct adapters; Xero via aggregator _(promoted v2→v1 2026-06-06: POC-as-MVP full tool coverage)_
- [ ] **TOOL-04**: Aggregate-MCP, Nango-aggregator, and Composio-aggregator (MCP-native) integration styles exercised end-to-end. Composio primary + Nango fallback (peer aggregator options — MCP-native single-endpoint vs open-source unified-API); see Spike 001 (`.planning/spikes/001-composio-vs-nango-coverage/`) _(promoted v2→v1 2026-06-06)_

### Self-Improvement

_Re-scoped 2026-06-07 (deep-research review of 2025–2026 self-evolving-agent SOTA): Phase 6
expanded from stub-replacement to the real, Option-C-safe self-improvement **loop**. See
`.planning/phases/06-self-improvement/06-CONTEXT.md` and `docs/self-improvement-loop.md`._

- [ ] **SI-01**: A real evaluation harness replaces the `evaluate_proposal` stub — proposals are
  scored by a Langfuse experiment run over a versioned held-out dataset, with item-level +
  run-level no-regression gating vs the promoted baseline
  - [ ] **SI-01a**: Proposals are scored on a held-out/realistic task set **distinct from any
    signal the proposer optimized against** (anti-reward-hack control); the gate never reads the
    optimization signal
  - [ ] **SI-01b**: Promotion-eligibility requires candidate ≥ baseline on aggregate gate metrics
    **AND** no item-level regression beyond a configured threshold
  - [ ] **SI-01c**: Held-out eval items are deterministic frozen-context snapshots so candidate
    and baseline are scored on identical inputs
  - [ ] **SI-01d**: Any LLM-judge dimension runs **only** in the `live` opt-in lane, with
    position-bias control (order-swap), calibrated against a human-labelled set (TPR/FPR) under a
    statistically valid below-threshold / finite-sample Type-I gate, and is never the sole arbiter
    for close-margin proposals; the default suite stays creds-free
- [ ] **SI-02**: Promotion generates an AI-BOM snapshot and wires controlled, versioned (non-hot)
  promotion; rollback retained; no runtime mutation of active instructions/permissions/routing
  - [ ] **SI-02a**: The promotion snapshot is a **CycloneDX ML-BOM** (ECMA-424 v1.7) generated
    from the deployment + tool-pack manifests (prompts/tools/models/routes/dataset version/eval
    results), bound to the promoted version and retained for rollback + audit
  - [x] **SI-02b
**: The promoted artifact is referenceable **only via versioned, non-hot wiring
    read at next start/deploy**; rollback re-points the active version to `previous_version`;
    both proven by tests (a promotion does not change running config until an explicit
    reload/boot step)
- [ ] **SI-03**: A log-driven reflective proposer (GEPA-style), run as a **separated, offline
  meta-agent**, mines collected traces and emits **inert** prompt/workflow diffs only (never
  applies, never auto-promotes); the improvement loop caps optimization iterations and
  re-validates on the held-out set each round (held-out protected from proposer visibility)

### Validation

- [ ] **E2E-01**: A Slack request creates a write-gated SaaS action from evidence and completes only after approval
- [x] **E2E-02
**: An MCP request triggers a long-running checkpointed mesh job and returns an artifact
- [ ] **E2E-03**: A failure E2E exercises model fallback, job retry, and budget-limit halt together

### Deploy-Readiness

- [ ] **DEP-01**: `gcloud` bootstrap + deploy scripts pass shellcheck/lint, `--dry-run`/`--help` syntax checks, and unit tests of their resource-detection branches with a mocked `gcloud` — proving the idempotency *logic* locally. (True end-to-end idempotency against a real project is deferred to DEP-03; this is the local-validation ceiling.)
- [ ] **DEP-02**: The Cloudflare `wrangler` deploy script passes lint + `wrangler --dry-run`, and the deployment + tool-pack manifests are schema-consistent — local-validation ceiling, no live publish

## v1.1 Requirements — Milestone v1.1: Local / Offline Deployability

New milestone (2026-06-08). Run the whole mesh **fully local and offline**: local inference
(vLLM + Ollama behind LiteLLM), a full-stack docker-compose, local Postgres(pgvector) +
self-hosted Langfuse, and an offline no-egress posture. **Guardrail: config / docker-compose /
docs / tests ONLY — zero production code change.** Deployment names (`low/medium/high-complexity`)
stay constant so agent/gateway code is untouched. Offline enforcement is test-asserted over
config, not a runtime `src/` guard. Phases continue at 08.

### Local Inference (Phase 8)

- [x] **LOCAL-01
**: A `config/model_gateway.vllm.yaml` profile routes all three tiers to a local vLLM OpenAI-compatible endpoint behind LiteLLM (`hosted_vllm/*` + local `api_base`); a `make run-vllm` target starts the server
- [x] **LOCAL-02
**: A `config/model_gateway.ollama.yaml` profile routes all three tiers to a local Ollama endpoint behind LiteLLM; a `make run-ollama` target starts/pulls it
- [x] **LOCAL-03
**: RUNBOOK has a "Local inference lane" section: how to run each backend, how the Router selects a profile (config path / env), and the tool-calling model-capability caveat
- [x] **LOCAL-04
**: A config-validation test asserts each local profile defines all three deployment names with a local `api_base` and builds via `build_router` with no network call

### Local Data & Telemetry (Phase 9)

- [ ] **LDATA-01**: A local Postgres(pgvector) run path is documented + make-wired to `DATABASE_URL`/`TEST_DATABASE_URL` and applies the existing migrations
- [ ] **LDATA-02**: A self-hosted Langfuse local run path is documented with its env wiring (`LANGFUSE_HOST`, keys) for local trace ingestion
- [ ] **LDATA-03**: The durable lane runs locally end to end (`make test-pg` against the local DSN); a test asserts the local-DSN path applies migrations and is reachable, loud-skip when unset

### Full-Stack Compose (Phase 10)

- [ ] **COMPOSE-01**: A `docker-compose.yml` brings up api + worker + gui + Postgres(pgvector) + Langfuse + LiteLLM + a local model backend (vLLM or Ollama) with one command
- [ ] **COMPOSE-02**: `make compose-up` / `make compose-down` wrap the stack; RUNBOOK documents the one-command local bring-up
- [ ] **COMPOSE-03**: A test/lint validates the compose file (`docker compose config` parses; required services + healthchecks + the pgvector image present), loud-skip when docker is absent

### Offline / No-Egress (Phase 11)

- [ ] **OFFLINE-01**: An OFFLINE posture is expressible via config/.env (CF off, no Vertex/Anthropic keys, local-only `api_base`, `.env`-sourced secrets) and documented in RUNBOOK
- [ ] **OFFLINE-02**: A test asserts the local/offline model profiles contain NO cloud `api_base` (no Vertex/Anthropic/CF wrapper URL) and no cloud-key env references — egress-free by construction
- [ ] **OFFLINE-03**: A test asserts the default creds-free lane performs no outbound network to a real provider/gateway (the existing stub posture, made explicit and enforced)

## v2 Requirements

Deferred to future milestones. Tracked, not in current roadmap.

### Live Deployment

- **DEP-03**: Live provisioning of Cloud SQL + Cloud Run in `australia-southeast1` and a live E2E run
- **DEP-04**: FinOps review of live telemetry against the USD $65 infra and USD $50 model guardrails

### Self-Evolving Surfaces (new milestone — "Self-Evolving Surfaces")

_Deferred from Phase 6 (2026-06-07). A different evolve-surface than prompts/tools/routes; needs
new data models and new regression controls. Flows through the same Phase-6 proposal→eval→ML-BOM→
promotion gate, Option-C-safe._

- **SI-04**: Memory growth/compression + skill-library promotion as governed, inert proposals,
  with memory-poisoning regression controls
- **SI-05**: Multi-agent topology / routing-depth evolution as governed, inert proposals, with
  co-evolutionary-drift controls

_(TOOL-03 and TOOL-04 promoted v2→v1 on 2026-06-06 — see Tools under v1. Driver: user reframed POC as MVP requiring viable general tool coverage, not a single-adapter proof.)_

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Live GCP provisioning this milestone | Deploy-ready only; keeps POC cost at zero until scripts validate locally |
| Cloud SQL HA / multi-region | Non-critical POC; production hardening (caveat §13) |
| Immutable / hash-chained approval ledger | Production hardening (caveat §4); POC keeps mutable `approval_records` |
| Default-deny egress, kill switches, signed images / SBOM | Production hardening (caveats §6, §8, §10) |
| External immutable audit archive + GDPR deletion | Production hardening (caveats §5, §12) |
| Temporal durable-workflow engine | Task contract stays Temporal-ready; not introduced now |
| Runtime autonomous self-modification | Permanently excluded by the Option C safety model |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DUR-01 | Phase 1 | Complete |
| DUR-02 | Phase 1 | Complete |
| DUR-03 | Phase 1 | Complete |
| SEC-01 | Phase 1 | Complete |
| SEC-02 | Phase 1 | Complete |
| ORCH-01 | Phase 2 | Complete |
| ORCH-02 | Phase 2 | Complete |
| ORCH-03 | Phase 2 | Complete |
| SBX-01 | Phase 2 | Complete |
| GW-01 | Phase 3 | Complete |
| GW-02 | Phase 3 | Complete |
| GW-03 | Phase 3 | Complete |
| OBS-01 | Phase 3 | Complete (tool-event spans deferred to Phase 4 framework — closed there once a real adapter exists) |
| OBS-02 | Phase 3 | Complete |
| TOOL-01 | Phase 4 | Pending |
| TOOL-02 | Phase 4 | Pending |
| TOOL-04 | Phase 4 | Pending |
| TOOL-03 | Phase 5 | Pending |
| SI-01 (+SI-01a–d) | Phase 6 | Pending |
| SI-02 (+SI-02a–b) | Phase 6 | Pending |
| SI-03 | Phase 6 | Pending |
| SI-04 | Milestone "Self-Evolving Surfaces" | Deferred (v2) |
| SI-05 | Milestone "Self-Evolving Surfaces" | Deferred (v2) |
| E2E-01 | Phase 7 | Complete |
| E2E-02 | Phase 7 | Complete |
| E2E-03 | Phase 7 | Complete |
| DEP-01 | Phase 7 | Complete |
| DEP-02 | Phase 7 | Complete |
| LOCAL-01 | Phase 8 | Complete |
| LOCAL-02 | Phase 8 | Complete |
| LOCAL-03 | Phase 8 | Complete |
| LOCAL-04 | Phase 8 | Complete |
| LDATA-01 | Phase 9 | Pending |
| LDATA-02 | Phase 9 | Pending |
| LDATA-03 | Phase 9 | Pending |
| COMPOSE-01 | Phase 10 | Pending |
| COMPOSE-02 | Phase 10 | Pending |
| COMPOSE-03 | Phase 10 | Pending |
| OFFLINE-01 | Phase 11 | Pending |
| OFFLINE-02 | Phase 11 | Pending |
| OFFLINE-03 | Phase 11 | Pending |

**Coverage:**
- v1.0 requirements: 26 top-level — all mapped to Phases 1–7; Phases 1–7 complete (2026-06-08)
- v1.1 requirements: 13 (LOCAL ×4, LDATA ×3, COMPOSE ×3, OFFLINE ×3) — all mapped to Phases 8–11
- Unmapped: 0 ✓
- Deferred to "Self-Evolving Surfaces" milestone (v2): SI-04, SI-05

**Re-scope note (2026-06-06):** TOOL-03/04 promoted v2→v1; tool work split across Phases 4–5,
self-improvement moved to Phase 6, E2E + deploy-readiness to Phase 7. Milestone grew 5→7 phases.

**Re-scope note (2026-06-07):** Deep-research review of 2025–2026 self-evolving-agent SOTA.
Phase 6 expanded from stub-replacement to the real Option-C self-improvement **loop**: SI-01
sharpened (+SI-01a–d: held-out-distinct, item+run no-regression, frozen-context snapshots,
opt-in calibrated judge), SI-02 sharpened (+SI-02a–b: CycloneDX ML-BOM, non-hot wiring +
rollback), **SI-03 added** (GEPA-style offline inert proposer + bounded loop). Memory/skill/
topology evolution deferred to a new "Self-Evolving Surfaces" milestone (SI-04, SI-05). The
milestone is re-scoped to a governed self-evolving-agent build (PROJECT.md update + new-milestone
creation are follow-up steps via `/gsd:new-milestone`).

**Milestone v1.1 note (2026-06-08):** v1.0 (Phases 1–7) complete — full local-validated
scaffold, deploy-ready. New milestone v1.1 "Local / Offline Deployability" adds 13 requirements
(LOCAL/LDATA/COMPOSE/OFFLINE) across Phases 8–11, config/compose/docs/tests-only, zero
production code change. v1.0 not yet archived via `/gsd:complete-milestone` — phase history 01–07
preserved in place.

---
*Requirements defined: 2026-06-05*
*Last updated: 2026-06-08 — milestone v1.1 (Local/Offline Deployability) requirements added (LOCAL/LDATA/COMPOSE/OFFLINE, Phases 8–11); v1.0 Phases 1–7 marked complete*
