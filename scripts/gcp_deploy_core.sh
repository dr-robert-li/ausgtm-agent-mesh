#!/usr/bin/env bash
set -euo pipefail

# Deploy reusable Cloud Run services/jobs once container images exist.
# Usage:
#   PROJECT_ID=my-project REGION=australia-southeast1 IMAGE_TAG=... ./scripts/gcp_deploy_core.sh

: "${PROJECT_ID:?Set PROJECT_ID}"
: "${REGION:=australia-southeast1}"
: "${AR_REPO:=agent-mesh}"
: "${IMAGE_TAG:=latest}"
: "${API_IMAGE:=${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/agent-mesh-api:${IMAGE_TAG}}"
: "${WORKER_IMAGE:=${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/agent-mesh-worker:${IMAGE_TAG}}"
: "${CODE_IMAGE:=${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/agent-mesh-code-executor:${IMAGE_TAG}}"

gcloud config set project "${PROJECT_ID}"

COMMON_ENV="REGION=${REGION},TASK_TOPIC=agent-mesh-tasks,APPROVAL_TOPIC=agent-mesh-approvals,DLQ_TOPIC=agent-mesh-dlq"

echo "Deploying API ingress"
gcloud run deploy agent-mesh-api \
  --image="${API_IMAGE}" \
  --region="${REGION}" \
  --service-account="agent-mesh-api@${PROJECT_ID}.iam.gserviceaccount.com" \
  --no-allow-unauthenticated \
  --set-env-vars="${COMMON_ENV}"

echo "Deploying Slack ingress"
gcloud run deploy agent-mesh-slack \
  --image="${API_IMAGE}" \
  --region="${REGION}" \
  --service-account="agent-mesh-api@${PROJECT_ID}.iam.gserviceaccount.com" \
  --no-allow-unauthenticated \
  --set-env-vars="${COMMON_ENV},ENTRYPOINT=slack"

echo "Deploying MCP ingress"
gcloud run deploy agent-mesh-mcp \
  --image="${API_IMAGE}" \
  --region="${REGION}" \
  --service-account="agent-mesh-api@${PROJECT_ID}.iam.gserviceaccount.com" \
  --no-allow-unauthenticated \
  --set-env-vars="${COMMON_ENV},ENTRYPOINT=mcp"

echo "Creating or updating long-running worker job"
if gcloud run jobs describe agent-mesh-worker --region="${REGION}" >/dev/null 2>&1; then
  gcloud run jobs update agent-mesh-worker \
    --image="${WORKER_IMAGE}" \
    --region="${REGION}" \
    --service-account="agent-mesh-worker@${PROJECT_ID}.iam.gserviceaccount.com" \
    --task-timeout=24h \
    --set-env-vars="${COMMON_ENV}"
else
  gcloud run jobs create agent-mesh-worker \
    --image="${WORKER_IMAGE}" \
    --region="${REGION}" \
    --service-account="agent-mesh-worker@${PROJECT_ID}.iam.gserviceaccount.com" \
    --task-timeout=24h \
    --set-env-vars="${COMMON_ENV}"
fi

echo "Creating or updating prompt-to-code sandbox job"
if gcloud run jobs describe agent-mesh-code-executor --region="${REGION}" >/dev/null 2>&1; then
  gcloud run jobs update agent-mesh-code-executor \
    --image="${CODE_IMAGE}" \
    --region="${REGION}" \
    --service-account="agent-mesh-code-executor@${PROJECT_ID}.iam.gserviceaccount.com" \
    --task-timeout=2h \
    --set-env-vars="${COMMON_ENV},SANDBOX_MODE=true"
else
  gcloud run jobs create agent-mesh-code-executor \
    --image="${CODE_IMAGE}" \
    --region="${REGION}" \
    --service-account="agent-mesh-code-executor@${PROJECT_ID}.iam.gserviceaccount.com" \
    --task-timeout=2h \
    --set-env-vars="${COMMON_ENV},SANDBOX_MODE=true"
fi

echo "Core deployment complete."

