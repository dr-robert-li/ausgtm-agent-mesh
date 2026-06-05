# Codebase Concerns

**Analysis Date:** 2026-06-05

## Overview

This codebase is an explicitly **not-production-ready POC** of a reusable autonomous agent mesh. The architecture is sound and well-documented, but it defers critical hardening to production phases. This document captures:

1. **Documented limitations** (from `docs/production-readiness-caveats.md`) that are deferred by design
2. **Code-grounded issues** not covered in the caveats (implementation gaps specific to this scaffold)
3. **Security, data isolation, and operational concerns** that require attention before any production use

**Key principle:** Labeled hardening tasks are *intentional design deferments*; unlabeled findings are implementation gaps in the scaffold itself.

---

## Documented Production Hardening (Deferred, In-Scope for Production)

The following 15 items are catalogued in `docs/production-readiness-caveats.md` as explicitly out-of-scope for this POC but **required before production workloads**:

### 1. Secure Container / Sandbox Prompt-to-Code Execution (§1)

**Files:** `src/agent_mesh/sandbox/executor.py`

**What it is:** The POC runs prompt-to-code in a subprocess sandbox with resource limits (CPU, memory, timeout). It is deliberately isolated from the repo but does not meet production isolation standards.

**Gap:** No gVisor/Kata VM, no hardened container, no least-privilege service accounts, no explicit network egress allowlist, no read-only base images. Subprocess isolation is permissive by POC design.

**Production requirement:** Hardened containers (Cloud Run Jobs with gVisor/Kata) with zero-trust execution.

---

### 2. Durable Orchestration (§2)

**Files:** `src/agent_mesh/services/task_service.py`, `src/agent_mesh/services/dispatch.py`, `src/agent_mesh/services/repository.py`

**What it is:** For >60-minute mesh runs, state must be persisted before dispatch and resumed from durable storage. The code correctly *frames* this requirement (`task_service.py` lines 38–57), but the actual repository is **in-memory** (`repository.py` lines 153–167, global singleton).

**Gap:** Durability is **aspirational in the POC**. State is persisted to a process-wide dict, not a durable store. A worker crash loses all pending/in-flight state. The Postgres migration exists (`migrations/0001_init.sql`), but the `RepositorySQL` implementation is not wired.

**Production requirement:** Temporal or equivalent durable workflow engine; Postgres-backed repository with LangGraph checkpointer.

---

### 3. Tenant Isolation (§3)

**Files:** `src/agent_mesh/services/repository.py` (lines 96–100, 115–117), `migrations/0001_init.sql`

**What it is:** All tables carry `tenant_id` columns. The in-memory repo filters by tenant only when explicitly requested; read operations do not enforce tenant scoping by default.

**Gap:** `InMemoryRepository.list_events()` (line 99) filters by `task_id` only, not by `tenant_id`. A query for task events crosses the tenant boundary if called naively. The Postgres schema includes `tenant_id` indexes, but row-level security is not implemented in the migrations.

**Production requirement:** Row-level security, schema-per-tenant, or database-per-tenant with per-tenant encryption keys and service accounts.

---

### 4. Immutable Approval Ledger (§4)

**Files:** `src/agent_mesh/services/approvals.py`, `migrations/0001_init.sql` (approval_records table)

**What it is:** Approvals are stored in `approval_records`, but the table allows in-place updates (`upsert_approval` calls `UPDATE`).

**Gap:** No append-only enforcement, no hash chaining, no tamper-evidence, no immutable ledger backend (WORM / object lock). Approvals can be modified after the fact.

**Production requirement:** Append-only, hash-chained ledger; signed approvals; tamper-evidence verification.

---

### 5. Externalized 12+ Month Audit Retention (§5)

**Files:** `migrations/0001_init.sql`, `docs/production-readiness-caveats.md` §5

**What it is:** The POC retains traces, AI-BOM snapshots, approvals, and tool calls for 12 months in-platform.

**Gap:** No external archive to immutable object storage (e.g., GCS with retention lock). When Langfuse storage fills or data is deleted, there is no recovery from an independent, tamper-evident external store.

**Production requirement:** Export audit streams to immutable object storage on a regular cadence; independent integrity checks; restore tests.

---

### 6. Egress Controls (§6)

