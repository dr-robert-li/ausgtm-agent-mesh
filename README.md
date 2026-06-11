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
  layer, approval model, observability, acceptance criteria, and the project-board-ready
  roadmap (task import/sync schema). This is the operating manual for any agent or
  engineer working in this repo.
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

This repo is a **locally-validated reference implementation**, not a hollow
scaffold. Across milestone **v1.0** the stubbed components were replaced with real,
test-backed implementations; milestone **v1.1** then made the whole mesh runnable
**fully local and offline** (local inference, local data + telemetry, a one-command
full-stack compose, and a test-asserted no-egress posture) with **zero production
code change**. Everything is exercised creds-free by the default test lane — heavy
deps (`langchain`, `langgraph`, `deepagents`, `langfuse`, `streamlit`,
`google-cloud-pubsub`, `mcp`) are lazy-imported so the creds-free lane stays green,
and a live lane (`make test-live`) opts in real providers when credentials exist.

The repo is **deploy-ready, not production-ready**: ready for MVP/POC deployment
configuration after local validation, with production hardening still owed (see the
caveats doc). Do not overclaim.

```bash
make install-dev   # editable install + dev extras (pytest, ruff, streamlit)
make schemas       # export JSON Schema from the Pydantic contracts -> schemas/contracts/
make test          # default lane (-m "not live"): contracts, approval gating, orchestration,
                   #   self-improvement, gateway/profiles, compose config, offline posture
make test-pg       # adds the Postgres-backed lanes (needs TEST_DATABASE_URL; loud-skips otherwise)
make test-live     # opt-in live lane — real providers/SaaS (needs creds; never in CI)
make lint          # ruff
make smoke         # end-to-end: write-gated Slack task + read-only MCP task, in-process
make run-api       # uvicorn FastAPI ingress (Slack/MCP/API) on localhost
make run-worker    # worker draining the dispatch queue
make run-gui       # Streamlit admin/operator console
```

`make smoke` runs the full ingress → task service → dispatch → worker →
approval-pause → decision → resume → completion loop in a single process, proving
the write-approval gate and the read path without GCP.

### Run it fully local & offline (v1.1)

Run the entire mesh on your machine with **no cloud-hosted LLM egress** — local
inference behind the same LiteLLM seam, local Postgres(pgvector) + self-hosted
Langfuse, and a no-egress posture that tests enforce. Deployment names
(`low/medium/high-complexity`) stay constant, so agent and gateway code are
untouched. Full operator detail in [RUNBOOK.md](./RUNBOOK.md).

```bash
# Local inference (pick a backend), then swap the active model-gateway profile to it
make run-vllm   ;  make use-vllm      # GPU box: vLLM on :8000
make run-ollama ;  make use-ollama    # CPU box: Ollama on :11434
make use-cloud                        # swap back to the cloud profile

make run-pg        # local Postgres(pgvector) for the durable + telemetry lane
make compose-up    # one-command full stack: api + worker + gui + pgvector + Langfuse + local model backend
make compose-down

cp .env.offline.example .env          # offline posture: cloud-LLM/gateway creds blank, SaaS creds normal
```

The offline posture is **asserted, not hoped**: `make test` fails if any local
model profile, the assembled compose stack, or the default creds-free lane could
reach a cloud LLM provider or model gateway. "Offline" here means **no cloud-hosted
LLM inference** (Vertex / Anthropic-direct / the Cloudflare AI Gateway model path);
local Postgres, Langfuse, in-stack service-DNS backends, and SaaS tool adapters
reaching their own APIs remain legitimate.

### What's implemented

