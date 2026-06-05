# ausgtm-agent-mesh

Reusable, governed autonomous agent mesh reference implementation for small
consultancies and client delivery teams, built on the **LangChain + LangGraph +
Deep Agents + Langfuse** stack. Portable in principle across AWS/GCP/Azure; the
first MVP/POC targets GCP in Sydney (`australia-southeast1`) with a LiteLLM-compatible
model gateway (Anthropic direct + Vertex AI) and Cloudflare AI Gateway for
model-traffic governance.

## Default required stack

- **LangChain** — core tool/model abstraction (REQUIRED).
- **LangGraph** — durable orchestration: state graphs, checkpoints, interrupt-based
  human-in-the-loop pause/resume for >60-minute runs (REQUIRED).
- **Deep Agents** — bounded, supervisor-orchestrated subagent roster (planner,
  researcher/tool-router, code-writer, reviewer); not an uncontrolled swarm (REQUIRED).
- **Langfuse** — open-source/self-hostable observability: tracing, prompt/version
  management, datasets/evals, token/cost telemetry, audit dashboards (REQUIRED).
- **LangSmith** — optional alternative only; never a dependency.
- **Model gateway** — LiteLLM-compatible routing/budgets/cascades with Anthropic-direct
  and Vertex AI paths.
- **Cloudflare AI Gateway** — integration-ready model-traffic governance plane.

## Where to start

- **[CLAUDE.md](./CLAUDE.md)** — the normative architectural design pattern:
  reusable platform boundary, task contract, execution plane, memory/evidence
  layer, approval model, observability, acceptance criteria, and the Monday.com-ready
  roadmap. This is the operating manual for any agent or engineer working in this repo.
- **[docs/ecosystem-decision.md](./docs/ecosystem-decision.md)** — why the stack is
  LangChain/LangGraph/Deep Agents/Langfuse and why the core is Python-first with
  TypeScript only at the edge.
- **[docs/governance-crosswalk.md](./docs/governance-crosswalk.md)** — governance
  alignment crosswalk: required MVP governance coverage mapped to framework themes.
- **[RUNBOOK.md](./RUNBOOK.md)** — repeatable deployment runbook: provisioning,
  verification, rollback, and audit checks for a client rollout.
- **[docs/self-improvement-loop.md](./docs/self-improvement-loop.md)** — the
  self-improvement design decision (Option C: approval-gated, self-improving
  agents), LangGraph + Deep Agents mapping, safety boundaries, promotion/rollback,
  and AI-BOM implications. **No runtime autonomous self-modification of active
  instructions, permissions, or routing in the POC.**
- **[docs/production-readiness-caveats.md](./docs/production-readiness-caveats.md)**
  — remaining production hardening requirements, plus a per-caveat governance
  alignment crosswalk. The POC is not production-ready until these are owned and
  verified.

## Clone-and-run readiness

This repo ships a **runnable POC scaffold**. The contract layer, shared task
service, ingress, worker, approval gating, self-improvement loop, GUI admin
read-model, and prompt-to-code sandbox are importable and exercised by tests
without any cloud dependencies — heavy deps (`langchain`, `langgraph`, `deepagents`,
`langfuse`, `streamlit`, `google-cloud-pubsub`, `mcp`) are lazy-imported and
degrade to in-process stubs.

```bash
make install-dev   # editable install + dev extras (pytest, ruff, streamlit)
make schemas       # export JSON Schema from the Pydantic contracts -> schemas/contracts/
make test          # contracts, approval gating, self-improvement, stack/toolpacks, importability, slack verify
make lint          # ruff
make smoke         # end-to-end: write-gated Slack task + read-only MCP task, in-process
make run-api       # uvicorn FastAPI ingress (Slack/MCP/API) on localhost
make run-worker    # in-process worker draining the dispatch queue
make run-gui       # Streamlit admin/operator console
```

`make smoke` runs the full ingress → task service → dispatch → worker →
approval-pause → decision → resume → completion loop in a single process, proving
the write-approval gate and the read path without GCP.

### Scaffolded vs. needs development

