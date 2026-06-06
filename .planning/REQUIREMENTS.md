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

### Self-Improvement

- [ ] **SI-01**: A real evaluation harness replaces the `evaluate_proposal` stub
- [ ] **SI-02**: Promotion generates an AI-BOM snapshot and wires controlled, versioned (non-hot) promotion; rollback retained; no runtime mutation of active instructions/permissions/routing

### Validation

- [ ] **E2E-01**: A Slack request creates a write-gated SaaS action from evidence and completes only after approval
- [ ] **E2E-02**: An MCP request triggers a long-running checkpointed mesh job and returns an artifact
- [ ] **E2E-03**: A failure E2E exercises model fallback, job retry, and budget-limit halt together

### Deploy-Readiness

- [ ] **DEP-01**: `gcloud` bootstrap + deploy scripts pass shellcheck/lint, `--dry-run`/`--help` syntax checks, and unit tests of their resource-detection branches with a mocked `gcloud` — proving the idempotency *logic* locally. (True end-to-end idempotency against a real project is deferred to DEP-03; this is the local-validation ceiling.)
- [ ] **DEP-02**: The Cloudflare `wrangler` deploy script passes lint + `wrangler --dry-run`, and the deployment + tool-pack manifests are schema-consistent — local-validation ceiling, no live publish

## v2 Requirements

Deferred to future milestones. Tracked, not in current roadmap.

### Live Deployment

- **DEP-03**: Live provisioning of Cloud SQL + Cloud Run in `australia-southeast1` and a live E2E run
- **DEP-04**: FinOps review of live telemetry against the USD $65 infra and USD $50 model guardrails

### Tool Coverage

- **TOOL-03**: Remaining reference tool adapters (Xero, Webflow, Bitscale, Cal.com, Clockify, Beehiiv) functional
- **TOOL-04**: Aggregate-MCP, Nango-aggregator, and Composio-aggregator (MCP-native fallback) integration styles exercised end-to-end. Composio and Nango are peer aggregator options (MCP-native single-endpoint vs open-source unified-API); see Spike 001 (`.planning/spikes/001-composio-vs-nango-coverage/`)

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
| OBS-01 | Phase 3 | Complete (tool-event spans deferred to Phase 4 / TOOL-01 — no tool adapters exist until then) |
| OBS-02 | Phase 3 | Complete |
| TOOL-01 | Phase 4 | Pending |
| TOOL-02 | Phase 4 | Pending |
| SI-01 | Phase 4 | Pending |
| SI-02 | Phase 4 | Pending |
| E2E-01 | Phase 5 | Pending |
| E2E-02 | Phase 5 | Pending |
| E2E-03 | Phase 5 | Pending |
| DEP-01 | Phase 5 | Pending |
| DEP-02 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 23 total
- Mapped to phases: 23
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-05*
*Last updated: 2026-06-05 after initial definition*
