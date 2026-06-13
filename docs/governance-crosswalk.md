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

Status reflects the v1.0 (real implementation, phases 1–7) and v1.1 (local/offline,
phases 8–11) milestones — both complete and locally validated. "Implemented & tested"
means real code exercised by `make test`; remaining production hardening is in
[production-readiness-caveats.md](./production-readiness-caveats.md).

| Governance surface | Where it lives in this repo | Status |
| :--- | :--- | :--- |
| Evidence registry | `evidence_chunks` (migrations `0001_init.sql`); evidence pointers attached to outputs/approvals; `EvidenceChunk` contract | Implemented (vector retrieval at scale is hardening) |
| AI-BOM | `ai_bom_snapshots` schema; `AIBomSnapshot` contract; CycloneDX ML-BOM generator (`services/ai_bom.py`) emitted on promotion; admin `aibom` section; promotion `ai_bom_snapshot_id` link | Implemented & tested |
| Approvals (HITL) | `approval_records`; authenticated/replay-proof approval gate with payload-hash binding (`services/approvals.py`); LangGraph interrupt model; admin `approvals` section | Implemented & tested |
| Risk classification | `ProposalRiskLevel` + `classify_risk(...)` (sensitive types floored to `high`); write-class tool categories require approval | Implemented & tested |
| Human oversight | Slack/MCP approval delivery; shared approval ledger; high/critical never auto-promote | Implemented & tested |
| Evals | Real held-out evaluation harness (`services/eval_harness.py`: Langfuse `run_experiment` + aggregate/item no-regression gate); GEPA-style offline proposer; `evaluate_proposal(...)` seam | Implemented & tested (broader eval sets / red-team are hardening) |
| Auditability | 12-month retention profile; Langfuse traces; durable task/tool/approval/promotion records | Implemented (externalized/immutable audit export is hardening) |
| Data governance | Tenant/client partitioning on memory/evidence; durable stores in `australia-southeast1`; credentials via Secret Manager / Tool Gateway | Implemented (data-deletion policy is hardening) |
| Operational monitoring | Langfuse/OpenTelemetry telemetry; admin `observability` section; SLOs are production hardening | Implemented (SLOs future) |
| Model & tool registry | Tool-pack manifest + loader; direct adapters + Composio/Nango aggregators; model-route profiles (cloud + local vLLM/Ollama); admin `toolpacks`/`mcp`/`budget` sections | Implemented & tested |
| Change management | Self-improvement Option C: real held-out eval → inert proposal → human approval → versioned non-hot promotion → rollback; CycloneDX ML-BOM on promotion | Implemented & tested |

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
a per-caveat governance alignment crosswalk. The MVP implements each governance
surface and validates it locally; production go-live still requires the hardened
version (immutable/externalized audit ledger, broader eval sets + red-team coverage,
kill switches, short-lived/scoped credentials, runtime promotion wiring beyond the
inert Option-C record, Cloud SQL HA). The held-out eval harness and CycloneDX
AI-BOM-on-promotion generator are implemented (v1.0); what remains is their
production-grade depth and runtime wiring.

Consult the
[`org-ai-maturity-assessment`](https://github.com/dr-robert-li/org-ai-maturity-assessment/tree/main)
repository for the authoritative control catalogue, maturity tiers, and scoring
before treating any item here as a satisfied control.
