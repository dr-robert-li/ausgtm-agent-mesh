# Architectural Design Pattern: Reusable Autonomous Agent Mesh POC via LangChain + LangGraph + Deep Agents + Langfuse on GCP

> `/goal` Complete the LangChain/LangGraph/Deep Agents/Langfuse reusable platform locally, with validated end-to-end testing for all functions, ready for GCP deployment and tool-pack configuration.

## 1. Executive Summary & Intent
- **Context:** Define a reusable, governed autonomous agent mesh pattern for small consultancies or client delivery teams. The concrete SaaS resources and tool adapters may vary by deployment, but the core agent fleet architecture, ingress model, task contract, execution plane, memory layer, approval model, and observability approach remain stable. The mesh is portable in principle across AWS/GCP/Azure; the first MVP/POC targets GCP in Sydney (`australia-southeast1`).
- **Solution Intent:** Use **LangChain** as the reusable tool/model abstraction, **LangGraph** as the durable orchestration layer (state graphs, checkpoints, human-in-the-loop pause/resume), **Deep Agents** as the bounded, supervisor-orchestrated subagent harness, and **Langfuse** as the open-source/self-hostable observability plane (tracing, prompt/version management, datasets/evals, token/cost telemetry, audit dashboards). Cloud Run services provide Slack/MCP/API ingress, Cloud Run Jobs or Worker Pools provide the long-running execution plane, Cloud SQL for PostgreSQL with `pgvector` is the durable memory and audit store, a LiteLLM-compatible gateway provides model routing/budgets/cascades/provider abstraction (Anthropic direct + Vertex AI), and Cloudflare AI Gateway provides model-traffic governance (integration-ready). SaaS integrations are packaged as replaceable client-specific tool packs behind a consistent Tool Gateway contract.

> **Default required stack (non-negotiable for this variant).**
> - **LangChain** — REQUIRED core application/tool/model abstraction.
> - **LangGraph** — REQUIRED durable orchestration: state graphs, checkpoints, and interrupt-based human-in-the-loop pause/resume for runs that may exceed 60 minutes.
> - **Deep Agents** — REQUIRED subagent harness. Subagents are a **supervisor-orchestrated, configured, bounded, observable team** (planner, researcher/tool-router, code-writer, reviewer), **not** an uncontrolled self-spawning swarm.
> - **Langfuse** — REQUIRED observability. Open-source and self-hostable; provides tracing, prompt/version management, datasets/evals, token/cost telemetry, and audit dashboards. Integrates with LangChain, OpenTelemetry, the OpenAI SDK, and LiteLLM.
> - **LangSmith** — NOT required. Optional alternative only; never a dependency.
> - **Model gateway** — LiteLLM-compatible: routing, budgets, cascades/fallbacks, provider abstraction, with Anthropic-direct and Vertex AI paths.
> - **Cloudflare AI Gateway** — integration-ready model-traffic governance. Observability *consumes* gateway decisions; it does not replace policy.

> **Implementation status (POC scaffold).** This document is the normative
> design pattern. A runnable Python-first scaffold of it lives in `src/agent_mesh/`
> and is exercised by `make test` / `make smoke` with no cloud dependencies — see
> [README.md](./README.md) for clone-and-run readiness and the scaffolded-vs-needs-development
> matrix, [docs/ecosystem-decision.md](./docs/ecosystem-decision.md) for the
> LangChain/LangGraph/Deep Agents/Langfuse and Python-first/TS-at-edge rationale,
> [RUNBOOK.md](./RUNBOOK.md) for local smoke checks and deployment,
> [docs/self-improvement-loop.md](./docs/self-improvement-loop.md) for the
> approval-gated self-improvement design (Option C) and its LangGraph/Deep Agents
> mapping, [docs/governance-crosswalk.md](./docs/governance-crosswalk.md) for the
> governance alignment crosswalk, and
> [docs/production-readiness-caveats.md](./docs/production-readiness-caveats.md)
> for the hardening required before production. The POC is **not production-ready**;
> it is ready for MVP/POC deployment configuration after local validation, and
> performs **no runtime autonomous self-modification of active instructions,
> permissions, or routing**.

