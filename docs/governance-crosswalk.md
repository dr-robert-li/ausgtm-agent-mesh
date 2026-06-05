# Governance Alignment Crosswalk

This document maps the agent mesh's governance surfaces to recognized AI-governance
themes and to the directive's required MVP governance coverage. It aligns with the
reference frameworks
[`agentic-mesh-reference-arch`](https://github.com/dr-robert-li/agentic-mesh-reference-arch)
and
[`org-ai-maturity-assessment`](https://github.com/dr-robert-li/org-ai-maturity-assessment/tree/main),
which draw on NIST AI RMF 1.0, ISO/IEC 42001:2023, the EU AI Act, OWASP Top 10 for
LLM Applications, MITRE ATLAS, OAIC Australian Privacy Principles, and APRA CPS
230/234.

The crosswalk is **implementation-facing**: it aligns the mesh's surfaces to
framework *themes* rather than asserting specific control IDs or maturity tiers.
Where the linked repositories are not accessible, this crosswalk does not block;
it remains a best-effort alignment to widely published framework themes.

## 1. Required MVP governance coverage

The directive requires the MVP to cover these governance surfaces. Each row names
where the surface lives in this repo and its current status.

| Governance surface | Where it lives in this repo | Status |
| :--- | :--- | :--- |
| Evidence registry | `evidence_chunks` (migrations `0001_init.sql`); evidence pointers attached to outputs/approvals; `EvidenceChunk` contract | Scaffolded |
| AI-BOM | `ai_bom_snapshots` schema; `AIBomSnapshot` contract; admin console `aibom` section; promotion `ai_bom_snapshot_id` link | Scaffolded (generator is future work) |
| Approvals (HITL) | `approval_records`; approval gating with payload-hash binding (`services/approvals.py`); LangGraph interrupt model; admin `approvals` section | Scaffolded & tested |
| Risk classification | `ProposalRiskLevel` + `classify_risk(...)` (sensitive types floored to `high`); write-class tool categories require approval | Scaffolded & tested |
| Human oversight | Slack/MCP approval delivery; shared approval ledger; high/critical never auto-promote | Scaffolded & tested |
| Evals | `evaluate_proposal(...)` seam; Langfuse datasets/evals; real harness is future work | Scaffolded (stub) |
| Auditability | 12-month retention profile; Langfuse traces; durable task/tool/approval/promotion records | Scaffolded |
| Data governance | Tenant/client partitioning on memory/evidence; durable stores in `australia-southeast1`; credentials via Secret Manager / Tool Gateway | Scaffolded |
| Operational monitoring | Langfuse/OpenTelemetry telemetry; admin `observability` section; SLOs are production hardening | Scaffolded (SLOs future) |
| Model & tool registry | Tool-pack manifest + loader; `DEFAULT_PROFILE` model routes; admin `toolpacks`/`mcp`/`budget` sections | Scaffolded & tested |
| Change management | Self-improvement Option C: proposal → eval → approval → versioned promotion → rollback; AI-BOM update | Scaffolded & tested |

## 2. Themes crosswalk

| Mesh surface | Aligns to governance framework themes / standards |
| :--- | :--- |
| Bounded Deep Agents roster (no uncontrolled spawning) | Agent security standards, scope/authority control, MITRE ATLAS agent-abuse mitigations |
| Model gateway separation (LiteLLM control plane / Cloudflare governance plane) | Model-traffic governance, DLP, data-leakage prevention, provider abstraction |
| Tool Gateway write-approval gates | Human accountability, ADM/decision logs, change governance |
| Approval ledger + payload-hash binding | Approval evidence, tamper-evidence intent, auditability |
| AI-BOM snapshots | Model/system card evidence, capability inventory, supply-chain assurance |
| Langfuse observability (traces, prompts, evals, cost) | Operational monitoring, evaluation evidence, success-metrics dashboard |
| Self-improvement Option C | Change governance, HITL approval, versioning/rollback, evaluation evidence |
| Tenant partitioning + AU data residency | Data governance, privacy/tenancy controls, OAIC APPs |
| 12-month retention | Audit trails, records management, board/management review readiness |

## 3. Relationship to production hardening

Each MVP surface above has a corresponding production hardening item in
[production-readiness-caveats.md](./production-readiness-caveats.md), which contains
a per-caveat governance alignment crosswalk. The MVP proves the *shape* of each
governance surface; production go-live requires the hardened version (immutable
ledger, real eval harness, externalized audit export, kill switches, scoped
credentials, automated AI-BOM generation, runtime promotion wiring).

Consult the
[`org-ai-maturity-assessment`](https://github.com/dr-robert-li/org-ai-maturity-assessment/tree/main)
repository for the authoritative control catalogue, maturity tiers, and scoring
before treating any item here as a satisfied control.
