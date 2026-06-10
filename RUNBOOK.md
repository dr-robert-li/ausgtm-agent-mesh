# Runbook: Repeatable Autonomous Agent Mesh Deployment

## Purpose

This runbook describes how to redeploy the reusable autonomous agent mesh pattern for a new client or environment. The core architecture remains stable; the deployment manifest, tool pack manifest, secrets, SaaS resource IDs, model route profile, and approval settings change per deployment.

The deployment process is intentionally idempotent. It can target a clean new project/gateway, which is recommended for isolation, or an existing GCP project and existing Cloudflare AI Gateway, provided the operator confirms that shared resources, quotas, logs, and DLP policies are acceptable for the client/environment.

## Deployment Inputs

- `manifests/deployment.manifest.yaml`
- `manifests/tool_pack_manifest.yaml`
- GCP project with billing enabled
- Cloudflare account with AI Gateway, Zero Trust, and Wrangler access
- Slack app credentials
- MCP hostname and auth configuration
- SaaS credentials for the selected tool pack
- Model provider credentials or Cloudflare unified model billing configuration

## Operator Prerequisites

Install and authenticate:

```bash
gcloud auth login
gcloud auth application-default login
wrangler login
```

Set baseline environment variables:

```bash
export PROJECT_ID="REPLACE_WITH_GCP_PROJECT_ID"
export REGION="australia-southeast1"
export CLOUDFLARE_ACCOUNT_ID="REPLACE_WITH_CLOUDFLARE_ACCOUNT_ID"
export CLOUDFLARE_AI_GATEWAY_ID="agent-mesh-poc"
export CREATE_PROJECT="false"
export REUSE_EXISTING_CLOUDFLARE_GATEWAY="true"
```

## Local Smoke Checks (before cloud provisioning)

The POC scaffold runs end-to-end in a single process with no GCP, Cloudflare, or
SaaS dependencies. Run these first to confirm the contract, ingress, worker, and
approval gate are healthy before provisioning anything.

```bash
make install-dev   # editable install + dev extras (pytest, ruff, streamlit)
make schemas       # export contract JSON Schemas -> schemas/contracts/
make lint          # ruff
make test          # contracts, approval gating, self-improvement, stack/toolpacks, importability, slack verify
make smoke         # full ingress -> service -> dispatch -> worker -> approval -> resume loop
```

Expected: `make test` reports all tests passing, and `make smoke` prints `SMOKE OK`
after exercising a write-gated Slack task (pauses for approval, approved,
completed) and a read-only MCP task (completes without approval).

To exercise the HTTP ingress and admin console locally:

```bash
make run-api       # uvicorn FastAPI on localhost; GET /healthz, POST /v1/tasks, /slack/events, /v1/approvals
make run-worker    # in a second shell: in-process worker draining the dispatch queue
make run-gui       # Streamlit admin/operator console
```

Heavy deps (`langchain`, `langgraph`, `deepagents`, `langfuse`, `streamlit`,
`google-cloud-pubsub`, `mcp`) are optional; without them the package still imports
and the in-process dispatcher/worker run. Install the `runtime`, `agents`, and
`gui` extras for the full stack before building images.

### Postgres durable checkpointer lane (deploy-readiness)

The default lane proves the durable restart-resume (E2E-02 / SC-2) against a file-backed
SQLite checkpointer, so `make test` stays creds- and DB-free. The REAL `PostgresSaver`
restart-resume — routed through the production `orchestrator._select_checkpointer()` /
`close_checkpointer()` lifecycle — is **DSN-gated** and **skipped by default**: the `pg_dsn`
fixture loud-skips every Postgres test when `TEST_DATABASE_URL` is unset, so it never
silently passes and never hard-fails on a machine with no Postgres.

Deploy-readiness validation **MUST** run this lane against a real Postgres. Point
`TEST_DATABASE_URL` at a **pgvector-enabled** Postgres (e.g. a `pgvector/pgvector:pg16`
container via testcontainers or Docker-Compose — a vanilla `postgres` image will fail the
`CREATE EXTENSION vector` migration), then:

```bash
export TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/agent_mesh_test
make test-pg       # DSN-gated durable/Postgres checkpointer lane; loud-skips when unset
```

