#!/usr/bin/env bash
set -euo pipefail

# Bootstrap reusable GCP resources for the Autonomous Agent Mesh POC.
# Idempotent by design:
# - Reuses an existing project if it exists.
# - Optionally creates a project only when CREATE_PROJECT=true and BILLING_ACCOUNT_ID is set.
# - Creates or reuses APIs, Artifact Registry, Pub/Sub topics, service accounts, IAM grants, and Cloud SQL.
# Usage:
#   PROJECT_ID=my-project REGION=australia-southeast1 ./scripts/gcp_bootstrap.sh
# Optional new project:
#   CREATE_PROJECT=true BILLING_ACCOUNT_ID=XXXXXX-XXXXXX-XXXXXX PROJECT_ID=my-project ./scripts/gcp_bootstrap.sh

: "${PROJECT_ID:?Set PROJECT_ID}"
: "${REGION:=australia-southeast1}"
: "${CREATE_PROJECT:=false}"
: "${BILLING_ACCOUNT_ID:=}"
: "${AR_REPO:=agent-mesh}"
: "${SQL_INSTANCE:=agent-mesh-poc}"
: "${SQL_DATABASE:=agent_mesh}"
: "${SQL_TIER:=db-g1-small}"
: "${SQL_STORAGE_GB:=20}"

echo "Checking project ${PROJECT_ID}"
if ! gcloud projects describe "${PROJECT_ID}" >/dev/null 2>&1; then
  if [[ "${CREATE_PROJECT}" == "true" ]]; then
    if [[ -z "${BILLING_ACCOUNT_ID}" ]]; then
      echo "BILLING_ACCOUNT_ID is required when CREATE_PROJECT=true" >&2
      exit 1
    fi
    echo "Creating project ${PROJECT_ID}"
    gcloud projects create "${PROJECT_ID}" --name="${PROJECT_ID}"
    gcloud billing projects link "${PROJECT_ID}" --billing-account="${BILLING_ACCOUNT_ID}"
  else
    echo "Project ${PROJECT_ID} does not exist. Create it first or set CREATE_PROJECT=true with BILLING_ACCOUNT_ID." >&2
    exit 1
  fi
else
  echo "Project ${PROJECT_ID} exists; reusing it."
fi

echo "Using project ${PROJECT_ID} in ${REGION}"
gcloud config set project "${PROJECT_ID}"

echo "Enabling required APIs"
gcloud services enable \
  run.googleapis.com \
  runapps.googleapis.com \
  sqladmin.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  pubsub.googleapis.com \
  cloudbuild.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com

echo "Creating Artifact Registry repository if missing"
gcloud artifacts repositories describe "${AR_REPO}" --location="${REGION}" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "${AR_REPO}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="Agent mesh container images"

echo "Creating Pub/Sub topics if missing"
for topic in agent-mesh-tasks agent-mesh-approvals agent-mesh-dlq; do
  gcloud pubsub topics describe "${topic}" >/dev/null 2>&1 || \
    gcloud pubsub topics create "${topic}"
done

echo "Creating service accounts if missing"
for sa in agent-mesh-api agent-mesh-worker agent-mesh-code-executor; do
  gcloud iam service-accounts describe "${sa}@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1 || \
    gcloud iam service-accounts create "${sa}" --display-name="${sa}"
done

echo "Granting service account permissions idempotently"
grant_role() {
  local member="$1"
  local role="$2"
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="${member}" \
    --role="${role}" \
    --condition=None >/dev/null
}

for sa in agent-mesh-api agent-mesh-worker agent-mesh-code-executor; do
  member="serviceAccount:${sa}@${PROJECT_ID}.iam.gserviceaccount.com"
  grant_role "${member}" "roles/logging.logWriter"
  grant_role "${member}" "roles/monitoring.metricWriter"
  grant_role "${member}" "roles/secretmanager.secretAccessor"
  grant_role "${member}" "roles/cloudsql.client"
done

grant_role "serviceAccount:agent-mesh-api@${PROJECT_ID}.iam.gserviceaccount.com" "roles/pubsub.publisher"
grant_role "serviceAccount:agent-mesh-worker@${PROJECT_ID}.iam.gserviceaccount.com" "roles/pubsub.subscriber"
grant_role "serviceAccount:agent-mesh-worker@${PROJECT_ID}.iam.gserviceaccount.com" "roles/pubsub.publisher"
grant_role "serviceAccount:agent-mesh-code-executor@${PROJECT_ID}.iam.gserviceaccount.com" "roles/pubsub.publisher"

echo "Creating non-HA Cloud SQL PostgreSQL instance if missing"
if ! gcloud sql instances describe "${SQL_INSTANCE}" >/dev/null 2>&1; then
  gcloud sql instances create "${SQL_INSTANCE}" \
    --database-version=POSTGRES_16 \
    --region="${REGION}" \
    --tier="${SQL_TIER}" \
    --storage-size="${SQL_STORAGE_GB}" \
    --storage-type=SSD \
    --availability-type=ZONAL \
    --backup-start-time=13:00
else
  echo "Cloud SQL instance ${SQL_INSTANCE} exists; reusing it."
fi

echo "Creating application database if missing"
gcloud sql databases describe "${SQL_DATABASE}" --instance="${SQL_INSTANCE}" >/dev/null 2>&1 || \
  gcloud sql databases create "${SQL_DATABASE}" --instance="${SQL_INSTANCE}"

echo "Create required secrets manually or via CI before deploy:"
echo "  SLACK_SIGNING_SECRET, SLACK_BOT_TOKEN, CLOUDFLARE_API_TOKEN, LITELLM_MASTER_KEY,"
echo "  LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, provider keys, and SaaS tool credentials."

echo "Bootstrap complete."