| Status | Component |
| :--- | :--- |
| **Scaffolded & tested** | Pydantic contracts + JSON Schema export, lifecycle state machine, in-memory repository, in-process dispatch, task service, FastAPI ingress (health/tasks/Slack/MCP/approvals), Slack signature verify, MCP server stub, approval gating with payload-hash binding, LangGraph + Deep Agents orchestration adapter (stub path), model-gateway routing profile, Langfuse observability seam, budget tracker, prompt-to-code sandbox skeleton, tool-pack loader, GUI admin read-model + Streamlit app, self-improvement loop (Option C: inert proposals → evaluate → approve → versioned promotion → rollback). |
| **Needs development** | Real LangGraph + Deep Agents multi-agent orchestration with a Postgres checkpointer, Postgres-backed repository (migrations are provided; the repo layer is in-memory), Pub/Sub wiring at runtime, live LiteLLM-compatible gateway + Cloudflare AI Gateway integration, real SaaS tool adapters, Langfuse/OTLP telemetry wiring, hardened sandbox isolation, real evaluation harness + runtime promotion wiring for the self-improvement loop. See [docs/production-readiness-caveats.md](./docs/production-readiness-caveats.md). |

The POC is **not production-ready**; it is ready for MVP/POC deployment
configuration after local validation. Do not overclaim. See the caveats doc for
the full hardening list.

## Ingress & MCP clients

Slack App ingress (with HITL approvals) and MCP ingress share one requester
identity, task record, and approval ledger. **Claude Desktop** and **Claude Code**
are first-class MCP clients; **Codex**, **OpenCode**, and **Pi** connect later via
the same MCP/tool boundary.

## Layout

| Path | Purpose |
| :--- | :--- |
| `src/agent_mesh/contracts/` | Pydantic v2 task/approval/tool/evidence/AI-BOM/budget models, lifecycle state machine, JSON Schema export. |
| `src/agent_mesh/services/` | Repository, dispatch, sessions, shared task service, approval gating, self-improvement loop (Option C). |
| `src/agent_mesh/api/` | FastAPI ingress (health, tasks, Slack events + signature verify, MCP server, approvals). |
| `src/agent_mesh/worker/` | LangGraph + Deep Agents orchestration adapter, model gateway, task runner with approval pause/resume, budget tracker, worker entrypoint. |
| `src/agent_mesh/observability.py` | Langfuse seam (callback handler, shared trace metadata). |
| `src/agent_mesh/gui/` | Streamlit admin/operator console: pure read-model helpers + the app. |
| `src/agent_mesh/sandbox/` | Prompt-to-code executor skeleton (isolated subprocess, resource limits; production needs hardened isolation). |
| `src/agent_mesh/tools/` | Tool gateway + per-client tool-pack manifest loader. |
| `schemas/` | Exported contract JSON Schema (`contracts/`) and sample read/write tool schemas. |
| `migrations/` | Cloud SQL PostgreSQL + `pgvector` SQL: `0001_init.sql` (tasks, sessions, memory/evidence chunks kept separate, tool calls, approvals, AI-BOM, budget, gateway events) and `0002_self_improvement.sql` (proposals, evaluations, promotions). |
| `config/model_gateway.config.yaml` | LiteLLM-compatible routing/cascades/budgets, routed through the Cloudflare AI Gateway wrapper, with Langfuse + OTel callbacks. |
| `docker/` | Dockerfiles for api / worker / code-executor / gui. |
| `manifests/deployment.manifest.yaml` | Per-environment deployment manifest (stack, tenant, region, model routes, MCP clients, GUI, tool packs, retention). |
| `manifests/tool_pack_manifest.yaml` | Per-client tool pack manifest for replaceable SaaS adapters (Xero, HubSpot, Webflow, Bitscale, Cal.com, Clockify, Beehiiv, Google Workspace) with integration styles. |
| `scripts/gcp_bootstrap.sh` | Idempotent GCP bootstrap (APIs, service accounts, Cloud SQL, Artifact Registry, Secret Manager). |
| `scripts/gcp_deploy_core.sh` | Idempotent deploy of Cloud Run ingress services, jobs, and worker pools. |
| `scripts/cf_deploy_ai_gateway_worker.sh` | Cloudflare `wrangler` deploy for the AI Gateway wrapper worker. |
| `cloudflare/ai-gateway-wrapper/` | Cloudflare Worker wrapping the AI Gateway (`wrangler.toml`, `src/index.ts`). |

Deployment scripts are idempotent and safe to target either a new recommended
environment or an existing GCP project / Cloudflare AI Gateway.