**Files:** `src/agent_mesh/worker/model_gateway.py`, `src/agent_mesh/tools/gateway.py`

**What it is:** Model and SaaS traffic is routed through configurable gateways. No default-deny network policy.

**Gap:** Workers can reach any model provider or SaaS endpoint. No DNS/proxy filtering, no egress allowlist, no monitoring/alerting on unexpected destinations.

**Production requirement:** Default-deny egress; explicit allowlists per service; DNS filtering; egress monitoring.

---

### 7. Short-Lived / Scoped Credentials and Rotation (§7)

**Files:** `src/agent_mesh/settings.py` (lines 67–75, 78)

**What it is:** Credentials are pulled from environment variables (Secret Manager entries in prod) but are never rotated in the POC.

**Gap:** Long-lived secrets; no per-tool minimal scopes; no automated rotation; no credential expiration.

**Production requirement:** Workload Identity Federation, short-lived OAuth token exchange, per-tool scoped credentials, automated rotation runbooks.

---

### 8. CI/CD, Signed Images, SBOM, Dependency Scanning (§8)

**Files:** `docker/`, `scripts/`

**What it is:** Deployment scripts build and push images to Artifact Registry but do not sign them or generate SBOMs.

**Gap:** No cosign signatures, no admission control for image verification, no SBOM generation, no dependency vulnerability scanning with policy gates.

**Production requirement:** Signed container images, SBOM per release, automated dependency scanning, policy gates on vulnerability discovery.

---

### 9. Automated Evals / Regression Testing (§9)

**Files:** `src/agent_mesh/services/self_improvement.py`, `tests/test_self_improvement.py`

**What it is:** The self-improvement loop includes an `evaluate_proposal(...)` seam. The POC implementation runs deterministic checks.

**Gap:** No real evaluation harness, no adversarial prompt tests, no guardrail/DLP regression checks, no cost baselines. Evaluation is a stub.

**Production requirement:** Real eval sets, golden-path and adversarial prompt tests, tool-call contract tests, cost/token regression baselines, run-on-merge gating.

---

### 10. Kill Switches and Incident Response (§10)

**Files:** None — not implemented

**What it is:** No kill switches or incident-response infrastructure.

**Gap:** No per-tenant or global pause of mesh execution, model traffic, or tool writes. No documented runbook, on-call ownership, or incident-response automation.

**Production requirement:** Fast kill switches (testable and independent), incident-response runbook with severities/comms/review process.

---

### 11. Memory / Vector Retrieval Governance (§11)

**Files:** `migrations/0001_init.sql` (memory_chunks, retrieval_document_chunks, tool_evidence_chunks), `src/agent_mesh/services/repository.py`

**What it is:** Memory and evidence chunks are stored with embeddings in Cloud SQL + pgvector, separated by type.

**Gap:** No retrieval access controls, no provenance/freshness enforcement, no evidence-pointer auditing, no poisoning/PII safeguards on ingestion. Schema includes `metadata`, but governance is not wired.

**Production requirement:** Access controls on retrieval, provenance tracking, freshness enforcement, poison/PII detection, migration path to dedicated vector store.

---

### 12. Data Retention / Deletion Policy (§12)

**Files:** None — not implemented

**What it is:** No explicit retention or deletion workflows.

**Gap:** No defined retention tiers per data class, no right-to-erasure workflow, no deletion propagation across memory/evidence/traces/logs/backups, no verification of deletion SLA.

**Production requirement:** Explicit retention policy, GDPR-compliant deletion workflows, deletion propagation, audit of deletes.

---

### 13. Multi-Region / HA Decision (§13)

**Files:** `scripts/gcp_bootstrap.sh`, `RUNBOOK.md` (lines 84–101)

**What it is:** POC uses non-HA, single-zone Cloud SQL in `australia-southeast1` and accepts the DB SPOF.

**Gap:** No automated failover, no backup/restore RTO/RPO, no multi-region replication.

**Production requirement:** If workload becomes critical, implement Cloud SQL HA (regional), read replicas, documented failover procedures, HA cost acceptance.

---

### 14. Operational SLOs and Monitoring (§14)

**Files:** `src/agent_mesh/observability.py`, `src/agent_mesh/gui/admin_console.py`

**What it is:** Langfuse/OpenTelemetry telemetry is wired, and the admin console reads observability metadata.

