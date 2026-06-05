# Architectural Design Pattern: Reusable Autonomous Agent Mesh POC via AG2 on GCP

## 1. Executive Summary & Intent
- **Context:** Define a reusable, governed autonomous agent mesh pattern for small consultancies or client delivery teams. The concrete SaaS resources and tool adapters may vary by deployment, but the core agent fleet architecture, ingress model, task contract, execution plane, memory layer, approval model, and observability approach remain stable.
- **Solution Intent:** Use AG2 as the reusable multi-agent execution layer, Cloud Run services as Slack/MCP/API ingress, Cloud Run Jobs or Worker Pools as the long-running execution plane, Cloud SQL for PostgreSQL with `pgvector` as the durable memory and audit store, LiteLLM for model routing/budgets/cascades, Cloudflare AI Gateway for model-traffic visibility, auditability, DLP/query blocking, guardrails, and rate controls, and Langfuse/OpenTelemetry for mesh-level trace, cost, and token telemetry. SaaS integrations are packaged as replaceable client-specific tool packs behind a consistent Tool Gateway contract.

> **Implementation status (POC scaffold).** This document is the normative
> design pattern. A runnable Python-first scaffold of it lives in `src/agent_mesh/`
> and is exercised by `make test` / `make smoke` with no cloud dependencies — see
> [README.md](./README.md) for clone-and-run readiness and the scaffolded-vs-needs-development
> matrix, [docs/language-decision.md](./docs/language-decision.md) for the
> Python-first/TS-at-edge rationale, [RUNBOOK.md](./RUNBOOK.md) for local smoke
> checks and deployment, [docs/self-improvement-loop.md](./docs/self-improvement-loop.md)
> for the approval-gated self-improvement design (Option C) and its AG2 mapping,
> and [docs/production-readiness-caveats.md](./docs/production-readiness-caveats.md)
> for the hardening required before production. The POC is not production-ready,
> and performs no runtime autonomous self-modification of active instructions.

## 2. Refined Engineering Requirements
- **Functional Requirements:**
  - Provide a redeployable reference architecture where the agent fleet, task lifecycle, memory layer, approval workflow, and telemetry model are reusable across clients.
  - Treat SaaS resources as replaceable tool packs, not core architecture dependencies.
  - Provide dual user ingress through a Slack App and an MCP endpoint with mirrored capabilities.
  - Route Slack, MCP, and internal calls through a common API and Task contract so the orchestrator remains the source of truth.
  - Support over-60-minute mesh runs through durable worker/job execution rather than request-bound Cloud Run service execution.
  - Use AG2 group-chat / blackboard-style multi-agent orchestration for dynamic agent coordination and self-correction.
  - Provide prompt-to-code execution where agents can create artifacts and proposed patches.
  - Execute generated code only in isolated Docker or Cloud Run Job sandboxes, never directly on the host.
  - Require requester approval before write actions, including creates, updates, deletes, sends, publishes, invoices, payments, commits, or production mutations.
  - Deliver high-risk approval prompts to the respective requester through Slack or MCP, with a shared approval ledger.
  - Store AI-BOM snapshots covering agents, prompts, tools, skills, model routes, versions, and approved capabilities.
  - Provide token, cost, latency, task, tool-call, and approval telemetry.
  - Use mixed model cascades across Vertex Gemini, Claude, and optional local/open models through LiteLLM.
  - Route all model traffic from LiteLLM through Cloudflare AI Gateway for visibility, audit logs, DLP/query blocking, guardrails, and request metadata.
  - Support repeatable deployment through environment-specific configuration, infrastructure-as-code, schema migrations, and per-client tool manifests.
  - Provide reusable `gcloud` scripts, Cloudflare `wrangler` scripts, deployment manifests, tool-pack manifests, and a repeatable deployment runbook.
  - Ensure deployment scripts are idempotent and can safely target either a new recommended deployment environment or an existing GCP project / Cloudflare AI Gateway.

