# Technology Stack

**Analysis Date:** 2026-06-05

## Languages

**Primary:**
- Python 3.11+ - Core agent mesh framework, orchestration, worker, API, and GUI
- TypeScript - Cloudflare AI Gateway wrapper and edge workers

**Secondary:**
- SQL (PostgreSQL dialect) - Database schema and migrations for durable state

## Runtime

**Environment:**
- Python 3.12-slim for containerized deployment (Docker)
- Node.js runtime for Cloudflare Workers (compatibility date 2026-06-01)

**Package Manager:**
- pip with `pyproject.toml` as source of truth
- Lockfiles: `requirements/base.txt`, `requirements/api.txt`, `requirements/worker.txt`, `requirements/gui.txt`, `requirements/dev.txt` (generated from pyproject.toml optional-dependencies groups)

## Frameworks

**Core:**
- FastAPI 0.110+ - REST API ingress for Slack, MCP, and approval callbacks (`src/agent_mesh/api/app.py`)
- Uvicorn 0.29+ - ASGI server for Cloud Run deployment

**Agent Orchestration (Default Required Stack):**
- LangChain 0.3+ - Tool/model abstraction layer for agent integration (`src/agent_mesh/worker/model_gateway.py`)
- LangGraph 0.2+ - Durable state graphs, checkpoints, and interrupt-based human-in-the-loop pause/resume
- Deep Agents 0.0.2+ - Bounded supervisor-orchestrated subagent roster (planner, researcher/tool-router, code-writer, reviewer)

**Observability (Default Required):**
- Langfuse 2.0+ - Open-source tracing, prompt/version management, datasets/evals, token/cost telemetry, audit dashboards (`src/agent_mesh/observability.py`)

**GUI:**
- Streamlit 1.36+ - Admin/operator console for task management, approvals, tool packs, AI-BOM, budget/routing, memory, and self-improvement (`src/agent_mesh/gui/admin_app.py`)

**Testing & Code Quality:**
- pytest 8.0+ - Unit and integration test framework (config in `pyproject.toml`)
- ruff 0.4+ - Linting and formatting (configured in `pyproject.toml` with line-length=100)

## Key Dependencies

**Critical:**
- pydantic>=2.6 - Data validation and serialization for task contracts and models (`src/agent_mesh/contracts/models.py`)
- httpx>=0.27 - Async HTTP client for external API calls and model gateway communication
- PyYAML>=6.0 - Configuration file parsing (deployment manifest, model gateway config, tool pack manifest)

**Infrastructure & Messaging:**
- google-cloud-pubsub>=2.21 - Pub/Sub for async task dispatch between ingress and workers
- psycopg[binary]>=3.1 - PostgreSQL driver for durable task/session/approval/budget state (`migrations/0001_init.sql`)

**Integrations:**
- slack-bolt>=1.18 - Slack Events API ingress and signature verification (`src/agent_mesh/api/app.py`, `src/agent_mesh/api/slack_verify.py`)
- mcp>=1.2 - Model Context Protocol for Claude Desktop and Claude Code integration (`src/agent_mesh/api/mcp_server.py`)
- litellm>=1.40 - LiteLLM-compatible model gateway proxy for Anthropic and Vertex AI routing (`config/model_gateway.config.yaml`)
- langchain-litellm>=0.1 - LangChain integration with LiteLLM for model routing

**Optional (used in specific roles):**
- langsmith - Optional alternative observability platform (NOT required; Langfuse is default)

## Configuration

**Environment:**
- Environment variables sourced from Google Secret Manager at deployment (no `.env` file in production)
- Runtime settings mapped in `src/agent_mesh/settings.py` with defaults for local development
- Model gateway configuration via `config/model_gateway.config.yaml` with environment variable resolution at runtime

**Build:**
- `Makefile` with targets: install, install-dev, schemas, test, lint, fmt, smoke, run-api, run-worker, run-gui
- `pyproject.toml` as source of truth for dependencies (base, runtime, agents, gui, dev optional-dependency groups)
- Docker build files: `docker/api.Dockerfile`, `docker/worker.Dockerfile`, `docker/gui.Dockerfile`, `docker/code-executor.Dockerfile`
- Cloudflare Wrangler config: `cloudflare/ai-gateway-wrapper/wrangler.toml` for AI Gateway wrapper deployment

**Deployment Manifests:**
- `manifests/deployment.manifest.yaml` - Parameterized tenant, region, GCP project, Cloud SQL, Cloud Run, Pub/Sub, Cloudflare, budgets, model routes, ingress, tool packs, and observability configuration
- `manifests/tool_pack_manifest.yaml` - Client-specific SaaS tool declarations with integration styles (direct_api, mcp_server, aggregate_mcp, nango_aggregator)

## Platform Requirements

**Development:**
- Python 3.11+ (3.12+ recommended)
- PostgreSQL 15+ with pgvector extension (for production; local dev uses in-memory storage)
- Docker (for containerized worker/ingress/GUI/code-executor deployments)
- Google Cloud SDK (gcloud CLI for GCP deployments)
- Cloudflare Wrangler 3+ (for AI Gateway wrapper deployment)

**Production/Deployment:**
- **Compute:** Google Cloud Run services (ingress: Slack/MCP/API/approval callbacks) and Cloud Run Jobs/Worker Pools (long-running mesh workers, code executors)
- **Database:** Google Cloud SQL for PostgreSQL in `australia-southeast1` with pgvector extension enabled
- **Messaging:** Google Pub/Sub for task and approval topic dispatch
- **Secrets:** Google Secret Manager for Slack tokens, API keys, OAuth credentials, Anthropic/Vertex AI keys, Langfuse keys, Cloudflare tokens
- **Model Gateway:** LiteLLM-compatible proxy (self-hosted or third-party) routing through Cloudflare AI Gateway
- **Observability:** Langfuse (cloud or self-hosted) for tracing and telemetry
- **Model Providers:** Anthropic (Claude direct) and/or Google Cloud Vertex AI (Gemini, Claude-on-Vertex)
- **Model Traffic Governance:** Cloudflare AI Gateway for DLP, query blocking, guardrails, audit logging
- **Container Registry:** Google Artifact Registry in `australia-southeast1`

---

*Stack analysis: 2026-06-05*
