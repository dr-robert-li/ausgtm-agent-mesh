#!/usr/bin/env bash
set -euo pipefail

# Deploy reusable Cloud Run services/jobs once container images exist.
# Idempotent: `run deploy` and the jobs create/update branches can be re-run.
# Usage:
#   PROJECT_ID=my-project REGION=australia-southeast1 IMAGE_TAG=... ./scripts/gcp_deploy_core.sh

: "${PROJECT_ID:?Set PROJECT_ID}"
: "${REGION:=australia-southeast1}"
: "${AR_REPO:=agent-mesh}"
: "${IMAGE_TAG:=latest}"
: "${TENANT_ID:=tenant-example}"
: "${CLIENT_SLUG:=example-client}"
: "${MODEL_ROUTE_PROFILE:=mixed-cascade}"
: "${API_IMAGE:=${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/agent-mesh-api:${IMAGE_TAG}}"
: "${WORKER_IMAGE:=${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/agent-mesh-worker:${IMAGE_TAG}}"
: "${CODE_IMAGE:=${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/agent-mesh-code-executor:${IMAGE_TAG}}"
: "${SQL_INSTANCE:=agent-mesh-poc}"

gcloud config set project "${PROJECT_ID}"

# Cloud SQL connection name for the Cloud SQL connector (--add-cloudsql-instances).
SQL_CONNECTION_NAME="$(gcloud sql instances describe "${SQL_INSTANCE}" \
  --format='value(connectionName)' 2>/dev/null || echo "")"

COMMON_ENV="REGION=${REGION},TENANT_ID=${TENANT_ID},CLIENT_SLUG=${CLIENT_SLUG}"
COMMON_ENV="${COMMON_ENV},MODEL_ROUTE_PROFILE=${MODEL_ROUTE_PROFILE}"
COMMON_ENV="${COMMON_ENV},USE_PUBSUB=true,PROJECT_ID=${PROJECT_ID}"
COMMON_ENV="${COMMON_ENV},TASK_TOPIC=agent-mesh-tasks,APPROVAL_TOPIC=agent-mesh-approvals,DLQ_TOPIC=agent-mesh-dlq"

# Secrets are resolved at runtime from Secret Manager via --set-secrets. The
# secret names below must exist (created in the bootstrap/secrets step). Values
# are never baked into images or env. Add provider/SaaS secrets as needed.
COMMON_SECRETS="SLACK_SIGNING_SECRET=SLACK_SIGNING_SECRET:latest"
COMMON_SECRETS="${COMMON_SECRETS},SLACK_BOT_TOKEN=SLACK_BOT_TOKEN:latest"
COMMON_SECRETS="${COMMON_SECRETS},MODEL_GATEWAY_MASTER_KEY=MODEL_GATEWAY_MASTER_KEY:latest"
COMMON_SECRETS="${COMMON_SECRETS},MODEL_GATEWAY_SHARED_SECRET=MODEL_GATEWAY_SHARED_SECRET:latest"
COMMON_SECRETS="${COMMON_SECRETS},LANGFUSE_PUBLIC_KEY=LANGFUSE_PUBLIC_KEY:latest"
COMMON_SECRETS="${COMMON_SECRETS},LANGFUSE_SECRET_KEY=LANGFUSE_SECRET_KEY:latest"
# DATABASE_URL is expected to be stored as a secret pointing at the Cloud SQL DB
# (via the connector socket). Create it before deploy; comment out for in-memory POC.
COMMON_SECRETS="${COMMON_SECRETS},DATABASE_URL=DATABASE_URL:latest"

CLOUDSQL_FLAG=()
if [[ -n "${SQL_CONNECTION_NAME}" ]]; then
  CLOUDSQL_FLAG=(--add-cloudsql-instances="${SQL_CONNECTION_NAME}")
fi

deploy_service() {
  local name="$1"; shift
  local extra_env="$1"; shift
  gcloud run deploy "${name}" \
    --image="${API_IMAGE}" \
    --region="${REGION}" \
    --service-account="agent-mesh-api@${PROJECT_ID}.iam.gserviceaccount.com" \
    --no-allow-unauthenticated \
    --set-env-vars="${COMMON_ENV}${extra_env}" \
    --set-secrets="${COMMON_SECRETS}" \
    "${CLOUDSQL_FLAG[@]}"
}

echo "Deploying API ingress"
deploy_service agent-mesh-api ""

echo "Deploying Slack ingress"
deploy_service agent-mesh-slack ",ENTRYPOINT=slack"

echo "Deploying MCP ingress"
deploy_service agent-mesh-mcp ",ENTRYPOINT=mcp"

deploy_job() {
  local name="$1"; shift
  local sa="$1"; shift
  local timeout="$1"; shift
  local extra_env="$1"; shift
  local image="$1"; shift
  local action="create"
  if gcloud run jobs describe "${name}" --region="${REGION}" >/dev/null 2>&1; then
    action="update"
  fi
  gcloud run jobs "${action}" "${name}" \
    --image="${image}" \
    --region="${REGION}" \
    --service-account="${sa}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --task-timeout="${timeout}" \
    --set-env-vars="${COMMON_ENV}${extra_env}" \
    --set-secrets="${COMMON_SECRETS}" \
    "${CLOUDSQL_FLAG[@]}"
}

echo "Creating or updating long-running worker job"
deploy_job agent-mesh-worker agent-mesh-worker 24h ",TASK_SUBSCRIPTION=agent-mesh-tasks-worker" "${WORKER_IMAGE}"

echo "Creating or updating prompt-to-code sandbox job"
deploy_job agent-mesh-code-executor agent-mesh-code-executor 2h ",SANDBOX_MODE=true" "${CODE_IMAGE}"

echo "Core deployment complete."
echo
echo "Reuse notes:"
echo "  - Existing project: this script only deploys; bootstrap handles project/API/SQL reuse."
echo "  - Existing Cloudflare AI Gateway: set CLOUDFLARE_AI_GATEWAY_ID and run cf_deploy_ai_gateway_worker.sh."
echo "  - For an in-memory POC without Cloud SQL, remove DATABASE_URL from COMMON_SECRETS and set USE_PUBSUB=false."
