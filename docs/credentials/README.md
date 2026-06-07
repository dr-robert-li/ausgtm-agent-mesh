# Credential & scope setup index (live lane) — D-12

The **default test lane is creds-free**: `make test` / `pytest -m "not live"` never
touches a real provider, never needs a secret, and never installs an optional SDK — each
adapter degrades to a deterministic stub when its credential is absent (D-11). Live
provider calls are **per-provider opt-in**: you only supply the secret(s) for the
provider(s) you want to exercise, and each provider's live tests **skip independently**
when its own creds are absent. Supplying HubSpot creds never forces you to supply
Composio's, and vice-versa.

This index is the single discoverable place that tells you, per provider, **which env
var(s) to set, what they govern, where to mint them, and which per-provider doc has the
exact scopes/setup**. No real secret values live in this repo — only env-var *names* and
placeholder instructions (threat T-04-09-01).

## Per-provider live-lane matrix (D-11 opt-in)

Each row is independently skippable: set its env var(s) to opt that provider into the
live lane; leave them unset and only that provider's live tests skip.

| Provider | Integration style | Operations | Live-lane env var(s) | Setup doc | Skip behaviour when unset |
| :--- | :--- | :--- | :--- | :--- | :--- |
| HubSpot | `direct_api` | read (`hubspot_lookup_company`) + approval-gated write (`hubspot_create_deal`) | `HUBSPOT_PRIVATE_APP_TOKEN` | [hubspot.md](./hubspot.md) | `tests/test_hubspot_live.py` skips; adapter falls back to stub |
| Google Workspace (Drive, Gmail, Sheets, Calendar, Docs, Slides) | `direct_api` | reads + approval-gated writes/sends across all six products | `GOOGLE_WORKSPACE_OAUTH` | [google_workspace.md](./google_workspace.md) | `tests/test_gws_live.py` skips; adapter falls back to stub |
| Composio (primary aggregator) | `composio_aggregator` | read (`composio_gmail_list_messages`) | `COMPOSIO_API_KEY` | [composio.md](./composio.md) | `tests/test_composio_live.py` skips; adapter falls back to stub |
| Nango (fallback aggregator) | `nango_aggregator` | read (`nango_hubspot_list_contacts`) | `NANGO_SECRET_KEY`, `NANGO_HOST`, `NANGO_CONNECTION_ID`, `NANGO_PROVIDER_CONFIG_KEY` | [nango.md](./nango.md) | `tests/test_nango_live.py` skips if **any** of the four is unset; adapter falls back to stub |
| Webflow | `direct_api` | read (`webflow_list_cms_items`) + approval-gated publish (`webflow_publish_item`) | `WEBFLOW_API_TOKEN` | [webflow.md](./webflow.md) | `tests/test_webflow_live.py` skips; adapter falls back to stub |
| Bitscale | `direct_api` | read (`bitscale_*` reads-only live lane; `run_grid` credit-safe-stubbed) | `BITSCALE_API_KEY` | [bitscale.md](./bitscale.md) | `tests/test_bitscale_live.py` skips; adapter falls back to stub |
| Cal.com | `direct_api` | read (`calcom_list_bookings`) + approval-gated write | `CALCOM_API_KEY` | [calcom.md](./calcom.md) | `tests/test_calcom_live.py` skips; adapter falls back to stub |
| Clockify | `direct_api` | read (`clockify_list_time_entries`) + approval-gated write | `CLOCKIFY_API_KEY` | [clockify.md](./clockify.md) | `tests/test_clockify_live.py` skips; adapter falls back to stub |
| Beehiiv | `direct_api` | read + approval-gated publish (real create only when `BEEHIIV_LIVE_PUBLICATION_ID` is also set) | `BEEHIIV_API_KEY` | [beehiiv.md](./beehiiv.md) | `tests/test_beehiiv_live.py` skips; adapter falls back to stub |
| Xero (via Composio) | `composio_aggregator` | read (`xero_read_invoices`) + approval-gated **draft-only** financial write (`xero_create_invoice`) | `COMPOSIO_API_KEY` (reused — no new env var) | [xero.md](./xero.md) | `tests/test_xero_live.py` skips when `COMPOSIO_API_KEY` unset; rides the existing composio adapter |