`make test-pg` covers `tests/e2e/test_e2e_mcp_durable_job_live.py` and
`tests/test_checkpointer_resume.py`. With no DSN exported it exits 0 with every Postgres
test loud-skipped (so the gap is never silent); with a DSN set it exercises the production
PostgresSaver construction + cache + close lifecycle end to end.

## Local inference lane

The mesh can run inference fully on-box behind the **existing** LiteLLM Router — no
agent or gateway code changes. Two backends are supported: **vLLM** (GPU) and **Ollama**
(CPU/dev). Selecting a backend is a reversible config file-swap; running it is a
best-effort operator step.

### Running a backend

```bash
make run-vllm      # GPU lane: vllm serve Qwen/Qwen2.5-7B-Instruct --port 8000 \
                   #   --enable-auto-tool-choice --tool-call-parser hermes
make run-ollama    # CPU/dev lane: ollama pull qwen2.5:7b-instruct && ollama serve
```

Both targets are **best-effort and operator-only** — they are deliberately never wired
into `make test` or any CI path. `make run-vllm` will fail on a box without a GPU (or
without vLLM installed); `make run-ollama` will fail on a box without Ollama installed.
That is acceptable: pick whichever backend your box supports. Override the served model
with `make run-vllm VLLM_MODEL=…` / `make run-ollama OLLAMA_MODEL=…` (and adjust the tag
to one `ollama list` knows — see the model-id note below). A recent vLLM (≥ 0.6 line) is
needed for the tool-call parsers.

### Selecting a profile (file-swap)

`build_router` reads a hardcoded `DEFAULT_CONFIG_PATH = config/model_gateway.config.yaml`;
there is **no env-driven config-path seam** (adding one would be a `src/` change, which
this milestone forbids). So profile selection is a `cp`-based file-swap, managed by `make`
and reversible:

```bash
make use-vllm      # cp config/model_gateway.vllm.yaml  -> config/model_gateway.config.yaml
make use-ollama    # cp config/model_gateway.ollama.yaml -> config/model_gateway.config.yaml
make use-cloud     # cp config/model_gateway.cloud.yaml  -> config/model_gateway.config.yaml (restore)
```

**Honest git-dirty disclosure:** activating a local profile overwrites the tracked
`config/model_gateway.config.yaml`, so `git status` will show it as **modified** for as
long as a local profile is active. This is inherent to the file-swap approach (not a bug),
and is fully reversible: `make use-cloud` restores the pristine cloud profile and the file
goes clean again. Run `make use-cloud` before committing unrelated work so you don't sweep
a local profile into a commit.

While a local profile is active, `make test` will also fail `tests/test_d06_chokepoint.py`:
that guard asserts the **active** config egresses through the Cloudflare wrapper, which the
loopback local profiles deliberately do not. This is expected, not a regression — run
`make use-cloud` to restore the cloud profile before running the full suite. (The
`tests/test_local_profiles.py` guard, by contrast, reads the local profiles by path and
passes in either state.)

### Tool-calling model-capability caveat

The mesh delegates work via **tool-calls**, so tool-calling quality — not transport — is
the real local constraint. Local instruct models are weaker at tool-calling than frontier
cloud models, and the served model must be a tool-call-capable instruct model.

vLLM additionally **requires** the right parser flags or `tool_calls` come back empty:

- `--enable-auto-tool-choice --tool-call-parser hermes` for **Qwen2.5** (the default).
- `--enable-auto-tool-choice --tool-call-parser llama3_json` for **Llama-3.1**.

The parser is model-family-specific — **do not cross them** (`hermes` on a Llama model, or
vice versa, yields empty/garbled tool calls). `make run-vllm` bakes the `hermes` pair in
for the default Qwen2.5 model; if you change `VLLM_MODEL` to a Llama-3.1 model, run vLLM by
hand with `--tool-call-parser llama3_json` (and pass the matching
`tool_chat_template_llama3.1_json.jinja` chat template if your vLLM build does not
auto-select it). Ollama does its own native tool-calling per model capability and needs no
parser flag.

### api_base path gotcha

The two backends differ in their api_base path, and getting this wrong is a runtime-only
404 that the LOCAL-04 config test cannot catch (an offline `build_router` succeeds with any
api_base string):