## 2. Refined Engineering Requirements
- **Functional Requirements:**
  - Provide a redeployable reference architecture where the agent fleet, task lifecycle, memory layer, approval workflow, and telemetry model are reusable across clients and, in principle, across AWS/GCP/Azure.
  - Treat SaaS resources as replaceable tool packs, not core architecture dependencies.
  - Provide user ingress through a Slack App (with human-in-the-loop approvals) and through MCP entrypoints. Claude Desktop and Claude Code are first-class MCP clients; Codex, OpenCode, and Pi connect later via the same MCP/tool boundary.
  - Route Slack, MCP, and internal calls through a common API and Task contract so the orchestrator remains the source of truth.
  - Support over-60-minute mesh runs through durable LangGraph checkpoints on durable worker/job execution rather than request-bound Cloud Run service execution.
  - Use **LangGraph** state-graph orchestration with a **Deep Agents** supervisor and a bounded subagent roster for dynamic coordination and self-correction. No uncontrolled self-spawning.
  - Provide prompt-to-code execution where agents can create artifacts and proposed patches.
  - Execute generated code only in isolated Docker or Cloud Run Job sandboxes, never directly on the host.
  - Require requester approval before write actions, including creates, updates, deletes, sends, publishes, invoices, payments, commits, or production mutations. Implement the approval gate as a LangGraph interrupt that pauses the graph and resumes from the checkpoint on decision.
  - Deliver high-risk approval prompts to the respective requester through Slack or MCP, with a shared approval ledger.
  - Store AI-BOM snapshots covering agents, prompts, tools, skills, model routes, versions, and approved capabilities.
  - Provide token, cost, latency, task, tool-call, and approval telemetry, centered on Langfuse.
  - Use mixed model cascades across Vertex AI (Gemini, Claude-on-Vertex) and Anthropic-direct through the LiteLLM-compatible gateway.
  - Route model traffic through the model gateway and (integration-ready) Cloudflare AI Gateway for visibility, audit logs, DLP/query blocking, guardrails, and request metadata.
  - Provide a self-improvement loop (Option C): proposal → evaluation → human-in-the-loop approval → versioned promotion → AI-BOM update, with rollback and **no silent mutation of active instructions, permissions, or routing**.
  - Provide both a GUI admin/operator console and CLI/code administration.
  - Support repeatable deployment through environment-specific configuration, infrastructure-as-code, schema migrations, and per-client tool manifests.
  - Provide reusable `gcloud` scripts, Cloudflare `wrangler` scripts, deployment manifests, tool-pack manifests, and a repeatable deployment runbook.
  - Ensure deployment scripts are idempotent and can safely target either a new recommended deployment environment or an existing GCP project / Cloudflare AI Gateway.

- **Non-Functional Requirements:**
  - **Scale:** Initial POC target is 5 users.
  - **Region:** Durable data stores must run in Sydney, `australia-southeast1`.
  - **Data Residency:** Prompt/model processing may leave Australia for the POC; durable stores remain in Australia.
  - **Execution Duration:** Long mesh runs may exceed 60 minutes and must retain state through LangGraph checkpoints, jobs, worker queues, and durable task records.
  - **Budget:** Enforce a user-configurable model budget starting at USD $50/month.
  - **Infrastructure Cost Posture:** Target lean non-critical POC infrastructure, estimated around USD $40-$65/month under light usage assumptions, excluding model tokens, SaaS subscriptions, and GST.
  - **Availability:** Cloud SQL high availability is not required for the POC because this is not a critical workload.
  - **Retention:** Retain traces, AI-BOM snapshots, approval records, tool-call logs, and task audit records for 12 months.
  - **Governance Scope:** A bespoke tool-egress policy/classification gateway is out of scope for this POC. Cloudflare AI Gateway DLP/query blocking and guardrails are in scope for model traffic.
  - **Redeployability:** The pattern must separate reusable platform components from client-specific adapters, credentials, SaaS schemas, and approval policies.
  - **Idempotent Deployment:** Scripts must detect existing GCP projects, APIs, service accounts, Cloud SQL instances, Artifact Registry repositories, Pub/Sub topics, Cloud Run services/jobs, and Cloudflare AI Gateway configuration inputs before attempting creation.