- **Non-Functional Requirements:**
  - **Scale:** Initial POC target is 5 users.
  - **Region:** Durable data stores must run in Sydney, `australia-southeast1`.
  - **Data Residency:** Prompt/model processing may leave Australia for the POC; durable stores remain in Australia.
  - **Execution Duration:** Long mesh runs may exceed 60 minutes and must retain state through jobs, worker queues, and durable task records.
  - **Budget:** Enforce a user-configurable model budget starting at USD $50/month.
  - **Infrastructure Cost Posture:** Target lean non-critical POC infrastructure, estimated around USD $40-$65/month under light usage assumptions, excluding model tokens, SaaS subscriptions, and GST.
  - **Availability:** Cloud SQL high availability is not required for the POC because this is not a critical workload.
  - **Retention:** Retain traces, AI-BOM snapshots, approval records, tool-call logs, and task audit records for 12 months.
  - **Governance Scope:** A bespoke tool-egress policy/classification gateway is out of scope for this POC. Cloudflare AI Gateway DLP/query blocking and guardrails are in scope for model traffic.
  - **Redeployability:** The pattern must separate reusable platform components from client-specific adapters, credentials, SaaS schemas, and approval policies.
  - **Idempotent Deployment:** Scripts must detect existing GCP projects, APIs, service accounts, Cloud SQL instances, Artifact Registry repositories, Pub/Sub topics, Cloud Run services/jobs, and Cloudflare AI Gateway configuration inputs before attempting creation.

## 3. Target Cloud Architecture
- **Generative AI Layer:** 
  - **Model Gateway Separation of Responsibilities (explicit for the POC):**
    - **LiteLLM owns model control-plane logic:** model routing, model cascades/fallbacks, per-user and per-task budget enforcement, token/max-output limits, model policy and routing profiles (`MODEL_ROUTE_PROFILE`), cost attribution, and provider abstraction. LiteLLM presents Cloudflare AI Gateway as its upstream rather than calling model providers directly.
    - **Cloudflare AI Gateway owns model-traffic governance and observability:** AI/model traffic logging, DLP matching, query blocking, prompt/response guardrails, AI Gateway audit visibility, request/response metadata and payload logging controls, and rate limiting/caching where applicable.
    - **Flow:** AG2 agents → LiteLLM (routing/budgets/cascades) → Cloudflare AI Gateway (logging/DLP/blocking/guardrails) → upstream model providers.
    - LiteLLM MUST route all upstream model calls through Cloudflare AI Gateway; agents and workers never call providers directly.
    - Neither gateway governs SaaS tool writes; tool-write governance stays in the Tool Gateway approval ledger.
  - Use LiteLLM as the model routing and budget gateway for Vertex Gemini, Claude, and optional local/open model cascades.
  - Route LiteLLM upstream calls through Cloudflare AI Gateway before reaching model providers.
  - Use Cloudflare AI Gateway for:
    - Request and response visibility.
    - Prompt/response metadata logs.
    - Token usage, provider, model, status, cost, and duration logs.
    - DLP matching and query blocking for model traffic.
    - Guardrails for prompt and/or response moderation.
    - Provider-level request timeout and retry controls where applicable.
    - Rate limiting and caching policies where appropriate.
  - Use Cloudflare per-request logging controls where sensitive payload storage should be skipped while retaining metadata.
  - Use task-tier routing:
    - Low-complexity routing to cheaper Gemini or compact models.
    - Medium-complexity routing to Gemini Flash/Pro or Claude Sonnet-class models.
    - High-complexity reasoning and prompt-to-code review routed to Claude or higher-capability Gemini models where justified.
  - Enforce per-user and per-task model budgets, max token limits, fallback rules, and cost attribution in LiteLLM.
  - Send token/cost metadata to Cloudflare AI Gateway, LiteLLM logs, and Langfuse via OpenTelemetry-compatible spans and model gateway logs.
  - Attach shared request metadata to model calls:
    - `tenant_id`
    - `client_slug`
    - `task_id`
    - `session_id`
    - `requester_id`
    - `entrypoint`
    - `agent_role`
    - `model_route_profile`
    - `approval_state`

