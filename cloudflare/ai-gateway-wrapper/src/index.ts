export interface Env {
  CF_ACCOUNT_ID: string;
  CF_AIG_GATEWAY_ID: string;
  COLLECT_LOG_PAYLOAD: string;
  CF_AIG_AUTH_TOKEN?: string;
  MODEL_GATEWAY_SHARED_SECRET?: string;
}

function metadataHeaders(request: Request): Headers {
  const headers = new Headers();
  const passthrough = [
    "x-agent-mesh-tenant-id",
    "x-agent-mesh-client-slug",
    "x-agent-mesh-task-id",
    "x-agent-mesh-session-id",
    "x-agent-mesh-requester-id",
    "x-agent-mesh-entrypoint",
    "x-agent-mesh-agent-role",
    "x-agent-mesh-model-route-profile",
  ];

  for (const name of passthrough) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  return headers;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    const sharedSecret = request.headers.get("x-gateway-shared-secret");
    if (env.MODEL_GATEWAY_SHARED_SECRET && sharedSecret !== env.MODEL_GATEWAY_SHARED_SECRET) {
      return new Response("Unauthorized", { status: 401 });
    }

    const url = new URL(request.url);
    const providerPath = url.pathname.replace(/^\/v1\//, "");
    const gatewayUrl = new URL(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/ai-gateway/gateways/${env.CF_AIG_GATEWAY_ID}/${providerPath}`
    );

    const headers = new Headers(request.headers);
    headers.set("cf-aig-gateway-id", env.CF_AIG_GATEWAY_ID);
    headers.set("cf-aig-collect-log-payload", env.COLLECT_LOG_PAYLOAD || "false");

    if (env.CF_AIG_AUTH_TOKEN) {
      headers.set("cf-aig-authorization", `Bearer ${env.CF_AIG_AUTH_TOKEN}`);
    }

    for (const [name, value] of metadataHeaders(request)) {
      headers.set(name, value);
    }

    return fetch(gatewayUrl, {
      method: request.method,
      headers,
      body: request.body,
    });
  },
};