## 3. Target Cloud Architecture
- **Generative AI Layer (default required stack):**
  - **Agent framework:** LangChain (tool/model abstraction) + LangGraph (durable state graph, checkpoints, HITL interrupts) + Deep Agents (bounded supervisor-orchestrated subagent roster: planner, researcher/tool-router, code-writer, reviewer). The roster is declared, bounded, and observable; there is no uncontrolled self-spawning.
  - **Observability:** Langfuse is the required, open-source/self-hostable observability plane. Spans, prompts, datasets/evals, and token/cost telemetry flow into Langfuse via the LangChain callback handler and/or OpenTelemetry. LangSmith is an optional alternative only, never required.
  - **Model Gateway Separation of Responsibilities (explicit for the POC):**
    - **LiteLLM-compatible gateway owns the model control plane:** model routing, model cascades/fallbacks, per-user and per-task budget enforcement, token/max-output limits, model policy and routing profiles (`MODEL_ROUTE_PROFILE`), cost attribution, and provider abstraction (Anthropic-direct and Vertex AI). The gateway presents Cloudflare AI Gateway as its upstream rather than calling model providers directly.
    - **Cloudflare AI Gateway owns model-traffic governance and observability of model traffic:** AI/model traffic logging, DLP matching, query blocking, prompt/response guardrails, audit visibility, request/response metadata and payload logging controls, and rate limiting/caching where applicable. It is integration-ready in this POC.
    - **Flow:** LangChain/LangGraph/Deep Agents → LiteLLM-compatible gateway (routing/budgets/cascades) → Cloudflare AI Gateway (logging/DLP/blocking/guardrails) → upstream model providers (Anthropic direct, Vertex AI).
    - The gateway MUST route all upstream model calls through Cloudflare AI Gateway when enabled; agents and workers never call providers directly.
    - Neither gateway governs SaaS tool writes; tool-write governance stays in the Tool Gateway approval ledger.
  - Use task-tier routing:
    - Low-complexity routing to cheaper Gemini or compact models (Vertex AI).
    - Medium-complexity routing to Gemini Flash/Pro or Claude Sonnet-class models.
    - High-complexity reasoning and prompt-to-code review routed to Claude (Anthropic direct) or higher-capability Gemini models where justified.
  - Enforce per-user and per-task model budgets, max token limits, fallback rules, and cost attribution in the model gateway.
  - Send token/cost metadata to the gateway logs, Cloudflare AI Gateway, and Langfuse via OpenTelemetry-compatible spans.
  - Attach shared request metadata to model calls: `tenant_id`, `client_slug`, `task_id`, `session_id`, `requester_id`, `entrypoint`, `agent_role`, `model_route_profile`, `approval_state`.