**Gap:** No defined SLOs/SLIs (task success rate, latency, approval turnaround, budget-halt correctness, gateway availability), no alerting thresholds, no error budgets, no on-call escalation.

**Production requirement:** Defined SLOs/SLIs with dashboards and alerting; on-call coverage and escalation paths.

---

### 15. Self-Improvement Loop Hardening (§15)

**Files:** `src/agent_mesh/services/self_improvement.py`, `src/agent_mesh/worker/orchestrator.py`, `docs/self-improvement-loop.md`

**What it is:** Self-improvement (Option C) is proposal → eval → approval → promotion. The loop is inert in the POC.

**Gaps:**
- `evaluate_proposal()` (lines 149–175 in `self_improvement.py`) is a stub; no real eval harness.
- No promotion → runtime wiring. A promoted `PromotionRecord` records a versioned change but does not reload/apply it to the live system.
- No AI-BOM snapshot generation on promotion (link field `ai_bom_snapshot_id` exists but is unused).
- No reflection subagent in the live LangGraph + Deep Agents supervisor.

**Production requirement:** Real evaluation harness, versioned config reload with controlled rollout (never hot in-place rewrites), AI-BOM snapshot generation on promotion, live reflection subagent, hard boundaries against autonomous modification.

---

## Code-Grounded Issues (Not in Documented Caveats)

### Security: Unauthenticated Approval Callback Endpoint

**Files:** `src/agent_mesh/api/app.py` (lines 89–101), `src/agent_mesh/api/mcp_server.py` (lines 58–75)

**Issue:** The `/v1/approvals` HTTP endpoint accepts an `approver_id` directly from the request payload without signature or bearer-token verification:

```python
@app.post("/v1/approvals")
def submit_approval(payload: dict) -> dict[str, str]:
    """Approval decision callback shared by Slack and MCP requesters."""
    record = _service.submit_approval_decision(
        approval_record_id=payload["approval_record_id"],
        decision=ApprovalDecision(payload["decision"]),
        approver_id=payload["approver_id"],  # Self-asserted, no verification
        channel=payload.get("channel", "api"),
    )
```

**Contrast:** `/slack/events` (line 59) verifies the Slack signature before trusting the payload. The approval endpoint does not.

**Impact:** **Critical for POC→Production:** Any client can forge an approval decision for any task by POSTing to `/v1/approvals` with a guessed `approval_record_id` and a spoofed `approver_id`. This defeats the entire write-approval gate promised by the architecture. The approval ledger records *who* decided, but it does not verify *that person is who they claim*.

**Risk level:** High. The architecture's core safety property (human-in-the-loop approval for writes) is bypassed.

**Recommended fix:**
- Add HMAC or JWT signature verification to `/v1/approvals`, mirroring Slack signature verify.
- Use a short-lived, signed approval token (issued when the approval request is created) rather than accept a self-asserted `approver_id`.
- For Slack: deliver the approval decision *through* Slack's button/modal so Slack's auth is leverage.
- For MCP: attach bearer token or HMAC to the approval decision request.

---

### Data Isolation: In-Memory Repo Reads Cross Tenant Boundaries

**Files:** `src/agent_mesh/services/repository.py` (lines 96–100, 139–141)

**Issue:** `InMemoryRepository.list_events()` and `list_evaluations()` do not filter by `tenant_id`:

```python
def list_events(self, task_id: str) -> list[TaskEvent]:
    with self._lock:
        return [e for e in self._events if e.task_id == task_id]  # No tenant filter

def list_evaluations(self, proposal_id: str) -> list[EvaluationResult]:
    with self._lock:
        return [e for e in self._evaluations.values() if e.proposal_id == proposal_id]  # No tenant filter
```

While `task_id` and `proposal_id` are globally unique (UUIDs), a careless caller could iterate task events without scoping them to a tenant, or could enumerate proposal evaluations across all tenants if proposal IDs are guessed/enumerated.

**Impact:** Medium. The in-memory repo is a POC; the Postgres migration will enforce `tenant_id` indexes and RLS. But the protocol (`Repository` interface, lines 28–48) does not mandate tenant filtering, so the same mistake could propagate to a Postgres implementation.

**Recommended fix:**
- Add `tenant_id` parameter to `list_events(task_id, tenant_id)` and `list_evaluations(proposal_id, tenant_id)` so callers must assert tenancy.
- Document in the `Repository` protocol that all read operations must be tenant-scoped.

