# ausgtm-agent-mesh

Reusable, governed autonomous agent mesh reference implementation for small
consultancies and client delivery teams, built on AG2 over GCP with Cloudflare
AI Gateway for model-traffic governance.

## Where to start

- **[CLAUDE.md](./CLAUDE.md)** — the normative architectural design pattern:
  reusable platform boundary, task contract, execution plane, memory/evidence
  layer, approval model, and observability approach. This is the operating
  manual for any agent or engineer working in this repo.
- **[docs/language-decision.md](./docs/language-decision.md)** — why the core is
  Python-first with TypeScript only at the edge, with pros/cons and the repo
  layout implication.
- **[RUNBOOK.md](./RUNBOOK.md)** — repeatable deployment runbook: provisioning,
  verification, rollback, and audit checks for a client rollout.
- **[docs/self-improvement-loop.md](./docs/self-improvement-loop.md)** — the
  self-improvement design decision (Option C: approval-gated, self-improving
  agents), AG2 compatibility, safety boundaries, promotion/rollback, and AI-BOM
  implications. **No runtime autonomous self-modification of active instructions
  in the POC.**

## Clone-and-run readiness

This repo ships a **runnable POC scaffold**. The contract layer, shared task
service, ingress, worker, approval gating, and prompt-to-code sandbox are
importable and exercised by tests without any cloud dependencies — heavy deps
(`ag2`, `google-cloud-pubsub`, `mcp`) are lazy-imported and degrade to in-process
stubs.

```bash
make install-dev   # editable install + dev extras (pytest, ruff)
make schemas       # export JSON Schema from the Pydantic contracts -> schemas/contracts/
make test          # 49 tests: contracts, approval gating, self-improvement loop, importability, slack verify
make lint          # ruff
make smoke         # end-to-end: write-gated Slack task + read-only MCP task, in-process
make run-api       # uvicorn FastAPI ingress (Slack/MCP/API) on localhost
make run-worker    # in-process worker draining the dispatch queue
```

`make smoke` runs the full ingress → task service → dispatch → worker →
approval-pause → decision → resume → completion loop in a single process, proving
the write-approval gate and the read path without GCP.

### Scaffolded vs. needs development

| Status | Component |
| :--- | :--- |
| **Scaffolded & tested** | Pydantic contracts + JSON Schema export, lifecycle state machine, in-memory repository, in-process dispatch, task service, FastAPI ingress (health/tasks/Slack/MCP/approvals), Slack signature verify, MCP server stub, approval gating with payload-hash binding, AG2 orchestration stub, budget tracker, prompt-to-code sandbox skeleton, tool-pack loader, self-improvement loop (Option C: inert proposals → evaluate → approve → versioned promotion → rollback). |
| **Needs development** | Real AG2 multi-agent orchestration, Postgres-backed repository (migrations are provided; the repo layer is in-memory), Pub/Sub wiring at runtime, live LiteLLM + Cloudflare AI Gateway integration, real SaaS tool adapters, Langfuse/OTLP telemetry, hardened sandbox isolation, real evaluation harness + runtime promotion wiring for the self-improvement loop. See [docs/production-readiness-caveats.md](./docs/production-readiness-caveats.md). |

The POC is **not production-ready**; do not overclaim. See the caveats doc for the
full hardening list.
- **[docs/production-readiness-caveats.md](./docs/production-readiness-caveats.md)**
  — remaining production hardening requirements (secure sandbox prompt-to-code
  execution, durable orchestration, tenant isolation, immutable approval ledger,
  externalized audit retention, egress controls, credential rotation, CI/CD &
  signed images, evals, kill switches, and more). The POC is not production-ready
  until these are owned and verified. Includes a **Governance Alignment
  Crosswalk** mapping each hardening caveat to the
  [`org-ai-maturity-assessment`](https://github.com/dr-robert-li/org-ai-maturity-assessment/tree/main)
  framework themes and agent/technical security standards.

## Layout

| Path | Purpose |
| :--- | :--- |
| `src/agent_mesh/contracts/` | Pydantic v2 task/approval/tool/evidence/AI-BOM/budget models, lifecycle state machine, JSON Schema export. |
| `src/agent_mesh/services/` | Repository, dispatch, sessions, shared task service, approval gating, self-improvement loop (Option C). |
| `src/agent_mesh/api/` | FastAPI ingress (health, tasks, Slack events + signature verify, MCP server, approvals). |
| `src/agent_mesh/worker/` | AG2 orchestration stub, task runner with approval pause/resume, budget tracker, worker entrypoint. |
| `src/agent_mesh/sandbox/` | Prompt-to-code executor skeleton (isolated subprocess, resource limits; production needs hardened isolation). |
| `src/agent_mesh/tools/` | Tool gateway + per-client tool-pack manifest loader. |
| `schemas/` | Exported contract JSON Schema (`contracts/`) and sample read/write tool schemas. |
| `migrations/` | Cloud SQL PostgreSQL + `pgvector` SQL: `0001_init.sql` (tasks, sessions, memory/evidence chunks kept separate, tool calls, approvals, AI-BOM, budget, gateway events) and `0002_self_improvement.sql` (proposals, evaluations, promotions). |
| `config/litellm.config.yaml` | LiteLLM routing/cascades/budgets, routed through the Cloudflare AI Gateway wrapper. |
| `docker/` | Dockerfiles for api / worker / code-executor. |
| `manifests/deployment.manifest.yaml` | Per-environment deployment manifest (tenant, region, model routes, retention). |
| `manifests/tool_pack_manifest.yaml` | Per-client tool pack manifest for replaceable SaaS adapters. |
| `scripts/gcp_bootstrap.sh` | Idempotent GCP bootstrap (APIs, service accounts, Cloud SQL, Artifact Registry, Secret Manager). |
| `scripts/gcp_deploy_core.sh` | Idempotent deploy of Cloud Run ingress services, jobs, and worker pools. |
| `scripts/cf_deploy_ai_gateway_worker.sh` | Cloudflare `wrangler` deploy for the AI Gateway wrapper worker. |
| `cloudflare/ai-gateway-wrapper/` | Cloudflare Worker wrapping the AI Gateway (`wrangler.toml`, `src/index.ts`). |

Deployment scripts are idempotent and safe to target either a new recommended
environment or an existing GCP project / Cloudflare AI Gateway.