- **vLLM** api_base **ends in `/v1`**: `http://localhost:8000/v1`. LiteLLM's `hosted_vllm`
  transport appends only `chat/completions`, so without the `/v1` suffix the request lands
  on `/chat/completions` and the vLLM server 404s.
- **Ollama** api_base has **no `/v1`**: `http://localhost:11434`. The `ollama_chat/` prefix
  targets the native `/api/chat` endpoint directly.

These are baked into the shipped profiles; only re-derive them if you point at a
non-default host/port.

> Fully-offline cold box: if litellm tries to fetch its model-cost map at import (a cost
> lookup, not routing), set `LITELLM_LOCAL_MODEL_COST_MAP=True` to force the bundled map.
> Not needed for the config test or for routing.

## Local data & telemetry plane

Run the durable persistence + observability plane fully on-box for local dev:
local Postgres(pgvector) in place of Cloud SQL, and self-hosted Langfuse in place
of cloud Langfuse. As with the inference lane, the run-targets are best-effort
operator steps and the pinned `.env.example` DSNs are **dev-only** local creds —
copy `.env.example` to an untracked `.env` and replace them for any real
deployment (prod secrets come from Secret Manager).

### Local Postgres run path

`make run-pg` starts a single local **pgvector** Postgres. It is **best-effort and
operator-only** — deliberately never wired into `make test` or any CI path. It
requires Docker and will fail on a box without it; that is acceptable, exactly like
`make run-vllm` without a GPU.

The image is pinned to `pgvector/pgvector:pg16`: a vanilla `postgres` image fails
the `CREATE EXTENSION vector` migration (0001) — `IF NOT EXISTS` does not install
the extension. The container uses a persistent `-d` + named volume so data
survives restarts and `make test-pg` can re-run against it.

Copy-paste operator block (creds/port/db match the pinned `.env.example` DSN):

```bash
make run-pg                                   # single local pgvector Postgres (best-effort, operator-only)
export TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/agent_mesh
make test-pg                                  # DSN-gated durable lane; loud-skips when unset
# teardown: docker rm -f agent_mesh_pg   (optional: docker volume rm agent_mesh_pgdata)
```

`make test-pg` applies migrations 0001->0004 via the `pg_dsn` fixture and runs the
durable/Postgres lane, including `tests/test_local_data_plane.py` which asserts the
0003 `tool_calls` columns and the 0004 tables exist in the live migrated schema.
With no DSN exported it exits 0 with every Postgres test loud-skipped.

### Self-hosted Langfuse (now standable via the full-stack compose)