---

### Durability: In-Memory State Not Persisted

**Files:** `src/agent_mesh/services/repository.py` (lines 153–167), `src/agent_mesh/services/task_service.py` (lines 37–58)

**Issue:** `task_service.create_task()` documents "State is persisted BEFORE dispatch so a worker can always resume from a durable record" (line 40–41), but the actual repository is a global in-memory singleton:

```python
_SINGLETON: InMemoryRepository | None = None

def get_repository() -> Repository:
    """..."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = InMemoryRepository()  # Never persisted to disk/DB
    return _SINGLETON
```

The "durability" claim in the docstring is aspirational only. A process crash loses all state.

**Impact:** Medium for the POC (expected limitation); Critical if deployed to production without Postgres wiring.

**Recommended fix:**
- Document the in-memory singleton's limitations clearly: "Suitable for local testing and smoke checks only."
- Wire the Postgres-backed `RepositorySQL` implementation (migration `0001_init.sql` exists but is unused) for any long-running deployment.
- Add a runtime check that raises if `DATABASE_URL` is unset and a worker is started (not just an ingress service).

---

### Sandbox Execution: Memory Limits Fail Open

**Files:** `src/agent_mesh/sandbox/executor.py` (lines 40–51)

**Issue:** `_preexec()` applies CPU and memory limits, but memory limit (RLIMIT_AS) **fails open**:

```python
def _preexec(limits: SandboxLimits):
    def _apply() -> None:
        import resource
        cpu = limits.max_cpu_seconds
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        mem = limits.max_memory_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        except (ValueError, OSError):
            # Some platforms reject RLIMIT_AS; fail open on the memory cap only.
            pass
```

On platforms that reject RLIMIT_AS (e.g., some macOS or BSD variants), the subprocess has **no memory limit**. A runaway prompt-to-code execution can exhaust host memory.

**Impact:** Medium. The CPU limit is still applied, and the timeout will eventually kill the process, but the intermediate memory exhaustion is not bounded.

**Recommended fix:**
- On platforms that reject RLIMIT_AS, use RLIMIT_FSIZE (file size) or RLIMIT_NPROC (process count) as a fallback.
- Log a warning if RLIMIT_AS fails so operators are aware.
- For production, use hardened containers (Cloud Run Jobs with gVisor) where memory limits are enforced by the runtime, not the process.

---

### Configuration: Model Gateway Credentials in Environment

**Files:** `src/agent_mesh/settings.py` (lines 67–75), `config/model_gateway.config.yaml` (lines 24–47)

**Issue:** The model gateway configuration references env vars for secrets:

```yaml
extra_headers:
  x-gateway-shared-secret: os.environ/MODEL_GATEWAY_SHARED_SECRET
```

And `settings.py` pulls secrets directly from `os.getenv()`:

```python
langfuse_secret_key: str = field(
    default_factory=lambda: os.getenv("LANGFUSE_SECRET_KEY", "")
)
```

This is correct for Cloud Run (where Secret Manager entries are injected as env vars), but it means secrets are in the process environment and potentially visible to child processes or in crash logs.

**Impact:** Low for the POC (expected for twelve-factor apps); remains a risk in production if crash dumps are not carefully guarded.

**Recommended fix:**
- Document that secrets must be injected by the runtime (Cloud Run `--set-secrets`), not hardcoded.
- Consider Secret Manager direct reads (avoiding env var intermediary) for highly sensitive values (e.g., master keys).
- Ensure crash-dump redaction and environment-sanitization in logs.

---

### Tool Gateway: No Input Validation or Output Sanitization

**Files:** `src/agent_mesh/tools/gateway.py`, `migrations/0001_init.sql` (tool_calls table)

**Issue:** The tool-call contract accepts arbitrary `parameters` (JSONB) and stores the result as-is:

```python
@dataclass
class ToolCall(BaseModel):
    tool_call_id: str
    task_id: str
    ...
    parameters: dict  # Arbitrary JSON, no validation
    result: dict | None = None  # Arbitrary JSON, no sanitization
```

A tool can return PII, secrets, or unescaped HTML. There is no schema validation, no PII scrubbing, no output escaping for display.