| Status | Component |
| :--- | :--- |
| **Implemented & locally validated (v1.0)** | Postgres-backed repository over `0001`–`0004` migrations with tenant-scoped reads; runtime dispatch with in-process fallback; authenticated / replay-proof approval gate (signed token + payload-hash binding); real LangGraph supervisor delegating to a bounded Deep Agents roster (planner, researcher/tool-router, code-writer, reviewer) with a durable Postgres checkpointer and interrupt-based HITL pause/resume; a real LiteLLM-compatible gateway (routing/cascades/budgets) with Cloudflare AI Gateway as the upstream chokepoint and Langfuse telemetry + prompt/eval management (real-provider lanes are opt-in via `make test-live`; the default lane is creds-free); Tool Gateway framework (execution-time credential resolution, JSON-Schema in/out validation, tool-event OTel spans) with HubSpot + Google Workspace direct adapters, Composio + Nango aggregators, and Webflow/Bitscale/Cal.com/Clockify/Beehiiv/Xero reference adapters; self-improvement loop (Option C: real held-out eval harness → inert proposal → human approval → versioned non-hot promotion → rollback) with CycloneDX ML-BOM; full E2E proofs + idempotent deploy-script validation. |
| **Local & offline (v1.1)** | vLLM + Ollama local-inference profiles behind the LiteLLM seam (`make run-vllm`/`run-ollama`, `use-*` profile swap); documented local Postgres(pgvector) + self-hosted Langfuse run path (`make run-pg`, migration-on-local-DSN test); one-command full-stack `docker-compose.yml` (`make compose-up/down`) with compose-config validation; offline / no-egress posture — `.env.offline.example` + RUNBOOK + tests asserting no cloud `api_base`/key across all local profiles + the compose stack, and a connect-level deny-guard proving the default lane makes no cloud-LLM call. All of v1.1 is config / compose / docs / tests only — **zero `src/` change** (a durable test enforces it). |
| **Remaining for production** | Live cloud provisioning (GCP) and FinOps review; Cloud SQL HA; immutable/externalized approval + audit ledger; broader egress controls and short-lived/rotated credentials; signed images + dependency scanning in CI; kill switches / incident response; memory-retrieval governance and data-deletion policy; self-improvement loop runtime hardening. See [docs/production-readiness-caveats.md](./docs/production-readiness-caveats.md) for the full 15-item list. |

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
| `src/agent_mesh/sandbox/` | Prompt-to-code executor (isolated subprocess, resource limits; production needs stronger isolation — caveat #1). |
| `src/agent_mesh/tools/` | Tool gateway + per-client tool-pack manifest loader. |
| `schemas/` | Exported contract JSON Schema (`contracts/`) and sample read/write tool schemas. |
| `migrations/` | Cloud SQL PostgreSQL + `pgvector` SQL: `0001_init.sql` (tasks, sessions, memory/evidence chunks kept separate, tool calls, approvals, AI-BOM, budget, gateway events), `0002_self_improvement.sql` (proposals, evaluations, promotions), `0003_tool_call_fields.sql`, and `0004_active_version.sql` (active-version pointer). |
| `config/model_gateway.*.yaml` | LiteLLM-compatible routing/cascades/budgets through the Cloudflare AI Gateway wrapper, with Langfuse + OTel callbacks. `config.yaml` is the active (mutable) profile; `cloud.yaml` the pristine cloud reference; `vllm.yaml`/`ollama.yaml` (loopback) and `vllm.compose.yaml`/`cpu.compose.yaml` (in-stack service-DNS) are the local-inference profiles selected via `make use-vllm`/`use-ollama`/`use-cloud`. |
| `docker-compose.yml` / `.env.offline.example` | One-command full-stack local bring-up (`make compose-up/down`) and the offline / no-egress posture template (cloud-LLM creds blank, SaaS creds normal). |
| `tests/` | Creds-free default lane (`-m "not live"`) + opt-in `-m live` lane; includes the offline-posture, deny-guard, compose-config, and durable zero-`src/` invariant suites. |
| `docker/` | Dockerfiles for api / worker / code-executor / gui. |
| `manifests/deployment.manifest.yaml` | Per-environment deployment manifest (stack, tenant, region, model routes, MCP clients, GUI, tool packs, retention). |
| `manifests/tool_pack_manifest.yaml` | Per-client tool pack manifest for replaceable SaaS adapters (Xero, HubSpot, Webflow, Bitscale, Cal.com, Clockify, Beehiiv, Google Workspace) with integration styles. |
| `scripts/gcp_bootstrap.sh` | Idempotent GCP bootstrap (APIs, service accounts, Cloud SQL, Artifact Registry, Secret Manager). |
| `scripts/gcp_deploy_core.sh` | Idempotent deploy of Cloud Run ingress services, jobs, and worker pools. |
| `scripts/cf_deploy_ai_gateway_worker.sh` | Cloudflare `wrangler` deploy for the AI Gateway wrapper worker. |
| `cloudflare/ai-gateway-wrapper/` | Cloudflare Worker wrapping the AI Gateway (`wrangler.toml`, `src/index.ts`). |

Deployment scripts are idempotent and safe to target either a new recommended
environment or an existing GCP project / Cloudflare AI Gateway.
