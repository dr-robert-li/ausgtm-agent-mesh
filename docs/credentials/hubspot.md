# HubSpot credential & scope setup (D-12)

The HubSpot direct adapter (`hubspot_lookup_company` read + `hubspot_create_deal`
approval-gated write — D-07, TOOL-01) authenticates with a single **private-app
bearer token**. The token is resolved only at execution time inside
`ToolGateway.execute()` (D-02) and is never logged or returned. With the token unset
the adapter degrades to the deterministic stub (D-11) and the default test suite stays
green and creds-free.

> **Supply-chain note (T-04-05-SC):** the adapter depends on the official HubSpot SDK
> `hubspot-api-client>=12,<13` (import path `from hubspot import HubSpot`). It is an
> **opt-in** dependency declared in the `tools` extra of `pyproject.toml` — install it
> only for the live lane (`pip install -e '.[tools]'`). It is NOT installed in the
> default lane; the adapter module imports cleanly without it.

## 1. Create a HubSpot dev/test sandbox (never write to production — T-04-05-01)

Live `hubspot_create_deal` writes MUST hit a non-production environment. Use either:

- a **standard sandbox** — HubSpot account: **Settings -> Account Management ->
  Sandboxes -> Create standard sandbox**; or
- a free **developer test account** — https://developers.hubspot.com -> create a test
  account.

Sandbox object/pipeline IDs differ from production, so a sandbox token cannot
accidentally mutate the live CRM.

## 2. Mint a private-app token + scopes

In the sandbox account: **Settings -> Integrations -> Private Apps -> Create a private
app**, then on the **Scopes** tab grant exactly:

| Scope | Used by |
| :--- | :--- |
| `crm.objects.companies.read` | `hubspot_lookup_company` (companies) |
| `crm.objects.contacts.read`  | `hubspot_lookup_company` (contacts) |
| `crm.objects.deals.write`    | `hubspot_create_deal` |

(Add `crm.objects.deals.read` only if you later read deals back.)

Create the app and copy the generated **access token** (a private-app token, shown
once).

## 3. Point the write at the sandbox pipeline

In the tool pack manifest (`manifests/tool_pack_manifest.yaml`), set the
`hubspot_create_deal` tool's sandbox pipeline:

```yaml
  - name: "hubspot_create_deal"
    provider: "hubspot"
    resource_bindings:
      pipeline_id: "<your-sandbox-pipeline-id>"   # from the sandbox, NOT production
```

The adapter passes `resource_bindings.pipeline_id` through as the deal `pipeline`
property and echoes it back as `pipeline_id` in the result. `hubspot_create_deal`
stays `category: write` / `approval_required: true`, so it is reached only after the
shared approval ledger approves the payload-hash-bound call (SEC-01/02 — unchanged).

## 4. Export the token for the live lane

```bash
export HUBSPOT_PRIVATE_APP_TOKEN='<the-private-app-token>'
```

The manifest's `credential_secret_name: "HUBSPOT_PRIVATE_APP_TOKEN"` keys the
`EnvCredentialResolver` to this variable. In production the same key resolves through
`SecretManagerResolver` instead (no engine change).

## 5. Run the live test

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q -m live tests/test_hubspot_live.py
```

- With the token set: runs a real `hubspot_lookup_company` through the gateway.
- With the token unset: **skips** cleanly (never errors), so the default suite stays
  creds-free.