**Impact:** Medium. If tool results are displayed in the GUI or returned to users, unescaped content could cause injection attacks or leak sensitive data.

**Recommended fix:**
- Define JSON Schema for tool inputs and outputs (partial schema exists in `schemas/` but is not enforced at runtime).
- Validate inputs against schema before calling a tool.
- Scrub or redact PII in results before persisting or displaying.
- Escape output when rendering in the GUI.

---

## Performance & Scaling Concerns

### pgvector Indexes Not Created

**Files:** `migrations/0001_init.sql` (memory_chunks, retrieval_document_chunks, tool_evidence_chunks tables)

**Issue:** Embedding vectors are stored (768-dim) but no vector indexes are created. Retrieval queries will do full-table scans.

**Impact:** Low for the POC (small dataset); High for production (retrieval will be O(n)).

**Recommended fix:**
- Add `CREATE INDEX idx_memory_embedding ON memory_chunks USING ivfflat (embedding vector_cosine_ops)` after the schema is stable.
- Monitor retrieval latency as the embedding table grows.

---

### LangGraph Checkpointer Not Wired

**Files:** `src/agent_mesh/worker/orchestrator.py`, `src/agent_mesh/worker/runner.py`, `migrations/0002_self_improvement.sql`

**Issue:** The migration includes `langgraph_checkpoint` tables, but the orchestrator does not use them. State graphs are run in-memory.

**Impact:** Medium. Over-60-minute runs will not be checkpointed; if the worker crashes mid-graph, the entire run is lost.

**Recommended fix:**
- Wire the Postgres checkpointer in `LangGraphOrchestrator` (production hardening item §2).

---

## Test Coverage Gaps

### No End-to-End Integration Tests for Approval Workflow

**Files:** `tests/test_approval_gating.py`, `tests/smoke.py`

**Issue:** `test_approval_gating.py` tests the approval service in isolation, and `smoke.py` exercises the full loop. However, there is no test that:
- Verifies an unauthenticated POST to `/v1/approvals` is rejected.
- Tests replay of the same approval against two different tasks.
- Tests that editing a patch after approval invalidates the approval.

**Impact:** Medium. The unauthenticated approval endpoint gap (above) would have been caught by integration tests.

**Recommended fix:**
- Add test cases for `/v1/approvals` with and without signature.
- Add replay and mutation tests in the approval gate test suite.

---

### Limited Coverage of Tenant Isolation

**Files:** `tests/`

**Issue:** No test exercises a cross-tenant data leak (e.g., querying events for a task from another tenant).

**Impact:** Medium. The tenant isolation gap (above) would be caught by a simple audit test.

**Recommended fix:**
- Add a test that verifies `list_events()` only returns events for the requested tenant.

---

## Fragile Areas

### Self-Improvement Promotion Depends on External AI-BOM Generator

**Files:** `src/agent_mesh/services/self_improvement.py` (lines 143–175)

**Issue:** `promote_proposal()` accepts a `ai_bom_snapshot_id` but does not verify it exists or is current:

```python
def promote_proposal(
    ...
    ai_bom_snapshot_id: str | None = None,
) -> PromotionRecord:
    ...  # No validation that the snapshot exists or matches the promoted change
```

If the snapshot is stale or absent, the promotion record will link to nonexistent capability inventory.

**Impact:** Low for the POC (snapshot generation is future work); Medium for production (audit trail breaks).

**Recommended fix:**
- Require `ai_bom_snapshot_id` (not optional) and validate it before promotion.
- Generate the snapshot as part of promotion (production hardening item §15).

---

### Concurrent Approval Decisions

**Files:** `src/agent_mesh/services/approvals.py` (lines 63–81), `src/agent_mesh/services/task_service.py` (lines 63–90)

**Issue:** If two approval requests arrive concurrently for the same task, both transitions are applied:

```python
def record_decision(...):
    record = repo.get_approval(approval_record_id)
    updated = record.model_copy(update={"decision": decision.value, ...})
    return repo.upsert_approval(updated)
    
def submit_approval_decision(...):
    # Two concurrent APPROVED decisions both transition the task to APPROVED and re-dispatch
```

The in-memory repo uses a lock, so this is safe in the POC, but a distributed Postgres repo without explicit transaction serialization could record both decisions and transition the task twice.

**Impact:** Low for the POC; Medium for production (Postgres needs serializable isolation level or explicit locking).

