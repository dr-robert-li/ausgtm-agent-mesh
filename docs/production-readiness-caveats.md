# Production Readiness Caveats

This document records the hardening work that is **deliberately out of scope for the
POC** but **required before this reference architecture carries production or
client-critical workloads**. The POC optimizes for a lean, redeployable proof of
the agent-mesh pattern (5 users, ~USD $40–65/month infra, non-HA Cloud SQL,
relaxed model-inference residency). Promoting it to production changes the risk
posture and the items below become mandatory, not optional.

Treat this as a gate checklist: each item should have an owner, a target, and a
verification step before any production go-live.

## Model gateway separation (POC baseline to preserve)

The POC already separates the two model-gateway planes, and production MUST keep
them separate:

- **LiteLLM-compatible gateway** — model control plane: routing, cascades/fallbacks,
  budget enforcement, token/output limits, routing profiles, provider abstraction
  (Anthropic direct + Vertex AI).
- **Cloudflare AI Gateway** — model-traffic governance/observability plane:
  AI traffic logging, DLP, query blocking, guardrails, audit visibility,
  request/response metadata and payload logging controls, rate limiting/caching.
- The gateway routes all upstream model calls through Cloudflare AI Gateway; neither
  plane governs SaaS tool writes (that stays in the Tool Gateway approval ledger).
- Observability is Langfuse-centered (tracing, prompt/version management,
  datasets/evals, token/cost telemetry); LangSmith is an optional alternative only.

Production hardening should not collapse these responsibilities into one layer.

## 1. Secure container / sandbox prompt-to-code execution

- POC may run prompt-to-code in convenient sandboxes; production MUST execute all
  generated code in isolated, least-privilege containers (gVisor/Kata or
  equivalent, or hardened Cloud Run Jobs) with:
  - no host filesystem or host network access,
  - scoped, short-lived service accounts,
  - CPU/memory/time quotas and hard timeouts,
  - read-only base images and ephemeral, isolated work directories,
  - explicit network egress allowlists (default-deny).
- No generated patch, file overwrite, SaaS mutation, repo commit, or external send
  is applied without an approval gate recorded in the approval ledger.

## 2. Durable orchestration

- POC uses Pub/Sub or Cloud Tasks dispatch with durable task records.
- Production should introduce **Temporal (or equivalent durable workflow engine)**
  for >60-minute mesh runs, retries, compensation, and resumability. The Task
  contract is already kept Temporal-ready; production wires it in without changing
  Slack/MCP/tool-gateway contracts.

## 3. Tenant isolation

- POC relies on tenant/client partitioning columns in shared tables.
- Production should strengthen isolation: row-level security and/or schema- or
  database-per-tenant, per-tenant encryption keys, per-tenant service accounts and
  secrets, and per-tenant budget/rate ceilings. Validate that no query path can
  cross tenant boundaries.

## 4. Immutable approval ledger

- POC stores approvals in `approval_records`.
- Production requires an **append-only, tamper-evident** approval ledger:
  hash-chained or WORM-backed records, no in-place updates/deletes, signed
  decisions, and independent verification of the chain. Approval payload hashes
  must be reproducible for audit.

## 5. Externalized 12+ month audit retention / log export

- POC retains traces, AI-BOM snapshots, approvals, and tool-call logs for 12
  months in-platform.
- Production should **export audit streams to immutable external storage** (e.g.
  object storage with retention lock / object hold), independent of Cloudflare and
  Langfuse storage limits, with documented export cadence, integrity checks, and
  restore tests. Avoid silent log-drop when Cloudflare log storage is exhausted.

## 6. Egress controls

- POC permits broad outbound model/SaaS traffic for convenience.
- Production needs **default-deny egress** with explicit allowlists per service and
  per sandbox, DNS/proxy egress filtering, and monitoring/alerting on unexpected
  destinations. Model egress remains pinned through Cloudflare AI Gateway.

## 7. Short-lived / scoped credentials and rotation

- POC may use long-lived secrets in Secret Manager.
- Production requires **short-lived, narrowly-scoped credentials** (Workload
  Identity Federation, OAuth token exchange, per-tool minimal scopes), automated
  rotation, and rotation runbooks. Agents never receive raw credentials; the Tool
  Gateway resolves them at execution time and they expire quickly.

## 8. CI/CD, signed images, SBOM, dependency scanning

- Production requires a hardened delivery pipeline:
  - reproducible builds with **signed container images** (e.g. cosign) and
    deploy-time signature verification / admission control,
  - **SBOM** generation per image and per release,
  - **dependency and container vulnerability scanning** with policy gates,
  - infrastructure-as-code review, least-privilege deploy identities, and
    promotion gates between environments.

## 9. Automated evals / regression testing

- POC validates via manual E2E and failure tests.
- Production needs **automated agent evals and regression suites**: golden-path and
  adversarial prompt tests, tool-call contract tests, guardrail/DLP regression
  checks, budget/fallback behavior tests, and run-on-merge gating with tracked
  quality/cost baselines.

## 10. Kill switches and incident response

- Production requires **fast kill switches**: per-tenant and global pause of mesh
  execution, model traffic, and tool writes; a documented incident-response
  runbook with severities, on-call ownership, comms templates, and a post-incident
  review process. Kill switches must be testable and independent of the normal
  deploy path.

## 11. Memory / vector retrieval governance