- **Compute & Integration Layer:** 
  - Use Cloud Run services in `australia-southeast1` for:
    - Slack Events API ingress.
    - MCP HTTP ingress.
    - Internal API / Task contract endpoint.
    - Approval callback handling.
  - Use Cloud Run Jobs or Cloud Run Worker Pools for:
    - Long-running AG2 mesh executions.
    - Prompt-to-code sandbox runs.
    - Retryable background work.
    - Artifact generation and proposed patch preparation.
  - Use Pub/Sub or Cloud Tasks for dispatch between ingress services and execution workers.
  - Keep the Task contract Temporal-ready so Temporal can be introduced later without changing Slack, MCP, or tool-gateway contracts.
  - Prefer Cloud Run Jobs for bounded long tasks and Worker Pools for continuously polling worker patterns.
  - Package deployment as a reusable stack with parameterized environment values:
    - `PROJECT_ID`
    - `REGION`
    - `TENANT_ID`
    - `CLIENT_SLUG`
    - `SLACK_APP_CONFIG`
    - `MCP_SERVER_BASE_URL`
    - `MODEL_ROUTE_PROFILE`
    - `TOOL_PACK_MANIFEST`
    - `APPROVAL_POLICY_PROFILE`
    - `RETENTION_PROFILE`
    - `CLOUDFLARE_ACCOUNT_ID`
    - `CLOUDFLARE_AI_GATEWAY_ID`
    - `CLOUDFLARE_ZERO_TRUST_DLP_PROFILE`
    - `WRANGLER_ENV`
    - `CREATE_PROJECT`
    - `BILLING_ACCOUNT_ID`
    - `REUSE_EXISTING_CLOUDFLARE_GATEWAY`

- **Cloudflare AI Gateway Layer:** 
  - Cloudflare AI Gateway is the model-traffic governance/observability plane (logging, DLP, query blocking, guardrails, audit visibility, metadata/payload logging controls, rate limiting/caching); LiteLLM remains the model control plane (routing, cascades/fallbacks, budgets, token limits, routing profiles, provider abstraction). The two are deliberately separated.
  - Use Cloudflare AI Gateway between LiteLLM and upstream model providers.
  - Manage the Cloudflare worker/wrapper and environment bindings with `wrangler`.
  - Prefer a new dedicated Cloudflare AI Gateway per client/environment, but support reusing an existing AI Gateway by setting `CLOUDFLARE_AI_GATEWAY_ID`.
  - Use Cloudflare Zero Trust / Gateway DLP policies for model-query blocking where applicable.
  - Export or inspect Cloudflare AI Gateway logs for audit review.
  - Keep Cloudflare AI Gateway configuration deployment-specific but represented in the reusable deployment manifest.
  - Do not use Cloudflare AI Gateway as a replacement for tool-write approval gates; it governs model traffic, not SaaS mutations.

- **Reusable Platform Boundary:** 
  - Keep the following components stable across deployments:
    - Slack/MCP/API ingress pattern.
    - Canonical Task contract and lifecycle.
    - AG2 agent fleet roles and orchestration loop.
    - Cloud Run Jobs or Worker Pools execution pattern.
    - Cloud SQL schema families for tasks, sessions, memory, evidence, approvals, AI-BOM, budgets, and tool calls.
    - LiteLLM model control-plane contract (routing, cascades/fallbacks, budgets, token limits, routing profiles, provider abstraction).
    - Cloudflare AI Gateway model-traffic governance contract (logging, DLP, query blocking, guardrails, audit visibility, metadata/payload logging controls, rate limiting/caching).
    - Langfuse/OpenTelemetry trace schema.
    - Approval ledger and write-action gating contract.
  - Keep the following components deployment-specific:
    - SaaS tools and credentials.
    - Monday.com board IDs and column IDs.
    - HubSpot pipelines/properties.
    - Google Drive folders and shared drives.
    - Xero tenants/accounts.
    - Clockify workspace/project IDs.
    - Webflow site IDs.
    - tl;dv workspace settings.
    - Bitscale workspace/API details.
    - Client-specific prompts, routines, approval rules, and budget limits.

