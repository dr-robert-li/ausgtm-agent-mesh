# ausgtm-agent-mesh

Reusable, governed autonomous agent mesh reference implementation for small
consultancies and client delivery teams, built on AG2 over GCP with Cloudflare
AI Gateway for model-traffic governance.

## Where to start

- **[CLAUDE.md](./CLAUDE.md)** — the normative architectural design pattern:
  reusable platform boundary, task contract, execution plane, memory/evidence
  layer, approval model, and observability approach. This is the operating
  manual for any agent or engineer working in this repo.
- **[RUNBOOK.md](./RUNBOOK.md)** — repeatable deployment runbook: provisioning,
  verification, rollback, and audit checks for a client rollout.
- **[docs/production-readiness-caveats.md](./docs/production-readiness-caveats.md)**
  — remaining production hardening requirements (secure sandbox prompt-to-code
  execution, durable orchestration, tenant isolation, immutable approval ledger,
  externalized audit retention, egress controls, credential rotation, CI/CD &
  signed images, evals, kill switches, and more). The POC is not production-ready
  until these are owned and verified.

## Layout

| Path | Purpose |
| :--- | :--- |
| `manifests/deployment.manifest.yaml` | Per-environment deployment manifest (tenant, region, model routes, retention). |
| `manifests/tool_pack_manifest.yaml` | Per-client tool pack manifest for replaceable SaaS adapters. |
| `scripts/gcp_bootstrap.sh` | Idempotent GCP bootstrap (APIs, service accounts, Cloud SQL, Artifact Registry, Secret Manager). |
| `scripts/gcp_deploy_core.sh` | Idempotent deploy of Cloud Run ingress services, jobs, and worker pools. |
| `scripts/cf_deploy_ai_gateway_worker.sh` | Cloudflare `wrangler` deploy for the AI Gateway wrapper worker. |
| `cloudflare/ai-gateway-wrapper/` | Cloudflare Worker wrapping the AI Gateway (`wrangler.toml`, `src/index.ts`). |

Deployment scripts are idempotent and safe to target either a new recommended
environment or an existing GCP project / Cloudflare AI Gateway.