- POC uses `memory_chunks` and `evidence_chunks` in Cloud SQL + pgvector.
- Production needs retrieval governance: access controls and tenant scoping on all
  retrieval, provenance/freshness enforcement, evidence-pointer auditing,
  poisoning/PII safeguards on ingestion, and a migration path to a dedicated vector
  store (AlloyDB, Vertex Vector Search, or equivalent) if volume/latency demands it.

## 12. Data retention / deletion policy

- Production requires an explicit **data retention and deletion policy**: defined
  retention per data class, right-to-erasure / deletion workflows, deletion
  propagation across memory, evidence, traces, logs, and backups, and verification
  that deletions are honored within SLA.

## 13. Multi-region / HA decision if workload becomes critical

- POC runs non-HA, single-zone Cloud SQL in `australia-southeast1` and accepts the
  database SPOF.
- If the workload becomes critical, make an explicit **HA / multi-region decision**:
  Cloud SQL HA (regional), read replicas, backup/restore RTO/RPO targets, and
  documented failover procedures. Revisit data-residency commitments at the same
  time.

## 14. Operational SLOs and monitoring

- Production requires defined **SLOs/SLIs** (task success rate, latency, approval
  turnaround, budget-halt correctness, gateway availability) with dashboards,
  alerting, error budgets, and on-call coverage. Langfuse/OpenTelemetry telemetry
  feeds these; alerting thresholds and escalation paths must be configured.

## 15. Self-improvement loop hardening (Option C)

The self-improvement loop ([self-improvement-loop.md](./self-improvement-loop.md))
is implemented (v1.0, Option C) and **intentionally inert** — proposals never mutate
the running system. Already real: a held-out evaluation harness (`services/eval_harness.py`:
Langfuse `run_experiment` + aggregate/item no-regression gate) replacing the boolean
stub, a GEPA-style offline proposer, and CycloneDX ML-BOM generation on promotion
(`services/ai_bom.py`). Before it carries weight in production:

- The **evaluation harness** needs production depth — broader versioned eval sets,
  regression suites, and red-team checks — beyond the held-out frozen-context snapshots
  proven creds-free today.
- **Promotion → runtime** must be wired through versioned config with a controlled
  reload/rollout, never a hot in-place rewrite of live prompts/tools/routes. The loop
  records a versioned `PromotionRecord` (and ML-BOM) but, by Option-C design, does not
  apply it to the running system — production needs the controlled-rollout wiring.
- The **reflection/governance proposer** is offline and inert by design; wiring it to
  emit proposals from live run telemetry via the `reflect_on_task` seam (rather than
  mined durable traces) is future work.
- Retain the **hard boundary**: no runtime autonomous self-modification of active
  instructions; high/critical proposals always require human approval.

## Governance Alignment Crosswalk

The production hardening items above are not just engineering tasks — each one
maps to a governance theme in the
[`org-ai-maturity-assessment`](https://github.com/dr-robert-li/org-ai-maturity-assessment/tree/main)
framework, which draws on NIST AI RMF 1.0, ISO/IEC 42001:2023, the EU AI Act,
OWASP Top 10 for LLM Applications, MITRE ATLAS, OAIC Australian Privacy
Principles, APRA CPS 230/234, and related standards.

This crosswalk is **implementation-facing**: it aligns each caveat to framework
*themes* and agent/technical security standards rather than asserting specific
control IDs or maturity-tier numbers. Use it to connect production go-live gating
to the assessment's intake, risk-register, and operational-governance workflows.

| Production hardening caveat | Aligns to governance framework themes / standards |
| :--- | :--- |
| Secure prompt-to-code sandboxing (§1) | Agent & technical security standards, OWASP LLM controls, tool/code execution governance |
| Durable orchestration and resumability (§2) | Operational resilience, auditability, incident recovery |
| Tenant isolation (§3) | Data governance, access control, privacy/tenancy controls |
| Immutable approval ledger (§4) | Human accountability, approval evidence, ADM/decision logs |
| Externalized audit retention (§5) | Audit trails, AI-BOM evidence, board/management review readiness |
| Egress controls (§6) | Data-leakage prevention, SaaS/tool boundary control |
| Scoped / rotating credentials (§7) | Identity and access management, credential governance |
| CI/CD, signed images, SBOM, dependency scanning (§8) | Technical security standards and supply-chain assurance |
| Automated evals / regression testing (§9) | Evaluation templates, red-team scope, model/system card evidence |
| Kill switches and incident response (§10) | Operational risk, pilot stop criteria, incident controls |
| Memory / vector retrieval governance (§11) | Evidence management, provenance, retention/deletion policy |
| Data retention / deletion policy (§12) | Privacy, records management, audit retention |
| Multi-region / HA decision (§13) | Reliability and business continuity proportional to criticality |
| Operational SLOs and monitoring (§14) | Success-metrics dashboard and operational monitoring |
| Self-improvement loop hardening (§15) | Change governance, human-in-the-loop approval, versioning/rollback, evaluation evidence, AI-BOM currency |

Mappings are indicative alignment to framework themes; consult the
[`org-ai-maturity-assessment`](https://github.com/dr-robert-li/org-ai-maturity-assessment/tree/main)
repository for the authoritative control catalogue, maturity tiers, and SEV
scoring before treating any item as a satisfied control.

---

**Summary:** The POC proves the pattern. Production go-live is contingent on the
items above being owned, implemented, and verified. None of these change the
reusable platform boundary or the Slack/MCP/Tool-Gateway contracts; they harden
the execution, governance, identity, delivery, and operational planes around it.
