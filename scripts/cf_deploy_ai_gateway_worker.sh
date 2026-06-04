#!/usr/bin/env bash
set -euo pipefail

# Deploy the Cloudflare AI Gateway wrapper with Wrangler.
# Idempotent by design:
# - Reuses an existing Cloudflare AI Gateway when CLOUDFLARE_AI_GATEWAY_ID is set.
# - Deploys/updates the Worker with Wrangler.
# - Does not delete or recreate gateways.
# Run from repository root:
#   CLOUDFLARE_ACCOUNT_ID=... CLOUDFLARE_AI_GATEWAY_ID=agent-mesh-poc ./scripts/cf_deploy_ai_gateway_worker.sh

: "${CLOUDFLARE_ACCOUNT_ID:?Set CLOUDFLARE_ACCOUNT_ID}"
: "${CLOUDFLARE_AI_GATEWAY_ID:=agent-mesh-poc}"
: "${WRANGLER_ENV:=poc}"
: "${REUSE_EXISTING_CLOUDFLARE_GATEWAY:=true}"

cd cloudflare/ai-gateway-wrapper

echo "Checking Wrangler authentication"
wrangler whoami

if [[ "${REUSE_EXISTING_CLOUDFLARE_GATEWAY}" == "true" ]]; then
  echo "Reusing Cloudflare AI Gateway ID: ${CLOUDFLARE_AI_GATEWAY_ID}"
else
  echo "Gateway auto-creation/creation should be handled before this script or via Cloudflare API/dashboard."
  echo "This script deploys the Worker wrapper and points it at CLOUDFLARE_AI_GATEWAY_ID."
fi

echo "Deploying Worker wrapper to Cloudflare"
wrangler deploy --env "${WRANGLER_ENV}"

echo "Set secrets with:"
echo "  wrangler secret put CF_AIG_AUTH_TOKEN --env ${WRANGLER_ENV}"
echo "  wrangler secret put LITELLM_SHARED_SECRET --env ${WRANGLER_ENV}"
echo
echo "Configure Cloudflare AI Gateway, Guardrails, and DLP profiles in Cloudflare dashboard or API."
echo "Gateway ID expected by this worker: ${CLOUDFLARE_AI_GATEWAY_ID}"