**Recommended fix:**
- Document that `upsert_approval()` must be idempotent or use transaction serialization.
- Add a `decision_version` or timestamp to prevent replaying old decisions.

---

## Security: Slack Signature Verification Timestamp Tolerance

**Files:** `src/agent_mesh/api/slack_verify.py`, `src/agent_mesh/settings.py` (line 79)

**Issue:** The timestamp tolerance is 5 minutes by default (`slack_timestamp_tolerance_s = 60 * 5`), which is generous for replay protection.

**Impact:** Low. A Slack signature is still required, so an attacker must intercept a real Slack request and replay it within the window. Not a critical gap, but tighter tolerance (30–60 seconds) is standard.

**Recommended fix:**
- Reduce tolerance to 60 seconds for production.
- Document the value in the manifest as configurable per deployment.

---

## Deployment & Operational Gaps

### No Health Checks for Model Gateway Connectivity

**Files:** `src/agent_mesh/api/app.py` (lines 32–34), `src/agent_mesh/worker/model_gateway.py`

**Issue:** The `/healthz` endpoint returns `ok` without checking whether the model gateway is reachable.

**Impact:** Low for the POC; Medium for production. A worker may start and begin processing tasks before discovering the gateway is unreachable, wasting retries.

**Recommended fix:**
- Add a liveness check in `/healthz` that pings the model gateway or executes a lightweight model call.

---

### Deployment Scripts Assume Specific Secret Names

**Files:** `scripts/gcp_bootstrap.sh`, `scripts/gcp_deploy_core.sh`, `RUNBOOK.md` (lines 111–123)

**Issue:** The runbook hardcodes secret names (e.g., `SLACK_SIGNING_SECRET`, `ANTHROPIC_API_KEY`) without allowing per-deployment customization.

**Impact:** Low. Hardcoding is acceptable for the POC, but production deployments may need different naming schemes per client.

**Recommended fix:**
- Add a `secrets.manifest.yaml` that maps logical secret names to their GCP Secret Manager IDs, allowing override per deployment.

---

## Known Limitations (By Design)

The following are **intentional POC scope limitations** documented elsewhere:

| Limitation | Reference | Status |
|------------|-----------|--------|
| In-memory repository instead of Postgres | README.md lines 48–56, production caveat §2 | Expected POC limitation |
| No real LangGraph + Deep Agents orchestration | README.md table "Needs development", orchestrator.py stub | Expected POC limitation |
| No Pub/Sub wiring | settings.py line 35 (in-process dispatcher fallback) | Expected POC limitation |
| No real SaaS tool adapters | README.md table "Needs development" | Expected POC limitation |
| No Langfuse telemetry wiring | observability.py has seams, no callback backend | Expected POC limitation |
| No real evaluation harness | self_improvement.py §109–179, evaluate_proposal stub | Expected POC limitation |
| No AI-BOM snapshot generation on promotion | self_improvement.py line 162 comment, caveat §15 | Expected POC limitation |
| No runtime promotion wiring (hot reload) | self_improvement.py docstring, caveat §15 | Expected POC limitation |

---

## Summary: Risk Prioritization for Production Path

**Critical (must fix before any production use):**
1. **Approval endpoint authentication** — `/v1/approvals` accepts self-asserted `approver_id`; add signature verification (HMAC/JWT).
2. **Durable repository** — Switch from in-memory to Postgres-backed `RepositorySQL` for any long-running deployment.

**High (before client workloads):**
3. **Tenant isolation enforcement** — Add `tenant_id` parameter to read methods to prevent cross-tenant queries.
4. **Self-improvement loop promotion blocking** — Prevent promotion until AI-BOM snapshot is generated and wired.
5. **Real evaluation harness** — Production hardening item §9; required before self-improvement can auto-promote.

**Medium (before scaling or HA):**
6. Immutable approval ledger (caveat §4).
7. Egress controls (caveat §6).
8. Kill switches (caveat §10).
9. pgvector indexes for retrieval performance.
10. Input validation and output sanitization for tool calls.

**Low (operational hardening):**
11. Reduce Slack timestamp tolerance to 60 seconds.
12. Add model gateway health checks to `/healthz`.
13. Generalize secret naming in deployment scripts.

---

*Concerns audit: 2026-06-05*