The full multi-container Langfuse standup is **now part of Phase 10's single
`docker-compose.yml`** — see [Full-stack local compose](#full-stack-local-compose)
below, which brings up the Langfuse v3 set under the `langfuse` profile alongside
the mesh. The upstream-clone path below remains documented as a standalone
reference (Langfuse-only, no mesh).

Upstream standalone self-host path *(datable — re-verify against upstream)*:

```bash
git clone https://github.com/langfuse/langfuse.git
cd langfuse && docker compose up        # UI at http://localhost:3000
```

The Langfuse **v3** stack is multi-container (web + worker + postgres + clickhouse +
redis/valkey + minio) — this is why a single `make` target was deferred to the
full-stack compose, which now carries it inline as a profile-gated service set.

**Client-vs-server key boundary (do not conflate):** the mesh's
`LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` are **UI-generated per-project** keys
the operator creates *after first boot* and exports into their untracked `.env` —
they are **NOT** Langfuse server env vars, which is why they are left blank in
`.env.example`. The Langfuse **server**-side secrets (`NEXTAUTH_SECRET`, `SALT`,
`ENCRYPTION_KEY`, the server's own `DATABASE_URL`, and the ClickHouse/Redis/S3
creds) live in the upstream compose `# CHANGEME` lines and are **Phase 10
territory**. `LANGFUSE_HOST` is pinned to `http://localhost:3000` in `.env.example`
for this self-host path. Mesh telemetry **loud-skips** when the keys are unset
(existing behavior — no `src/` change), so the default lane stays green without a
running Langfuse.

## Full-stack local compose

Brings the **whole mesh up as one local stack** — `api` + `worker` + `gui` +
`postgres` + a one-shot `migrate` + a model backend + the full self-hosted Langfuse
v3 plane — from a single `docker-compose.yml` (COMPOSE-01/02). Like the inference and
data-plane run-targets above, `make compose-up` / `compose-down` are **best-effort,
operator-run, and DELIBERATELY never wired into `make test` or any CI path**: they
require Docker and may fail on a bare box (no Docker, or no GPU for the default vLLM
profile), which is acceptable. The lone CI-wired Phase-10 piece is the static
`tests/test_compose_config.py` (`docker compose config` parse — runs under `make
test`, loud-skips when the `docker` binary is absent).

### One-command bring-up

```bash
make compose-up                          # default: vLLM model backend (needs a GPU) + Langfuse
MODEL_PROFILE=cpu make compose-up        # non-GPU boxes: Ollama (CPU) instead of vLLM
make compose-down                        # tear down all profiles (vllm cpu langfuse); data survives (no -v)
```

`compose-up` runs `docker compose --profile $(MODEL_PROFILE) --profile langfuse up -d
--build` (`MODEL_PROFILE ?= vllm`). `compose-down` runs the **enumerated** teardown
`docker compose --profile vllm --profile cpu --profile langfuse down` so it cleans up
deterministically regardless of which profile brought the stack up. A raw `docker
compose up` (no `--profile`) stays **lean** — core services only, no model backend or
Langfuse.

### Dev-only disclosures (read before relying on the stack)

These are honest dev-only postures, exactly like the pinned `.env.example` DSNs above
— **never a production posture**:

- **The worker's docker-socket mount is DEV-ONLY.** The `worker` service binds
  `/var/run/docker.sock` so the real Phase-2 DooD sandbox runs in-stack (the worker
  shells out to the host `docker` daemon to launch the code-execution sandbox). This
  grants the worker **effective host-root** and is **NEVER** a production posture —
  production runs the sandbox as isolated Cloud Run Jobs, not over a mounted host
  socket. The `MESH_SBX_DIR` (default `/tmp/agent-mesh-sbx`, identical-path host bind)
  and `DOCKER_GID` (default `999`, the host socket gid) knobs are host-dependent
  dev-only overrides — set them in your untracked `.env` if your host differs (e.g.
  Docker Desktop on macOS vs Linux).
- **Langfuse keys are UI-minted, not env-provided.** On first bring-up
  `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` are **blank**, so mesh tracing
  **loud-skips** (existing behavior — no `src/` change). To enable tracing, open the
  Langfuse UI at <http://localhost:3000>, create a project, **mint** a key pair, and
  set `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` in your untracked `.env`, then
  recreate the api/worker (`make compose-up` again). These are the same UI-generated
  per-project keys described in the client-vs-server key boundary note above — they
  are **NOT** Langfuse server env vars.
- **vLLM is the default and needs a GPU.** The `vllm` profile reserves an NVIDIA GPU;
  on a non-GPU box use `MODEL_PROFILE=cpu make compose-up` to run **Ollama** (CPU)
  instead. A wrong/unavailable model image tag fails at pull time, not at config time.
- **LiteLLM runs EMBEDDED in api/worker — there is no litellm proxy container.** The
  in-process `litellm.Router` inside the api/worker IS the model control plane, which
  mirrors the deploy topology (no standalone litellm image). `tests/test_compose_config.py`
  asserts **no `litellm` service** is present, by design.
- **Langfuse server `# CHANGEME` secrets are local-only dev defaults.** The inline
  `NEXTAUTH_SECRET` / `SALT` / `ENCRYPTION_KEY` and the ClickHouse / Redis / MinIO
  credentials in the `langfuse` profile are dev-only placeholders (each marked
  `# CHANGEME` in `docker-compose.yml`). **Replace every one for any non-local use.**
  Langfuse uses its OWN postgres (`langfuse-postgres`, distinct volume) — the mesh DSN
  points only at the pgvector `postgres`, never at Langfuse's store.

### Volume wipe (data loss)

`compose-down` does **not** pass `-v`, so the named volumes (`mesh_pgdata`,
`langfuse_pgdata`, `clickhouse_data`, `minio_data`, `ollama_data`) survive a teardown.
To wipe all stack data (a clean slate — **irreversible data loss**), run the teardown
with `-v` explicitly:

```bash
docker compose --profile vllm --profile cpu --profile langfuse down -v
```

### Verify migrations applied (non-static runtime proof)

The static `docker compose config` test cannot prove the schema is actually applied
at runtime — only that the `migrate` service is *declared*. After `make compose-up`,
the one-shot `migrate` service applies migrations `0001`–`0004` (gated so api/worker/gui
wait for it via `service_completed_successfully`). Confirm the schema is live before
relying on any durable call:

```bash
docker compose exec postgres psql -U postgres -d agent_mesh -c '\dt'
```

The migration-created tables (tasks, sessions, tool_calls, the self-improvement and
active-version objects, …) should be listed. If they are absent, inspect the `migrate`
service logs (`docker compose logs migrate`) before proceeding.

## Credentials & live lane

The default smoke/test lane above is **creds-free** — it never touches a real SaaS
provider. To exercise a provider for real (the opt-in **live lane**), supply that
provider's credential env var(s). Each provider is independently skippable: leave a
provider's creds unset and only its live tests skip (D-11). The single discoverable
per-provider credential/scope setup index — which env vars to set, what they govern,
where to mint them, and the exact scopes — is:

- [`docs/credentials/README.md`](./docs/credentials/README.md) — the credential index
  + per-provider opt-in live-lane matrix, linking the per-provider setup docs for
  HubSpot, Google Workspace (all six products), Composio, and Nango.

Run the live lane with `pytest -m live`; providers whose creds are absent skip cleanly.

## Deployment Sequence

### Prepare manifests

1. Copy `manifests/deployment.manifest.yaml` for the client/environment.
2. Set `client_slug`, `tenant_id`, `project_id`, `region`, budget values, Cloudflare gateway ID, and model route profile.
3. Copy `manifests/tool_pack_manifest.yaml` for the client/environment.
4. Replace all SaaS resource IDs, board IDs, folder IDs, workspace IDs, and credential secret names.
5. Commit the manifests to the implementation repository or controlled deployment bundle.

### Bootstrap GCP

The recommended approach is a new GCP project per client/environment. If you use an existing project, the bootstrap script will reuse it, enable missing APIs, create missing service accounts/topics/SQL resources, and grant required IAM roles.

Run:

```bash
PROJECT_ID="$PROJECT_ID" REGION="$REGION" ./scripts/gcp_bootstrap.sh
```

To create a new project from the script, run:

```bash
CREATE_PROJECT=true \
BILLING_ACCOUNT_ID="REPLACE_WITH_BILLING_ACCOUNT_ID" \
PROJECT_ID="$PROJECT_ID" \
REGION="$REGION" \
./scripts/gcp_bootstrap.sh
```

Verify:

```bash
gcloud services list --enabled
gcloud sql instances describe agent-mesh-poc
gcloud pubsub topics list
gcloud artifacts repositories list --location="$REGION"
```

### Load secrets

Create secrets before deploying services:

```bash
gcloud secrets create SLACK_SIGNING_SECRET --replication-policy=automatic
gcloud secrets create SLACK_BOT_TOKEN --replication-policy=automatic
gcloud secrets create MODEL_GATEWAY_MASTER_KEY --replication-policy=automatic
gcloud secrets create ANTHROPIC_API_KEY --replication-policy=automatic
gcloud secrets create LANGFUSE_PUBLIC_KEY --replication-policy=automatic
gcloud secrets create LANGFUSE_SECRET_KEY --replication-policy=automatic
```

Add provider and SaaS secrets matching `tool_pack_manifest.yaml`.

### Deploy Cloudflare AI Gateway wrapper

The recommended approach is a dedicated Cloudflare AI Gateway per client/environment. If an existing Cloudflare AI Gateway is already in use, set `CLOUDFLARE_AI_GATEWAY_ID` to that gateway ID and keep `REUSE_EXISTING_CLOUDFLARE_GATEWAY=true`.

Update `cloudflare/ai-gateway-wrapper/wrangler.toml` with the correct account and gateway values.

Run:

```bash
CLOUDFLARE_ACCOUNT_ID="$CLOUDFLARE_ACCOUNT_ID" \
CLOUDFLARE_AI_GATEWAY_ID="$CLOUDFLARE_AI_GATEWAY_ID" \
REUSE_EXISTING_CLOUDFLARE_GATEWAY="$REUSE_EXISTING_CLOUDFLARE_GATEWAY" \
./scripts/cf_deploy_ai_gateway_worker.sh
```

Set Worker secrets:

```bash
cd cloudflare/ai-gateway-wrapper
wrangler secret put CF_AIG_AUTH_TOKEN --env poc
wrangler secret put MODEL_GATEWAY_SHARED_SECRET --env poc
```

Configure Cloudflare:

1. Enable authenticated AI Gateway.
2. Enable logging.
3. Set `cf-aig-collect-log-payload` default posture for the deployment.
4. Configure Guardrails for prompt and response evaluation.
5. Configure Zero Trust DLP profiles and HTTP policies for query blocking.
6. Configure Logpush or external export if 12-month retention exceeds gateway storage limits.

If reusing an existing gateway, verify:

1. Existing DLP profiles match this deployment’s risk posture.
2. Existing guardrails are appropriate for the client/environment.
3. Gateway log storage limits and automatic deletion settings will not conflict with 12-month audit requirements.
4. Request metadata includes tenant/client/task IDs so logs can be filtered by deployment.
5. Existing rate limits and cache settings will not affect model routing unexpectedly.

### Deploy GCP services and jobs

After images are built and pushed:

```bash
PROJECT_ID="$PROJECT_ID" REGION="$REGION" IMAGE_TAG="latest" ./scripts/gcp_deploy_core.sh
```

Verify:

```bash
gcloud run services list --region="$REGION"
gcloud run jobs list --region="$REGION"
```

### Configure model gateway routing

Configure the LiteLLM-compatible model gateway so upstream model calls (Anthropic direct + Vertex AI) route through the Cloudflare AI Gateway wrapper. Required metadata headers should include:

- `x-agent-mesh-tenant-id`
- `x-agent-mesh-client-slug`
- `x-agent-mesh-task-id`
- `x-agent-mesh-session-id`
- `x-agent-mesh-requester-id`
- `x-agent-mesh-entrypoint`
- `x-agent-mesh-agent-role`
- `x-agent-mesh-model-route-profile`

### Verify end-to-end

Run the following checks:

1. Slack ingress creates a task and returns an acknowledgement quickly.
2. MCP ingress creates a task with the same task contract.
3. Long-running worker job picks up the task and persists state.
4. Model gateway call routes through Cloudflare AI Gateway.
5. Cloudflare AI Gateway logs token usage, model, provider, status, cost, and duration.
6. DLP test prompt triggers the expected Cloudflare action.
7. Write action pauses for approval.
8. Approval decision is recorded in `approval_records`.
9. Evidence chunks and memory chunks are written to separate tables.
10. AI-BOM snapshot includes deployment manifest and tool pack manifest.

## Rollback

1. Revert Cloud Run service revisions:

```bash
gcloud run services update-traffic agent-mesh-api --region="$REGION" --to-revisions=PREVIOUS_REVISION=100
```

2. Revert Worker deployment:

```bash
cd cloudflare/ai-gateway-wrapper
wrangler rollback --env poc
```

3. Disable newly added tool pack entries by updating the manifest and redeploying config.
4. Rotate any exposed secrets in Secret Manager and Cloudflare.

## Redeployment Checklist

- [ ] Deployment manifest copied and updated.
- [ ] Tool pack manifest copied and updated.
- [ ] GCP project selected.
- [ ] If using existing GCP project, resource sharing, IAM, quotas, logs, and naming collisions reviewed.
- [ ] If creating new GCP project, `CREATE_PROJECT=true` and billing account confirmed.
- [ ] APIs enabled.
- [ ] Cloud SQL non-HA instance created in Sydney.
- [ ] Secrets loaded.
- [ ] Cloudflare AI Gateway created/configured.
- [ ] If using existing Cloudflare AI Gateway, DLP, guardrails, log storage, rate limits, and metadata filters reviewed.
- [ ] Wrangler worker deployed.
- [ ] Model gateway route profile points to Cloudflare wrapper/gateway.
- [ ] Cloud Run ingress deployed.
- [ ] Cloud Run jobs deployed.
- [ ] Slack test passed.
- [ ] MCP test passed.
- [ ] DLP/query-blocking test passed.
- [ ] Write approval test passed.
- [ ] Long-running worker test passed.
- [ ] Cost and model budget telemetry visible.
- [ ] AI-BOM generated.