- **Data & Vector Store:** 
  - Use Cloud SQL for PostgreSQL in `australia-southeast1`, non-HA, with automated backups.
  - Enable `pgvector` for lightweight vector retrieval inside PostgreSQL.
  - Use separate logical tables/collections for:
    - `tasks`: task metadata, state, entrypoint, requester, correlation IDs, lifecycle timestamps.
    - `sessions`: Slack/MCP session summaries, conversation summaries, and active run references.
    - `memory_chunks`: reusable semantic memory, routine notes, and session-derived summaries.
    - `evidence_chunks`: retrieval documents, tool evidence, source snippets, evidence pointers, freshness metadata, and embeddings.
    - `tool_calls`: tool invocation requests, parameters, outcomes, requester, model route, and correlation IDs.
    - `approval_records`: write-action approval requests, decisions, approver, channel, timestamp, and payload hash.
    - `ai_bom_snapshots`: agent definitions, tools, skills, prompts, model routes, versions, and approved capability bundles.
    - `budget_ledger`: model calls, tokens, estimated cost, budget owner, and month-to-date usage.
    - `gateway_events`: Cloudflare AI Gateway request IDs, LiteLLM request IDs, DLP action metadata, provider status, model route, and audit correlation IDs.
  - Keep evidence chunks separate from session summaries and task metadata to avoid mixing operational state with retrieval evidence.

- **Monday.com API Bridge:** 
  - Treat Monday.com as an example write-gated SaaS tool exposed through the Tool Gateway, not as a mandatory core dependency.
  - Map mesh tasks to Monday.com board items using the following canonical columns:
    - `Item`: human-readable task/action name.
    - `Status`: `Not Started`, `Working on it`, `Blocked`, `Awaiting Approval`, `Done`, `Failed`.
    - `Timeline`: planned start/end date derived from task estimates and dependencies.
    - `Dependencies`: upstream task IDs or board item references.
  - All Monday.com write actions require explicit requester approval before execution.
  - Store Monday.com item IDs and update outcomes in `tool_calls` and `approval_records`.
  - For redeployability, map Monday.com resources through a per-client `tool_pack_manifest.yaml` file rather than hardcoding board, group, item, or column IDs.

- **Tool Pack Contract:** 
  - Each client deployment supplies a tool pack manifest that declares:
    - Tool name and semantic description.
    - Tool category: read, write, external-send, financial, publishing, code, or admin.
    - Required OAuth scopes or API credentials.
    - Approval requirement.
    - Input JSON schema.
    - Output JSON schema.
    - Freshness expectations.
    - Rate-limit assumptions.
    - SaaS resource identifiers.
    - Owner and support contact.
  - The reusable platform loads tool manifests into the AI-BOM snapshot and exposes only approved tools to AG2 agents.
  - Agents never receive raw credentials; the Tool Gateway resolves credentials at execution time.

- **Memory / Context Layer:** 
  - Implement the context layer directly on Cloud SQL PostgreSQL plus `pgvector` for the POC.
  - Use `memory_chunks` for summarized agent memory, reusable routines, task learnings, and user/project context.
  - Use `evidence_chunks` for retrieval documents, tool evidence, source excerpts, SaaS-derived evidence, and embeddings.
  - Attach evidence pointers to task outputs, proposed patches, and write-action approval requests.
  - Keep the knowledge layer as a cache/index/evidence pointer system, not as a system of record.
  - Use tenant/client partitioning on all memory and evidence tables so the same schema can support multiple redeployments without mixing contexts.