- **Compute & Integration Layer:**
  - Use Cloud Run services in `australia-southeast1` for: Slack Events API ingress, MCP HTTP ingress, internal API / Task contract endpoint, approval callback handling, and the GUI admin/operator console.
  - Use Cloud Run Jobs or Cloud Run Worker Pools for: long-running LangGraph + Deep Agents mesh executions, prompt-to-code sandbox runs, retryable background work, and artifact/proposed-patch preparation.
  - Use Pub/Sub or Cloud Tasks for dispatch between ingress services and execution workers.
  - LangGraph owns durability: long runs checkpoint state (Postgres checkpointer in prod) and resume from the checkpoint when a decision is dispatched back. Keep the Task contract Temporal-ready so Temporal can be introduced later without changing Slack, MCP, or tool-gateway contracts.
  - Package deployment as a reusable stack with parameterized environment values: `PROJECT_ID`, `REGION`, `TENANT_ID`, `CLIENT_SLUG`, `SLACK_APP_CONFIG`, `MCP_SERVER_BASE_URL`, `MODEL_ROUTE_PROFILE`, `MODEL_GATEWAY_BASE_URL`, `MODEL_PROVIDER_MODE`, `TOOL_PACK_MANIFEST`, `APPROVAL_POLICY_PROFILE`, `RETENTION_PROFILE`, `LANGFUSE_HOST`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_AI_GATEWAY_ID`, `CLOUDFLARE_ZERO_TRUST_DLP_PROFILE`, `WRANGLER_ENV`, `CREATE_PROJECT`, `BILLING_ACCOUNT_ID`, `REUSE_EXISTING_CLOUDFLARE_GATEWAY`.

- **Ingress & MCP Clients:**
  - Slack App ingress with fast acknowledgement, async dispatch, and HITL approvals.
  - MCP ingress with shared requester identity and Task creation. Claude Desktop and Claude Code are first-class MCP clients now; Codex, OpenCode, and Pi connect later via the same MCP/tool boundary.
  - All ingress normalizes into one shared requester identity, task record, approval ledger, and audit envelope.

- **Cloudflare AI Gateway Layer:**
  - Cloudflare AI Gateway is the model-traffic governance/observability plane (logging, DLP, query blocking, guardrails, audit visibility, metadata/payload logging controls, rate limiting/caching); the LiteLLM-compatible gateway remains the model control plane. The two are deliberately separated.
  - Use Cloudflare AI Gateway between the model gateway and upstream model providers; manage the worker/wrapper and bindings with `wrangler`.
  - Prefer a new dedicated AI Gateway per client/environment, but support reusing an existing one via `CLOUDFLARE_AI_GATEWAY_ID`.
  - Export or inspect AI Gateway logs for audit review; keep configuration deployment-specific but represented in the reusable deployment manifest.
  - Do not use Cloudflare AI Gateway as a replacement for tool-write approval gates; it governs model traffic, not SaaS mutations.

- **Reusable Platform Boundary:**
  - Keep stable across deployments: Slack/MCP/API ingress pattern; canonical Task contract and lifecycle; LangGraph + Deep Agents agent fleet roles and orchestration loop; Cloud Run Jobs or Worker Pools execution pattern; Cloud SQL schema families for tasks, sessions, memory, evidence, approvals, AI-BOM, budgets, and tool calls; LiteLLM-compatible model control-plane contract; Cloudflare AI Gateway model-traffic governance contract; Langfuse/OpenTelemetry trace schema; approval ledger and write-action gating contract.
  - Keep deployment-specific: SaaS tools and credentials; HubSpot pipelines/properties; Google Workspace folders, shared drives, and scopes; Xero tenants/accounts; Clockify workspace/project IDs; Webflow site IDs; Cal.com event types; Beehiiv publication IDs; Bitscale workspace/API details; client-specific prompts, routines, approval rules, and budget limits.

- **Data & Vector Store:**
  - Use Cloud SQL for PostgreSQL in `australia-southeast1`, non-HA, with automated backups. Enable `pgvector` for lightweight vector retrieval.
  - Use separate logical tables/collections for: `tasks`, `sessions`, `memory_chunks`, `evidence_chunks`, `tool_calls`, `approval_records`, `ai_bom_snapshots`, `budget_ledger`, and `gateway_events`. Keep evidence chunks separate from session summaries and task metadata. Also persist LangGraph checkpoints and self-improvement proposals/evaluations/promotions.

- **Tool Pack Contract:**
  - Each client deployment supplies a tool pack manifest that declares: tool name and semantic description; tool category (read, write, external_send, financial, publishing, code, or admin); integration style (`direct_api`, `mcp_server`, `aggregate_mcp`, or `nango_aggregator`); required OAuth scopes or API credentials; approval requirement; input/output JSON schema; freshness expectations; rate-limit assumptions; SaaS resource identifiers; owner and support contact.
  - Reference toolpacks (extensible): Xero, HubSpot, Webflow, Bitscale, Cal.com, Clockify, Beehiiv, and Google Workspace (Gmail/Calendar/Drive/Sheets/Docs/Presentations).
  - The reusable platform loads tool manifests into the AI-BOM snapshot and exposes only approved tools to the agents. Agents never receive raw credentials; the Tool Gateway resolves credentials at execution time.

- **Memory / Context Layer:**
  - Implement the context layer on Cloud SQL PostgreSQL plus `pgvector` for the POC. Distinguish: retrieval/evidence chunks, session summaries, task metadata, reusable long-term memory, Deep Agents working context, and Langfuse trace links.
  - Use `memory_chunks` for summarized agent memory, reusable routines, task learnings, and user/project context; `evidence_chunks` for retrieval documents, tool evidence, source excerpts, and embeddings.
  - Attach evidence pointers to task outputs, proposed patches, and write-action approval requests. Keep the knowledge layer as a cache/index/evidence pointer system, not a system of record. Tenant/client partition all memory and evidence tables.

- **Prompt-to-Code Layer:**
  - Use Deep Agents code-writer and (sandboxed) code-executor roles. Generated code can create artifacts, diagnostics, scripts, and proposed patches.
  - Execute code in short-lived Docker or Cloud Run Job sandboxes with least-privilege service accounts. Return stdout, stderr, exit code, artifact paths, and patch diffs to the agent loop for self-correction.
  - Require approval before any generated patch, SaaS mutation, repository commit, file overwrite, external send, or production-impacting write is applied. Persist results in `tool_calls`, `evidence_chunks`, and task audit logs.

## 4. Risks, Limitations & Mitigation Strategies
- **Risk:** Hardcoded SaaS identifiers make the architecture brittle and non-redeployable. *Mitigation:* per-client tool pack manifests, environment variables, Secret Manager entries, and migrations instead of hardcoded IDs.
- **Risk:** Deployment scripts can overwrite existing client environments. *Mitigation:* idempotent-by-default scripts, explicit env vars for destructive/project-creation actions, resource detection before creation, support for reusing existing GCP projects and Cloudflare AI Gateways.
- **Risk:** Deep Agents subagents could degenerate into an uncontrolled self-spawning swarm. *Mitigation:* a declared, bounded, supervisor-orchestrated roster (planner, researcher/tool-router, code-writer, reviewer); no dynamic uncontrolled spawning; full observability via Langfuse spans.
- **Risk:** Client-specific prompts, routines, and tools can drift from the reusable architecture. *Mitigation:* version all prompts, routines, tool manifests, and model route profiles; include them in AI-BOM snapshots and release manifests; manage prompt versions in Langfuse.
- **Risk:** Cloud Run services are not suitable as the sole runtime for over-60-minute mesh tasks. *Mitigation:* Cloud Run Jobs or Worker Pools with LangGraph checkpoints and task state persisted in Cloud SQL; dispatch via Pub/Sub or Cloud Tasks.
- **Risk:** Model processing may leave Australia. *Mitigation:* keep durable stores in Sydney; document relaxed model inference residency for the POC.
- **Risk:** Cloud SQL without HA is a DB availability SPOF. *Mitigation:* accept for the non-critical POC, enable backups, define HA upgrade as production hardening.
- **Risk:** `pgvector` may not meet high-scale vector search needs. *Mitigation:* separate `memory_chunks`/`evidence_chunks` now; allow future migration to AlloyDB or Vertex Vector Search.
- **Risk:** Generated code can be unsafe with broad host/network access. *Mitigation:* never local host execution in production-like paths; Docker/Cloud Run Job sandboxes with scoped service accounts, timeouts, isolated work dirs, and approval before writes.
- **Risk:** Observability does not equal enforcement. *Mitigation:* Cloudflare AI Gateway for model-traffic DLP/query blocking and guardrails; SaaS/tool-write governance limited to audit, AI-BOM, budget tracking, and approval gates for writes.
- **Risk:** Self-improvement could silently mutate live behavior. *Mitigation:* Option C only — proposals are inert until evaluated, human-approved, and version-promoted; no runtime mutation of active instructions, permissions, or routing; full rollback and AI-BOM update.
- **Risk:** Cloudflare AI Gateway governs model traffic but not SaaS tool execution. *Mitigation:* keep approval gates on all write actions in the Tool Gateway; store decisions in the shared ledger.
- **Risk:** Model cascades can hide provider failures or cost spikes. *Mitigation:* explicit route tiers, token caps, fallback ordering, per-user budgets, budget-threshold alerting.
- **Risk:** Slack and MCP identity contexts can diverge. *Mitigation:* normalize all ingress into a shared requester identity, task record, approval ledger, and audit envelope.
- **Risk:** Overlapping model-gateway responsibilities create gaps or double-counting. *Mitigation:* keep the planes separated — gateway owns routing/budgets/cascades/provider abstraction; Cloudflare owns logging/DLP/blocking/guardrails; gateway always routes upstream through Cloudflare; neither substitutes for Tool Gateway write-approval gates.

## 5. Well-Architected Validation
- **Security:** least-privilege service accounts per Cloud Run service/job; secrets in Google Secret Manager; SaaS credentials out of agent prompts and exposed only through controlled adapters; approval for write actions; signed/pinned sandbox images; Cloud SQL private connectivity where feasible; AI-BOM snapshots; authenticated Cloudflare AI Gateway; configured DLP profiles and guardrails for model traffic.
- **Reliability & Performance:** async dispatch from ingress into worker queues; persist task state before long execution; idempotent tool-call records and retry-safe transitions; LangGraph checkpoints for resumability; Cloud Run Jobs/Worker Pools for long execution; zonal Cloud SQL for POC cost; pgvector indexes only when retrieval volume justifies them.
- **Cost Optimization:** request-based Cloud Run with no minimum instances for ingress; Jobs/Worker Pools only when work exists; low-cost Cloud SQL sizing; USD $50/month configurable model budget in the gateway; route low-complexity work to cheaper models; logging volume controls and 12-month retention only for required audit streams; Cloudflare payload-logging controls to retain metadata without storing bodies where unnecessary.
- **Operational Excellence:** canonical Task contract for Slack/MCP/API/internal; persist task transitions, approvals, model calls, tool calls, and code-execution outputs; emit OpenTelemetry traces into Langfuse for agent/tool spans, latency, cost, and tokens; AI-BOM snapshot per release/config change; GUI admin console plus CLI/code administration; per-environment deployment manifest; versioned `gcloud`/`wrangler` scripts and an operator runbook; idempotent repeatable deployment.
- **Sustainability:** prefer serverless and scale-to-zero; avoid always-on GKE/Temporal for the first POC; right-size Cloud SQL and Cloud Run; route simple tasks to smaller models.

## 6. Acceptance Criteria
1. The default required stack is LangChain + LangGraph + Deep Agents + Langfuse, declared in the deployment manifest and asserted by tests.
2. LangSmith is optional only and never a runtime dependency.
3. Deep Agents subagents form a bounded, supervisor-orchestrated roster (planner, researcher/tool-router, code-writer, reviewer) — not an uncontrolled swarm.
4. LangGraph provides durable checkpoints and interrupt-based HITL pause/resume for >60-minute runs.
5. Model access is gateway-routed (LiteLLM-compatible) with Anthropic-direct and Vertex AI paths; agents/workers never call providers directly.
6. Cloudflare AI Gateway is integration-ready as the model-traffic governance plane and does not replace tool-write approval gates.
7. A USD $50/month configurable model budget is enforced at the gateway with per-user/per-task attribution.
8. Durable stores run in `australia-southeast1`; model processing may leave the region for the POC.
9. Dual ingress: Slack App (with HITL) and MCP; Claude Desktop and Claude Code are first-class MCP clients; Codex/OpenCode/Pi are deferred via the same boundary.
10. A canonical Task contract and lifecycle state machine normalize all ingress into one task record and audit envelope.
11. All write-class tools (write, external_send, financial, publishing, admin) require approval, gated through the shared approval ledger with payload-hash binding.
12. The toolpack manifest declares the required providers (Xero, HubSpot, Webflow, Bitscale, Cal.com, Clockify, Beehiiv, Google Workspace) each with an integration style.
13. Toolpacks support direct API, individual MCP, aggregate MCP, and Nango-aggregator integration styles.
14. The memory/context layer separates retrieval/evidence, session, task metadata, long-term memory, Deep Agents context, and Langfuse links, on Cloud SQL + pgvector.
15. The self-improvement loop (Option C) is proposal → evaluation → HITL approval → versioned promotion → AI-BOM update, with rollback and no runtime mutation of active instructions, permissions, or routing.
16. Observability is Langfuse-centered (traces, prompt/version management, datasets/evals, token/cost telemetry, audit dashboards).
17. A GUI admin/operator console and CLI/code administration both exist; the console covers tasks, approvals, toolpacks, MCP, AI-BOM, budget/routing, memory, self-improvement, deployment checks, and Langfuse observability.
18. Deployment is idempotent and redeployable across new or existing GCP projects / Cloudflare AI Gateways, with the platform/client boundary preserved; the POC is ready for MVP/POC deployment configuration after local validation and is not claimed production-ready.

## 7. Implementation Roadmap & Tasks
*Exact task strings ready for import/syncing into a project board / work management system (task-board columns: Item, Status, Timeline, Dependencies).*

| Task Name / Action Item | Target Component | Estimated Effort | Dependencies |
| :--- | :--- | :--- | :--- |
| Define reusable platform boundary and client-specific configuration boundary | Architecture / Platform | 0.5 Day | None |
| Create deployment manifest schema for tenant, region, model routes, tool packs, approval profile, and retention profile | Platform Config | 0.5 Day | Define reusable platform boundary and client-specific configuration boundary |
| Create tool pack manifest schema with integration styles for replaceable SaaS adapters | Tool Gateway | 0.5 Day | Define reusable platform boundary and client-specific configuration boundary |
| Create reusable gcloud bootstrap script for APIs, service accounts, Cloud SQL, Artifact Registry, and Secret Manager | Infra Automation | 1 Day | Create deployment manifest schema for tenant, region, model routes, tool packs, approval profile, and retention profile |
| Create reusable gcloud deploy script for Cloud Run ingress services, jobs, worker pools, GUI console, and environment variables | Infra Automation | 1 Day | Create reusable gcloud bootstrap script for APIs, service accounts, Cloud SQL, Artifact Registry, and Secret Manager |
| Create reusable Cloudflare wrangler deployment script for AI Gateway wrapper and environment bindings | Cloudflare Automation | 1 Day | Create deployment manifest schema for tenant, region, model routes, tool packs, approval profile, and retention profile |
| Add idempotency checks for existing GCP projects, APIs, service accounts, Cloud SQL, Pub/Sub, Cloud Run, and Cloudflare Gateway IDs | Infra Automation | 1 Day | Create reusable gcloud bootstrap script for APIs, service accounts, Cloud SQL, Artifact Registry, and Secret Manager |
| Create deployment runbook for repeatable client rollout, verification, rollback, and audit checks | Operations | 1 Day | Create reusable gcloud deploy script for Cloud Run ingress services, jobs, worker pools, GUI console, and environment variables |
| Create GCP Sydney project baseline and enable required APIs | Infra / GCP Foundation | 0.5 Day | None |
| Provision non-HA Cloud SQL PostgreSQL in australia-southeast1 | Data Layer | 0.5 Day | Create GCP Sydney project baseline and enable required APIs |
| Enable pgvector and create tenant-partitioned task, session, memory, evidence, approval, AI-BOM, budget, and gateway-event schemas | Data / Memory Layer | 1 Day | Provision non-HA Cloud SQL PostgreSQL in australia-southeast1 |
| Add LangGraph Postgres checkpointer schema for durable run state | Data / Orchestration | 0.5 Day | Enable pgvector and create tenant-partitioned task, session, memory, evidence, approval, AI-BOM, budget, and gateway-event schemas |
| Create Secret Manager entries for Slack, MCP, SaaS, model gateway, Langfuse, Anthropic, and Vertex credentials | Security / Secrets | 0.5 Day | Create GCP Sydney project baseline and enable required APIs |
| Build canonical Task contract and lifecycle state machine | Control Plane | 1 Day | Enable pgvector and create tenant-partitioned task, session, memory, evidence, approval, AI-BOM, budget, and gateway-event schemas |
| Implement Slack App ingress service with fast acknowledgement and async dispatch | Slack Ingress | 1 Day | Build canonical Task contract and lifecycle state machine |
| Implement MCP ingress for Claude Desktop and Claude Code with shared requester identity and Task creation | MCP Ingress | 1.5 Days | Build canonical Task contract and lifecycle state machine |
| Implement Pub/Sub or Cloud Tasks dispatch layer for long-running mesh tasks | Queue / Dispatch | 0.5 Day | Implement Slack App ingress service with fast acknowledgement and async dispatch |
| Containerize LangGraph + Deep Agents mesh worker for Cloud Run Jobs or Worker Pools | Execution Layer | 1.5 Days | Implement Pub/Sub or Cloud Tasks dispatch layer for long-running mesh tasks |
| Implement LangGraph supervisor graph with bounded Deep Agents roster (planner, researcher/tool-router, code-writer, reviewer) | Agent Mesh | 2 Days | Containerize LangGraph + Deep Agents mesh worker for Cloud Run Jobs or Worker Pools |
| Implement LangGraph interrupt-based approval pause/resume from durable checkpoints | Agent Mesh / HITL | 1 Day | Implement LangGraph supervisor graph with bounded Deep Agents roster (planner, researcher/tool-router, code-writer, reviewer) |
| Configure Cloudflare AI Gateway for model traffic visibility, DLP/query blocking, guardrails, and authenticated access | Cloudflare AI Gateway | 1 Day | Create reusable Cloudflare wrangler deployment script for AI Gateway wrapper and environment bindings |
| Configure LiteLLM-compatible gateway cascade for Vertex AI and Anthropic-direct through Cloudflare AI Gateway | Model Gateway | 1 Day | Configure Cloudflare AI Gateway for model traffic visibility, DLP/query blocking, guardrails, and authenticated access |
| Implement USD 50 monthly model budget ledger and per-user cost tracking | Budget / Governance | 1 Day | Configure LiteLLM-compatible gateway cascade for Vertex AI and Anthropic-direct through Cloudflare AI Gateway |
| Deploy Langfuse and configure OTLP/callback trace ingestion from mesh workers, gateway, and Cloudflare correlation IDs | Observability | 1 Day | Configure LiteLLM-compatible gateway cascade for Vertex AI and Anthropic-direct through Cloudflare AI Gateway |
| Configure Langfuse prompt/version management and datasets/evals | Observability / Evals | 1 Day | Deploy Langfuse and configure OTLP/callback trace ingestion from mesh workers, gateway, and Cloudflare correlation IDs |
| Implement AI-BOM snapshot generation for agents, prompts, tools, skills, and model routes | Governance / AI-BOM | 1 Day | Implement LangGraph supervisor graph with bounded Deep Agents roster (planner, researcher/tool-router, code-writer, reviewer) |
| Implement approval ledger and write-action approval workflow for Slack requesters | HITL / Slack | 1 Day | Implement Slack App ingress service with fast acknowledgement and async dispatch |
| Implement approval workflow for MCP requesters with shared approval ledger | HITL / MCP | 1.5 Days | Implement MCP ingress for Claude Desktop and Claude Code with shared requester identity and Task creation |
| Implement generic Tool Gateway loader for per-client tool pack manifests | Tool Gateway | 1 Day | Create tool pack manifest schema with integration styles for replaceable SaaS adapters |
| Implement sample Tool Gateway adapters for Google Workspace and HubSpot | Tool Gateway | 1.5 Days | Implement generic Tool Gateway loader for per-client tool pack manifests |
| Implement sample integration-style paths for Xero, Clockify, Webflow, Cal.com, Beehiiv, and Bitscale | Tool Gateway | 2 Days | Implement sample Tool Gateway adapters for Google Workspace and HubSpot |
| Implement prompt-to-code executor using Docker or Cloud Run Job sandbox | Prompt-to-Code | 2 Days | Containerize LangGraph + Deep Agents mesh worker for Cloud Run Jobs or Worker Pools |
| Persist code execution stdout, stderr, artifacts, proposed patches, and approval requirements | Prompt-to-Code / Audit | 1 Day | Implement prompt-to-code executor using Docker or Cloud Run Job sandbox |
| Implement retrieval ingestion for evidence_chunks with embeddings and freshness metadata | Context / Retrieval | 1.5 Days | Enable pgvector and create tenant-partitioned task, session, memory, evidence, approval, AI-BOM, budget, and gateway-event schemas |
| Implement memory summarization into memory_chunks separate from evidence_chunks | Context / Memory | 1 Day | Implement retrieval ingestion for evidence_chunks with embeddings and freshness metadata |
| Implement self-improvement loop (Option C): proposal, evaluation, HITL approval, versioned promotion, rollback, AI-BOM update | Self-Improvement / Governance | 2 Days | Implement AI-BOM snapshot generation for agents, prompts, tools, skills, and model routes |
| Build GUI admin/operator console (Streamlit) covering tasks, approvals, toolpacks, MCP, AI-BOM, budget/routing, memory, self-improvement, deployment, and Langfuse | GUI Admin | 1.5 Days | Implement generic Tool Gateway loader for per-client tool pack manifests |
| Configure 12-month retention for audit records, AI-BOM snapshots, approvals, and tool-call logs | Governance / Retention | 0.5 Day | Deploy Langfuse and configure OTLP/callback trace ingestion from mesh workers, gateway, and Cloudflare correlation IDs |
| Generate AI-BOM snapshot from deployment manifest and tool pack manifest | Governance / AI-BOM | 0.5 Day | Implement AI-BOM snapshot generation for agents, prompts, tools, skills, and model routes |
| Run end-to-end test: Slack request creates a write-gated SaaS action from evidence with approval | E2E Test | 1 Day | Implement sample Tool Gateway adapters for Google Workspace and HubSpot |
| Run end-to-end test: MCP request triggers a long-running checkpointed mesh job and returns an artifact | E2E Test | 1 Day | Implement prompt-to-code executor using Docker or Cloud Run Job sandbox |
| Run failure test: model fallback, job retry, and budget-limit halt | Reliability Test | 1 Day | Implement USD 50 monthly model budget ledger and per-user cost tracking |
| Produce POC operations runbook and known limitations register | Operations | 1 Day | Run failure test: model fallback, job retry, and budget-limit halt |
| Review cost telemetry against USD 65 infra guardrail and USD 50 model guardrail | FinOps | 0.5 Day | Produce POC operations runbook and known limitations register |
| Package redeployment checklist and sample client configuration templates | Platform Handoff | 1 Day | Review cost telemetry against USD 65 infra guardrail and USD 50 model guardrail |

---

## 8. GSD Workflow (Planning & Execution)

> This section is **process guidance** for any agent/engineer driving delivery via the
> GSD (Get Shit Done) workflow. It does not alter the normative architecture above
> (§1–§7) — that remains the operating manual for *what* to build. This governs *how*
> work is planned, executed, and tracked.

**Source of truth for delivery state** lives in `.planning/`:

| File | Role |
| :--- | :--- |
| `.planning/PROJECT.md` | Living project context: What This Is, Core Value, Validated/Active/Out-of-Scope requirements, constraints, key decisions. Evolves at phase/milestone boundaries. |
| `.planning/REQUIREMENTS.md` | Checkable v1 requirements with REQ-IDs (DUR/SEC/ORCH/SBX/GW/OBS/TOOL/SI/E2E/DEP), v2 deferrals, out-of-scope, and phase traceability. |
| `.planning/ROADMAP.md` | 5 coarse phases (horizontal layers), each with goal, dependencies, mapped REQ-IDs, observable success criteria, and plan stubs. |
| `.planning/STATE.md` | Project memory: current position, velocity, decisions, blockers, deferred items, session continuity. |
| `.planning/config.json` | Workflow config: YOLO mode, coarse granularity, parallel execution, quality model profile, research+plan-check+verifier on. |
| `.planning/codebase/` | Mapped brownfield analysis (ARCHITECTURE/CONCERNS/CONVENTIONS/STACK/STRUCTURE/TESTING). |

**Milestone goal** (this cycle): complete the runnable scaffold — replace every stubbed
component with a real, locally-validated implementation, then prove the platform
end-to-end and validate deploy-readiness. **Scope = full-vertical** (finish all stubs);
**structure = horizontal layers** (durability → orchestration → model/observability →
tools/self-improvement → E2E+deploy-readiness). Deploy-ready only — **no live GCP
provisioning** this milestone.

**Phase order:** 1 → 2 → 3 → 4 → 5, each depending on the prior. See `ROADMAP.md` for
per-phase goals, REQ mappings, and success criteria.

**Driving the workflow (slash commands):**
- `/gsd:plan-phase <N>` — create the detailed `PLAN.md` for phase N (spawns gsd-planner + gsd-plan-checker).
- `/gsd:discuss-phase <N>` — gather context before planning (optional).
- `/gsd:execute-phase <N>` — execute all plans in the phase (wave-based, parallel per config).
- `/gsd:progress` — situational status / advance the workflow.

**Prerequisite:** GSD subagents (`gsd-planner`, `gsd-plan-checker`, `gsd-phase-researcher`,
`gsd-verifier`, …) are **not** in `~/.claude/agents/`. Install them before planning:
`npx get-shit-done-cc@latest --global`. Without them, `/gsd:plan-phase` will fail to
spawn its planner subagent.

**Guardrails that survive every phase** (do not let planning regress these):
- The human-in-the-loop **write-approval gate** holds for every write-class tool (payload-hash bound).
- **No runtime autonomous self-modification** of active instructions, permissions, or routing (Option C).
- **Deep Agents roster stays bounded and declared** (planner, researcher/tool-router, code-writer, reviewer) — no uncontrolled self-spawning.
- **LangChain + LangGraph + Deep Agents + Langfuse** remain REQUIRED; LangSmith never a dependency.
