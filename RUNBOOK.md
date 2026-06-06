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
