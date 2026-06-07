# Webflow credential & scope setup (D-12)

The Webflow direct adapter (`webflow_list_cms_items` read + `webflow_create_cms_item`
approval-gated publishing write — D-07, TOOL-03) authenticates with a single **Webflow
Site API token** (bearer). The token is resolved only at execution time inside
`ToolGateway.execute()` (D-02) and is never logged or returned. With the token unset the
adapter degrades to the deterministic stub (D-11) and the default test suite stays green
and creds-free.

> **Transport note:** the adapter calls the **Webflow Data API v2**
> (`https://api.webflow.com/v2/...`) over the core `httpx` dependency — there is **no
> SDK** and no opt-in extra to install. The adapter module imports cleanly in the default
> lane; only a live token (plus real resource bindings) is needed for the live lane.

## 1. Mint a Webflow Site API token + scopes

In the Webflow Designer/Dashboard for the target **site**:

**Site -> Settings -> Apps & Integrations -> API Access -> Generate API token**

Grant exactly these CMS scopes:

| Scope | Used by |
| :--- | :--- |
| `CMS:read`  | `webflow_list_cms_items` (list collection items) |
| `CMS:write` | `webflow_create_cms_item` (create a draft item) |

Copy the generated **Site API token** (shown once). It is scoped to that one site.

## 2. Point the tools at a real site + collection

The adapter reads `site_id` and `collection_id` from the tool's `resource_bindings` in
the tool pack manifest (`manifests/tool_pack_manifest.yaml`) — **not** from params.
Replace the placeholders for BOTH tools with the real IDs from your site:

```yaml
  - name: "webflow_list_cms_items"
    provider: "webflow"
    resource_bindings:
      site_id: "<your-site-id>"
      collection_id: "<your-collection-id>"

  - name: "webflow_create_cms_item"
    provider: "webflow"
    resource_bindings:
      site_id: "<your-site-id>"
      collection_id: "<your-collection-id>"
```

You can list collection IDs for a site via `GET /v2/sites/{site_id}/collections` with the
same token, or read them from the Designer URL.

> **Operator note (live lane):** the live lane skips on a **missing** `WEBFLOW_API_TOKEN`
> but it does **not** skip on placeholder `resource_bindings`. A leftover
> `collection_id: "REPLACE_WITH_COLLECTION_ID"` makes the live call **error** (Webflow
> returns 404/400 for the bogus collection) instead of skipping. Set real `site_id` /
> `collection_id` before running the live lane, not just the env key.

## 3. Export the token for the live lane

```bash
export WEBFLOW_API_TOKEN='<the-site-api-token>'
```

The manifest's `credential_secret_name: "WEBFLOW_API_TOKEN"` keys the
`EnvCredentialResolver` to this variable. In production the same key resolves through
`SecretManagerResolver` instead (no engine change).

## 4. Draft-only & 202 gotchas (publishing safety)

- **`webflow_create_cms_item` always stages a DRAFT.** The adapter hardcodes
  `isDraft: true` in the POST body and **ignores** any caller-supplied `isDraft: false`
  (threat T-05-02-01) — a create therefore never publishes a live CMS item, it only
  stages a draft for later human publishing. The default-lane test asserts this.
- **The create returns HTTP `202` (Accepted)**, not `200/201` — the item is staged
  asynchronously. The adapter accepts the 202 body and maps it to `{id, fieldData, ...}`.
- **`webflow_create_cms_item` stays `category: publishing` / `approval_required: true`**,
  so it is reached only after the shared approval ledger approves the payload-hash-bound
  call (SEC-01/02 — the adapter performs no gating of its own).
- The Data API v2 **paths already include `/v2`** (e.g.
  `/v2/collections/{collection_id}/items`); the adapter uses host `https://api.webflow.com`
  and never doubles the `/v2` segment.

## 5. Run the live test

```bash
PYTHONPATH=src python -m pytest -q -m live tests/test_webflow_live.py
```

- With the token set (and real bindings): runs a real `webflow_list_cms_items` through
  the gateway.
- With the token unset: **skips** cleanly (never errors), so the default suite stays
  creds-free. (`webflow_create_cms_item` is not exercised live — it is an approval-gated
  draft mutation; its mapping is proven in the default-lane unit test.)