## Complete live-lane env var enumeration

Every env var the adapters' live lane reads (the authoritative set the completeness guard
in `tests/test_credential_docs.py` derives from the live tests + adapter source):

| Env var | Provider | Shape | Resolved where |
| :--- | :--- | :--- | :--- |
| `HUBSPOT_PRIVATE_APP_TOKEN` | HubSpot | private-app bearer token | only inside `ToolGateway.execute()` (D-02) |
| `GOOGLE_WORKSPACE_OAUTH` | Google Workspace | JSON blob `{client_id, client_secret, refresh_token}` | only inside `ToolGateway.execute()` (D-02) |
| `COMPOSIO_API_KEY` | Composio | API key (`comp_…`) | only inside `ToolGateway.execute()` (D-02) |
| `NANGO_SECRET_KEY` | Nango | environment secret key (Bearer for the proxy) | only inside `ToolGateway.execute()` (D-02) |
| `NANGO_HOST` | Nango | self-hosted base URL (e.g. `http://localhost:3003`) | read by `tools/adapters/nango.py` at call time |
| `NANGO_CONNECTION_ID` | Nango | connection id from the Nango dashboard | read by `tools/adapters/nango.py` at call time |
| `NANGO_PROVIDER_CONFIG_KEY` | Nango | provider config key from the Nango dashboard | read by `tools/adapters/nango.py` at call time |
| `WEBFLOW_API_TOKEN` | Webflow | site API token | resolved only inside `ToolGateway.execute()` (D-02) |
| `BITSCALE_API_KEY` | Bitscale | API key (`X-API-Key`) | resolved only inside `ToolGateway.execute()` (D-02) |
| `CALCOM_API_KEY` | Cal.com | API key | resolved only inside `ToolGateway.execute()` (D-02) |
| `CLOCKIFY_API_KEY` | Clockify | workspace API key | resolved only inside `ToolGateway.execute()` (D-02) |
| `BEEHIIV_API_KEY` | Beehiiv | publication API key | resolved only inside `ToolGateway.execute()` (D-02) |

> Xero is integrated **via Composio** and reuses `COMPOSIO_API_KEY` (already enumerated
> above) — it adds **no new env var**. `BEEHIIV_LIVE_PUBLICATION_ID` is an optional
> non-secret resource toggle for Beehiiv's real-create live path (not a credential).

The credential proper (`*_TOKEN` / `*_OAUTH` / `*_API_KEY` / `NANGO_SECRET_KEY`) is keyed
by each tool's `credential_secret_name` in `manifests/tool_pack_manifest.yaml` and resolved
by the `EnvCredentialResolver` locally (the same key resolves through `SecretManagerResolver`
in production — no engine change). It is never logged, never returned to the agent, and
never set as a span attribute (D-02).

## Running the live lane

The live lane is opt-in and deselected by default:

```bash
# default (creds-free) lane — never touches a provider:
make test                                  # == pytest -m "not live"

# live lane — supply only the provider(s) you want to exercise:
export HUBSPOT_PRIVATE_APP_TOKEN='...'     # see hubspot.md
PYTHONPATH=src .venv/bin/python -m pytest -q -m live tests/test_hubspot_live.py
```

Run all live tests with `pytest -m live`; each provider whose creds are absent **skips
cleanly** (it never errors), so you can run the whole live lane with only a subset of
providers configured. Per-provider minting/scopes/setup live in the docs linked above:
[hubspot.md](./hubspot.md), [google_workspace.md](./google_workspace.md),
[composio.md](./composio.md), [nango.md](./nango.md), [webflow.md](./webflow.md),
[bitscale.md](./bitscale.md), [calcom.md](./calcom.md), [clockify.md](./clockify.md),
[beehiiv.md](./beehiiv.md), [xero.md](./xero.md).
