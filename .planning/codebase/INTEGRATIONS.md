# External Integrations

**Analysis Date:** 2026-06-05

## APIs & External Services

**Model Providers:**
- Anthropic Claude API (direct) - High-complexity reasoning, prompt-to-code review, and optional fallback
  - SDK/Client: `langchain-litellm>=0.1` via LiteLLM proxy
  - Auth: `ANTHROPIC_API_KEY` (Secret Manager)
  - Route: `anthropic/claude-sonnet-4-6` (default high-complexity), `anthropic/claude-haiku-4-5` (optional low-complexity)
  - Gateway: Routes through Cloudflare AI Gateway wrapper (configured in `config/model_gateway.config.yaml`)

- Google Vertex AI (Gemini + Claude-on-Vertex) - Low/medium-complexity routing, optional high-complexity
  - SDK/Client: `langchain-litellm>=0.1` via LiteLLM proxy
  - Auth: `VERTEX_PROJECT_ID`, `VERTEX_LOCATION`, `GOOGLE_APPLICATION_CREDENTIALS` (Service Account)
  - Routes: `vertex_ai/gemini-1.5-flash` (low-complexity), `vertex_ai/gemini-1.5-pro` (medium-complexity), `vertex_ai/claude-sonnet-4-6` (optional high-complexity)
  - Gateway: Routes through Cloudflare AI Gateway wrapper

**Slack Integration:**
- Slack Events API - User requests via app mentions and messages
  - SDK/Client: `slack-bolt>=1.18`
  - Auth: `SLACK_SIGNING_SECRET`, `SLACK_BOT_TOKEN` (Secret Manager)
  - Ingress: `POST /slack/events` in `src/agent_mesh/api/app.py`
  - Verification: HMAC-SHA256 signature verification with 5-minute timestamp tolerance
  - Approval Callbacks: Slack users approve write actions via interactive messages back to `POST /v1/approvals`

**Model Context Protocol (MCP):**
- MCP Streamable HTTP Ingress - Claude Desktop and Claude Code integration
  - SDK/Client: `mcp>=1.2`
  - Auth: OAuth resource server (configurable in `manifests/deployment.manifest.yaml`)
  - Ingress: `POST /mcp` in `src/agent_mesh/api/app.py`, routed through `src/agent_mesh/api/mcp_server.py`
  - First-class clients: Claude Desktop, Claude Code
  - Future clients: Codex, OpenCode, Pi (deferred, same MCP/tool boundary)
  - Tools exposed via MCP: Task creation, task status retrieval, approval submission

## Data Storage

**Databases:**
- Google Cloud SQL for PostgreSQL (australia-southeast1)
  - Connection: `DATABASE_URL` (Secret Manager, format: `postgresql://user:pass@host/database`)
  - Client: `psycopg[binary]>=3.1` (binary C adapter for performance)
  - Durable Storage: Tasks, sessions, memory chunks, evidence chunks, approval records, AI-BOM snapshots, budget ledger, tool calls, gateway events
  - Schema: Initialized via migrations in `migrations/0001_init.sql`, `migrations/0002_self_improvement.sql`
  - Vector Extension: `pgvector` for embeddings in `memory_chunks` and `evidence_chunks` (768-dimensional, Vertex embedding model)
  - Indexes: Task lifecycle (tenant_id, state), session tracking, event audit trails

**File Storage:**
- Local filesystem only for the POC - Generated code artifacts, proposed patches, and code-execution artifacts stored locally during execution
- Production: Cloud Storage (GCS) would be added for artifact persistence across Cloud Run Job instances

**Caching:**
- None detected in current implementation - Model responses cached in Langfuse; tool results cached via evidence chunks with freshness metadata (SLA per tool)

## Authentication & Identity

