# Xero (via Composio aggregator) credential setup (D-12)

Xero is integrated **through Composio** (`integration_style: composio_aggregator`), not
as a direct adapter. Composio brokers the Xero OAuth + tenant selection, so the mesh
never handles raw Xero credentials and **ships no Xero adapter module** — both Xero tools
ride the existing `src/agent_mesh/tools/adapters/composio.py` (its verb-agnostic
`session.execute(tool=tool_slug, ...)`).

This is **opt-in**: the default test suite never touches Xero. You only need this to run
the live read (`tests/test_xero_live.py`).

## Reuses the SAME `COMPOSIO_API_KEY` — no new env var

Xero rides the existing Composio control plane, so it reuses the **same** secret already
documented for Composio:

```bash
export COMPOSIO_API_KEY="comp_xxx..."   # same key as composio.md — NOT a new secret
```

There is **no new env var** for Xero. The credential is resolved ONLY inside
`ToolGateway.execute()` and is never logged or returned to the agent (D-02).

## 1. Connect the Xero toolkit in Composio

1. Sign in at https://app.composio.dev with the account that owns `COMPOSIO_API_KEY`.
2. **Toolkits / Apps -> Xero -> Connect.** Composio runs the Xero OAuth and lets you pick
   the Xero **tenant/organisation**; the connection is bound to your Composio `user_id`.
3. Use the same `user_id` the manifest declares in `resource_bindings.user_id`
   (`mesh-tenant-example`) so the gateway resolves the same connected Xero account.

## 2. Manifest tools (`tool_slug` + `user_id`)

Both entries live in `manifests/tool_pack_manifest.yaml` under `provider: xero`,
`integration_style: composio_aggregator`, `credential_secret_name: COMPOSIO_API_KEY`:

| Tool | Category | `resource_bindings.tool_slug` | Approval |
| :--- | :--- | :--- | :--- |
| `xero_read_invoices` | `read` | `XERO_LIST_INVOICES` | none (read) |
| `xero_create_invoice` | `financial` | `XERO_CREATE_INVOICE` | **approval-gated (D-07)** |

## 3. The financial write is DRAFT-only

`xero_create_invoice` is a **financial write**. It is:

- **Approval-gated upstream** — it is reached only after the human-in-the-loop
  write-approval gate (payload-hash bound), like every write-class tool.
- **DRAFT-only** — the created invoice is `Status: DRAFT` and is **never auto-finalised**
  or authorised. Finalising/sending a Xero invoice is out of scope for the POC.

It is **not exercised in the live lane**; its mapping rides Composio's verb-agnostic
`session.execute` and is proven structurally (the default-lane resolution test asserts it
resolves to the `composio` adapter).

## 4. Run the live read

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q -m live tests/test_xero_live.py
```

- With `COMPOSIO_API_KEY` set + the Xero toolkit connected, this performs one real
  read-only `xero_read_invoices` through `ToolGateway.execute()` and asserts the
  registered composio adapter ran (not the stub).
- Without the key it **SKIPS** cleanly (it never errors, and never needs the SDK).

## Notes

- No new Xero adapter module exists (`src/agent_mesh/tools/adapters/xero.py` is absent by
  design) — Xero rides `composio.py` unchanged.
- SDK install + API-key minting are identical to Composio — see
  [composio.md](./composio.md).