- **Prompt-to-Code Layer:** 
  - Use AG2 code-writer and code-executor agent roles.
  - Allow generated code to create artifacts, diagnostics, scripts, and proposed patches.
  - Execute code in short-lived Docker or Cloud Run Job sandboxes with least-privilege service accounts.
  - Return stdout, stderr, exit code, generated artifact paths, and patch diffs to the agent loop for self-correction.
  - Require approval before any generated patch, SaaS mutation, repository commit, file overwrite, external send, or production-impacting write is applied.
  - Persist prompt-to-code execution results in `tool_calls`, `evidence_chunks`, and task audit logs.

## 4. Risks, Limitations & Mitigation Strategies
- **Risk/Limitation:** Hardcoded SaaS identifiers would make the architecture brittle and non-redeployable.
  - *Mitigation:* Use per-client tool pack manifests, environment variables, Secret Manager entries, and migration scripts instead of hardcoded board IDs, workspace IDs, folder IDs, or API endpoints.

- **Risk/Limitation:** Deployment scripts can accidentally overwrite existing client environments if they assume greenfield infrastructure.
  - *Mitigation:* Make scripts idempotent by default, require explicit environment variables for destructive or project-creation actions, detect existing resources before creating them, and support reuse of existing GCP projects and Cloudflare AI Gateways.

- **Risk/Limitation:** Client-specific prompts, routines, and tools can drift from the reusable architecture.
  - *Mitigation:* Version all prompts, routines, tool manifests, and model route profiles; include them in AI-BOM snapshots and release manifests.

- **Risk/Limitation:** Cloud Run services are not suitable as the sole runtime for over-60-minute mesh tasks.
  - *Mitigation:* Use Cloud Run Jobs or Worker Pools for long-running execution, with task state persisted in Cloud SQL and dispatch via Pub/Sub or Cloud Tasks.

- **Risk/Limitation:** Model processing may leave Australia when using global or non-AU model endpoints.
  - *Mitigation:* Keep durable stores in Sydney and document that model inference residency is relaxed for the POC.

- **Risk/Limitation:** Cloud SQL without HA creates a database availability SPOF.
  - *Mitigation:* Accept this for the non-critical POC, enable automated backups, and define HA upgrade as a post-POC production hardening step.

- **Risk/Limitation:** `pgvector` inside Cloud SQL is sufficient for small-scale retrieval but may not meet high-scale vector search needs.
  - *Mitigation:* Use separate `memory_chunks` and `evidence_chunks` schemas now; allow future migration to AlloyDB, Vertex Vector Search, or another vector store if retrieval volume or latency demands increase.

- **Risk/Limitation:** Generated code can be unsafe if executed with broad host or network access.
  - *Mitigation:* Never use local host execution in production-like paths; execute code in Docker or Cloud Run Job sandboxes with scoped service accounts, timeouts, isolated work directories, and explicit approval before writes.

- **Risk/Limitation:** Observability does not equal enforcement.
  - *Mitigation:* Use Cloudflare AI Gateway for model-traffic DLP/query blocking and guardrails. Keep SaaS/tool-write governance limited to audit, AI-BOM, budget tracking, and approval gates for writes.

- **Risk/Limitation:** Cloudflare AI Gateway governs model traffic but not downstream SaaS tool execution.
  - *Mitigation:* Keep approval gates on all write actions in the Tool Gateway and store approval decisions in the shared approval ledger.

- **Risk/Limitation:** Cloudflare log storage limits can stop new logs from being saved if storage is exhausted.
  - *Mitigation:* Configure storage limits, automatic deletion/export posture, and external audit retention where required by the 12-month retention profile.

- **Risk/Limitation:** LiteLLM model cascades can hide provider-specific failures or cost spikes if poorly configured.
  - *Mitigation:* Define explicit route tiers, token caps, fallback ordering, per-user budgets, and alerting on budget thresholds.

- **Risk/Limitation:** Slack and MCP identity contexts can diverge.
  - *Mitigation:* Normalize all ingress into a shared requester identity, task record, approval ledger, and audit envelope.