**Auth Provider:**
- Custom multi-entrypoint normalization (no third-party auth service for internal agents)
  - Slack: User identity sourced from Slack user ID, mapped to tenant context
  - MCP: OAuth resource server (configurable per deployment)
  - API: Direct task creation with explicit `requester_id` and tenant context
  - Normalized via `RequesterIdentity` contract in `src/agent_mesh/contracts/models.py`

**Credential Management:**
- Google Secret Manager - All secrets stored at rest
  - SaaS OAuth tokens: `GOOGLE_WORKSPACE_OAUTH`, `HUBSPOT_PRIVATE_APP_TOKEN`, `XERO_OAUTH`, `WEBFLOW_API_TOKEN`, `BITSCALE_API_KEY`, `CALCOM_API_KEY`, `CLOCKIFY_API_KEY`, `BEEHIIV_API_KEY`
  - Model provider keys: `ANTHROPIC_API_KEY`
  - Gateway secrets: `MODEL_GATEWAY_SHARED_SECRET`, `MODEL_GATEWAY_MASTER_KEY`
  - Observability: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`
  - Injected at runtime via Cloud Run `--set-secrets` flag; never logged or embedded in configs

## Monitoring & Observability

**Error Tracking & Tracing:**
- Langfuse - Default required platform (not LangSmith; Langfuse is explicitly mandatory per design)
  - Features: Spans/traces, prompt/version management, datasets/evals, token/cost telemetry, audit dashboards
  - Integration: Attached to LangChain/LangGraph runs via `CallbackHandler` in `src/agent_mesh/observability.py`
  - Ingestion: LangChain callback handler + OpenTelemetry (OTEL) integration
  - Auth: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` (Secret Manager)
  - Endpoint: `LANGFUSE_HOST` (default: https://cloud.langfuse.com; self-hosted option available)
  - Shared metadata: tenant_id, client_slug, task_id, session_id, requester_id, entrypoint, agent_role, model_route_profile, approval_state

**Logs:**
- Stdout/stderr to Cloud Logging (Cloud Run native)
  - Task lifecycle events, worker execution logs, approval audit trail, budget enforcement logs
  - Payload logging controls: `COLLECT_LOG_PAYLOAD` (Cloudflare), `log_payloads.model_payloads` and `log_payloads.tool_payloads` (deployment manifest)

**Cloud Monitoring:**
- Google Cloud Monitoring (via Cloud Run metrics) - CPU, memory, error rates, latency
- Cloudflare Analytics - AI Gateway traffic, DLP matches, guardrail evaluations

## CI/CD & Deployment

**Hosting:**
- Google Cloud Run (services): Slack/MCP/API ingress, approval callbacks, GUI admin console
  - Region: australia-southeast1
  - Container images: `docker/api.Dockerfile`, `docker/gui.Dockerfile`
  - Secrets injection: Cloud Run `--set-secrets` flag

- Google Cloud Run Jobs / Worker Pools: Long-running LangGraph + Deep Agents mesh execution, prompt-to-code sandboxes
  - Region: australia-southeast1
  - Container images: `docker/worker.Dockerfile`, `docker/code-executor.Dockerfile`
  - Dispatch: Pub/Sub topic subscription (async pull)
  - Checkpointing: LangGraph state persisted to Cloud SQL between resumptions

- Google Artifact Registry: Container image storage
  - Repo: `agent-mesh` (default, configurable via deployment manifest)
  - Region: australia-southeast1

**CI Pipeline:**
- None detected in codebase (local `make test`, `make lint`, `make fmt` available)
- Deployment scripts: `scripts/gcp_deploy_core.sh`, `scripts/gcp_bootstrap.sh` (referenced in RUNBOOK.md, not fully listed)
- Cloudflare deployment: `cloudflare/ai-gateway-wrapper/wrangler.toml` with `wrangler deploy` automation

## Environment Configuration

**Required env vars:**
- Deployment identity: `TENANT_ID`, `CLIENT_SLUG`, `REGION`, `PROJECT_ID`
- Database: `DATABASE_URL` (PostgreSQL connection string)
- Pub/Sub dispatch: `USE_PUBSUB` (true for production), `TASK_TOPIC`, `APPROVAL_TOPIC`, `DLQ_TOPIC`
- Model gateway: `MODEL_GATEWAY_BASE_URL`, `MODEL_PROVIDER_MODE` (anthropic|vertex_ai|mixed), `MODEL_ROUTE_PROFILE`, `MODEL_MAX_TOKENS`, `MODEL_MONTHLY_BUDGET_USD`
- Model providers: `ANTHROPIC_API_KEY`, `VERTEX_PROJECT_ID`, `VERTEX_LOCATION`, `GOOGLE_APPLICATION_CREDENTIALS`
- Slack: `SLACK_SIGNING_SECRET`, `SLACK_BOT_TOKEN`
- Langfuse: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`
- SaaS tool credentials: Per tool pack (e.g., `GOOGLE_WORKSPACE_OAUTH`, `HUBSPOT_PRIVATE_APP_TOKEN`, `XERO_OAUTH`)

**Secrets location:**
- Google Secret Manager (production) - All sensitive values stored as secrets, injected at Cloud Run service/job startup
- Local `.env` file (development) - Copy `.env.example` and export values for local smoke checks

**Config files:**
- `config/model_gateway.config.yaml` - LiteLLM model routes, cascades/fallbacks, router settings (respects `os.environ/` runtime resolution)
- `manifests/deployment.manifest.yaml` - Parameterized tenant, cloud platform, budgets, ingress, tool packs, observability config per deployment
- `manifests/tool_pack_manifest.yaml` - SaaS tool declarations, integration styles, approval requirements, resource bindings, schemas

## Webhooks & Callbacks

**Incoming:**
- `POST /slack/events` - Slack Events API (app mentions, messages)
  - Signature verification with HMAC-SHA256 and timestamp tolerance
  - Ingress point: `src/agent_mesh/api/app.py`

- `POST /v1/approvals` - Approval decision callback shared by Slack and MCP
  - Submitter: Slack users (via interactive messages) or MCP clients
  - Ingress point: `src/agent_mesh/api/app.py`

- `POST /mcp` - Model Context Protocol Streamable HTTP entry point
  - Claude Desktop and Claude Code direct ingress
  - Ingress point: `src/agent_mesh/api/app.py`, routed to `src/agent_mesh/api/mcp_server.py`

**Outgoing:**
- Slack approvals - Slack bot sends interactive approval prompts to requester
  - Triggered on write-class tools and admin actions
  - Response routed back to `POST /v1/approvals`

- Langfuse telemetry - LangChain callback sends traces, tokens, costs to Langfuse cloud/self-hosted
  - Continuous during mesh execution

- Cloudflare AI Gateway logging - Model traffic logged and evaluated for DLP/guardrails
  - Request/response metadata and (optionally) payloads sent to Cloudflare

- SaaS tool mutations - Agent-generated mutations (writes, sends, publishes, financial) require approval
  - Approval gate enforced in `src/agent_mesh/worker/` before tool execution
  - Tool execution occurs via direct API, MCP server, aggregate MCP, or Nango integration

## Integration Styles by Tool

**Direct API:**
- Google Drive search, Gmail send, Google Sheets append
- HubSpot lookup/create
- Webflow CMS item creation
- Bitscale enrichment
- Cal.com bookings
- Beehiiv post creation
- Client: Direct HTTP/REST calls with OAuth/API key auth

**Nango Aggregator:**
- Xero (read invoices, create invoice)
- OAuth credential exchange and API routing via Nango integration layer

**MCP Server (Future):**
- Codex, OpenCode, Pi clients (deferred; same MCP/tool boundary)
- Declared in `manifests/tool_pack_manifest.yaml` but not yet implemented

**Aggregate MCP (Future):**
- One MCP server fronting multiple SaaS tools
- Declared in `manifests/tool_pack_manifest.yaml` but not yet implemented

---

*Integration audit: 2026-06-05*