- **Risk/Limitation:** Overlapping model-gateway responsibilities (e.g. attempting routing/budgets in Cloudflare or logging/DLP/guardrails in LiteLLM) can create gaps, double-counting, or unenforced policy.
  - *Mitigation:* Keep the two planes explicitly separated: LiteLLM owns routing, cascades/fallbacks, budgets, token limits, and routing profiles; Cloudflare AI Gateway owns logging, DLP, query blocking, guardrails, audit visibility, metadata/payload logging controls, and rate limiting/caching. LiteLLM always routes upstream calls through Cloudflare AI Gateway, and neither plane substitutes for Tool Gateway write-approval gates.

## 5. AWS Well-Architected Validation
- **Security:** 
  - Use least-privilege service accounts per Cloud Run service/job.
  - Store secrets in Google Secret Manager.
  - Keep SaaS credentials out of agent prompts and expose tools only through controlled adapters.
  - Require approval for write actions.
  - Use signed or pinned container images for execution sandboxes.
  - Use Cloud SQL private connectivity where feasible.
  - Maintain AI-BOM snapshots for agents, prompts, tools, skills, and model routes.
  - Parameterize client-specific credentials and resource IDs through Secret Manager and deployment manifests.
  - Route model traffic through authenticated Cloudflare AI Gateway.
  - Configure Cloudflare DLP profiles and guardrails for model traffic according to the deployment profile.

- **Reliability & Performance:** 
  - Use asynchronous dispatch from Slack/MCP ingress into worker queues.
  - Persist all task state before long-running execution begins.
  - Use idempotent tool-call records and retry-safe task transitions.
  - Use Cloud Run Jobs or Worker Pools for long execution and resumability.
  - Keep Cloud SQL zonal for POC cost control; add HA only after production promotion.
  - Use pgvector indexes only after retrieval volume justifies indexing overhead.

- **Cost Optimization:** 
  - Use request-based Cloud Run services with no minimum instances for ingress.
  - Use Cloud Run Jobs/Worker Pools only when work exists.
  - Start with non-HA Cloud SQL `db-g1-small` or equivalent low-cost sizing.
  - Enforce USD $50/month configurable model budget through LiteLLM.
  - Route low-complexity work to cheaper models and reserve premium models for complex reasoning, prompt-to-code review, and high-risk tasks.
  - Set logging volume controls and 12-month retention only for required audit streams.
  - Use Cloudflare payload logging controls to retain metadata without storing prompt/response bodies where full payload retention is unnecessary.

- **Operational Excellence:** 
  - Use a canonical Task contract for Slack, MCP, API, and internal work.
  - Persist task transitions, approvals, model calls, tool calls, and code execution outputs.
  - Emit OpenTelemetry traces into Langfuse for agent spans, tool spans, latency, cost, and token usage.
  - Maintain an AI-BOM snapshot per release/configuration change.
  - Use Monday.com task sync for implementation tracking.
  - Maintain a deployment manifest per client/environment that captures region, tenant, model routes, tool packs, approval profile, retention profile, and SaaS resource mappings.
  - Manage repeatable deployment through versioned `gcloud` scripts, `wrangler` scripts, manifest templates, and an operator runbook.
  - Run deployment scripts safely multiple times without duplicating resources or requiring teardown between client rollouts.

- **Sustainability:** 
  - Prefer serverless and scale-to-zero components where possible.
  - Avoid always-on GKE/Temporal infrastructure for the first POC.
  - Use right-sized Cloud SQL and Cloud Run resources.
  - Route simple tasks to smaller models to reduce compute waste.

## 6. Implementation Roadmap & Monday.com Tasks
*Provide exact task strings ready for import/syncing to Monday.com boards.*

| Task Name / Action Item | Target Component | Estimated Effort | Dependencies |
| :--- | :--- | :--- | :--- |
| Define reusable platform boundary and client-specific configuration boundary | Architecture / Platform | 0.5 Day | None |
| Create deployment manifest schema for tenant, region, model routes, tool packs, approval profile, and retention profile | Platform Config | 0.5 Day | Define reusable platform boundary and client-specific configuration boundary |
| Create tool pack manifest schema for replaceable SaaS adapters | Tool Gateway | 0.5 Day | Define reusable platform boundary and client-specific configuration boundary |
| Create reusable gcloud bootstrap script for APIs, service accounts, Cloud SQL, Artifact Registry, and Secret Manager | Infra Automation | 1 Day | Create deployment manifest schema for tenant, region, model routes, tool packs, approval profile, and retention profile |
| Create reusable gcloud deploy script for Cloud Run ingress services, jobs, worker pools, and environment variables | Infra Automation | 1 Day | Create reusable gcloud bootstrap script for APIs, service accounts, Cloud SQL, Artifact Registry, and Secret Manager |
| Create reusable Cloudflare wrangler deployment script for AI Gateway wrapper and environment bindings | Cloudflare Automation | 1 Day | Create deployment manifest schema for tenant, region, model routes, tool packs, approval profile, and retention profile |
| Add idempotency checks for existing GCP projects, APIs, service accounts, Cloud SQL, Pub/Sub, Cloud Run, and Cloudflare Gateway IDs | Infra Automation | 1 Day | Create reusable gcloud bootstrap script for APIs, service accounts, Cloud SQL, Artifact Registry, and Secret Manager |
| Create deployment runbook for repeatable client rollout, verification, rollback, and audit checks | Operations | 1 Day | Create reusable gcloud deploy script for Cloud Run ingress services, jobs, worker pools, and environment variables |
| Create GCP Sydney project baseline and enable required APIs | Infra / GCP Foundation | 0.5 Day | None |
| Provision non-HA Cloud SQL PostgreSQL in australia-southeast1 | Data Layer | 0.5 Day | Create GCP Sydney project baseline and enable required APIs |
| Enable pgvector and create tenant-partitioned task, session, memory, evidence, approval, AI-BOM, and budget schemas | Data / Memory Layer | 1 Day | Provision non-HA Cloud SQL PostgreSQL in australia-southeast1 |
| Create Secret Manager entries for Slack, MCP, SaaS, LiteLLM, Langfuse, and model credentials | Security / Secrets | 0.5 Day | Create GCP Sydney project baseline and enable required APIs |
| Build canonical Task contract and lifecycle state machine | Control Plane | 1 Day | Enable pgvector and create tenant-partitioned task, session, memory, evidence, approval, AI-BOM, and budget schemas |
| Implement Slack App ingress service with fast acknowledgement and async dispatch | Slack Ingress | 1 Day | Build canonical Task contract and lifecycle state machine |
| Implement MCP ingress service with shared requester identity and Task creation | MCP Ingress | 1.5 Days | Build canonical Task contract and lifecycle state machine |
| Implement Pub/Sub or Cloud Tasks dispatch layer for long-running mesh tasks | Queue / Dispatch | 0.5 Day | Implement Slack App ingress service with fast acknowledgement and async dispatch |
| Containerize AG2 mesh worker for Cloud Run Jobs or Worker Pools | Execution Layer | 1.5 Days | Implement Pub/Sub or Cloud Tasks dispatch layer for long-running mesh tasks |
| Implement AG2 group-chat orchestration with planner, executor, reviewer, and tool-router agents | Agent Mesh | 2 Days | Containerize AG2 mesh worker for Cloud Run Jobs or Worker Pools |
| Configure Cloudflare AI Gateway for model traffic visibility, DLP/query blocking, guardrails, and authenticated access | Cloudflare AI Gateway | 1 Day | Create reusable Cloudflare wrangler deployment script for AI Gateway wrapper and environment bindings |
| Configure LiteLLM model cascade for Gemini, Claude, and optional local/open models through Cloudflare AI Gateway | Model Gateway | 1 Day | Configure Cloudflare AI Gateway for model traffic visibility, DLP/query blocking, guardrails, and authenticated access |
| Implement USD 50 monthly model budget ledger and per-user cost tracking | Budget / Governance | 1 Day | Configure LiteLLM model cascade for Gemini, Claude, and optional local/open models through Cloudflare AI Gateway |
| Deploy Langfuse and configure OTLP trace ingestion from mesh workers, LiteLLM, and Cloudflare correlation IDs | Observability | 1 Day | Configure LiteLLM model cascade for Gemini, Claude, and optional local/open models through Cloudflare AI Gateway |
| Implement AI-BOM snapshot generation for agents, tools, skills, prompts, and model routes | Governance / AI-BOM | 1 Day | Implement AG2 group-chat orchestration with planner, executor, reviewer, and tool-router agents |
| Implement approval ledger and write-action approval workflow for Slack requesters | HITL / Slack | 1 Day | Implement Slack App ingress service with fast acknowledgement and async dispatch |
| Implement approval workflow for MCP requesters with shared approval ledger | HITL / MCP | 1.5 Days | Implement MCP ingress service with shared requester identity and Task creation |
| Implement generic Tool Gateway loader for per-client tool pack manifests | Tool Gateway | 1 Day | Create tool pack manifest schema for replaceable SaaS adapters |
| Implement sample Tool Gateway adapters for Google Workspace and HubSpot MCP tools | Tool Gateway | 1.5 Days | Implement generic Tool Gateway loader for per-client tool pack manifests |
| Implement sample unified SaaS adapter path for Xero, Clockify, Webflow, tl;dv, and Bitscale | Tool Gateway | 2 Days | Implement sample Tool Gateway adapters for Google Workspace and HubSpot MCP tools |
| Implement sample Monday.com bridge with Item, Status, Timeline, and Dependencies mapping | Monday.com Integration | 1 Day | Implement sample unified SaaS adapter path for Xero, Clockify, Webflow, tl;dv, and Bitscale |
| Implement prompt-to-code executor using Docker or Cloud Run Job sandbox | Prompt-to-Code | 2 Days | Containerize AG2 mesh worker for Cloud Run Jobs or Worker Pools |
| Persist code execution stdout, stderr, artifacts, proposed patches, and approval requirements | Prompt-to-Code / Audit | 1 Day | Implement prompt-to-code executor using Docker or Cloud Run Job sandbox |
| Implement retrieval ingestion for evidence_chunks with embeddings and freshness metadata | Context / Retrieval | 1.5 Days | Enable pgvector and create tenant-partitioned task, session, memory, evidence, approval, AI-BOM, and budget schemas |
| Implement memory summarization into memory_chunks separate from evidence_chunks | Context / Memory | 1 Day | Implement retrieval ingestion for evidence_chunks with embeddings and freshness metadata |
| Configure 12-month retention for audit records, AI-BOM snapshots, approvals, and tool-call logs | Governance / Retention | 0.5 Day | Deploy Langfuse and configure OTLP trace ingestion from mesh workers and LiteLLM |
| Generate AI-BOM snapshot from deployment manifest and tool pack manifest | Governance / AI-BOM | 0.5 Day | Implement AI-BOM snapshot generation for agents, tools, skills, prompts, and model routes |
| Run end-to-end test: Slack request creates Monday.com item from tl;dv evidence with approval | E2E Test | 1 Day | Implement sample Monday.com bridge with Item, Status, Timeline, and Dependencies mapping |
| Run end-to-end test: MCP request triggers long-running mesh job and returns artifact | E2E Test | 1 Day | Implement prompt-to-code executor using Docker or Cloud Run Job sandbox |
| Run failure test: model fallback, job retry, and budget-limit halt | Reliability Test | 1 Day | Implement USD 50 monthly model budget ledger and per-user cost tracking |
| Produce POC operations runbook and known limitations register | Operations | 1 Day | Run failure test: model fallback, job retry, and budget-limit halt |
| Review cost telemetry against USD 65 infra guardrail and USD 50 model guardrail | FinOps | 0.5 Day | Produce POC operations runbook and known limitations register |
| Package redeployment checklist and sample client configuration templates | Platform Handoff | 1 Day | Review cost telemetry against USD 65 infra guardrail and USD 50 model guardrail |
