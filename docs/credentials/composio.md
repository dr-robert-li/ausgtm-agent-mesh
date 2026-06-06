# Composio aggregator credential setup (D-12)

Composio is the **primary** aggregator (Spike 001 winner): the MCP-native managed-auth
Tool Router. One API key brokers OAuth for hundreds of SaaS tools, so the mesh never
handles raw per-provider credentials — Composio resolves them at execution time.

This is **opt-in**: the default test suite never touches Composio. You only need this to
run the live read (`tests/test_composio_live.py`).

## 1. Install the SDK (opt-in extra)

The `composio` SDK is in the `aggregators` optional extra, NOT installed by default
(supply-chain hygiene — see the package-legitimacy note below):

```bash
pip install -e '.[aggregators]'   # installs composio>=0.13,<1
```

Confirm the import path (the package was renamed from `composio-core`):

```python
from composio import Composio   # 0.13.x — NOT `composio-core`
```

> **Package legitimacy (12-month supply-chain audit).** `composio` 0.13.1 is the current
> OFFICIAL Composio SDK (PyPI publisher Composio; home `github.com/composiohq/composio`).
> Verified on PyPI 2026-06-06 and approved at the blocking-human checkpoint
> (threat T-04-08-SC). Pin `composio>=0.13,<1`.

## 2. Get an API key

1. Sign in at https://app.composio.dev.
2. **Settings -> API Keys -> Create** a key.
3. Export it as the secret name the manifest declares:

```bash
export COMPOSIO_API_KEY="comp_xxx..."
```

## 3. Connect an account (managed auth)

Composio brokers OAuth per SaaS. Connect at least the provider the test read targets
(Gmail, in the default manifest seam `composio_gmail_list_messages`):

```python
from composio import Composio
composio = Composio()                       # reads COMPOSIO_API_KEY from env
session = composio.create(user_id="mesh-tenant-example")  # managed-auth connected account
print(session.tools())                      # tool defs incl. input JSON Schema (D-04)
```

Use the same `user_id` the manifest's `resource_bindings.user_id` declares
(`mesh-tenant-example` in the seam) so the gateway resolves the same connected account.

## 4. Run the live read

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q -m live tests/test_composio_live.py
```

- With `COMPOSIO_API_KEY` set + a connected account, this performs one real read through
  `ToolGateway.execute()` and asserts the registered adapter ran (not the stub).
- Without the key it **SKIPS** cleanly (it never errors, and never needs the SDK).

## Notes

- The adapter (`src/agent_mesh/tools/adapters/composio.py`) registers under the key
  `composio` (the `adapter_key_for` aggregator-name key), lazy-imports the SDK, and
  fetches the runtime input JSON Schema via `aggregate_schema.fetch_runtime_schema`
  (D-04 — a missing schema never blocks).
- The credential is resolved ONLY inside `execute()` and is never logged or returned
  (D-02).
- Reads only this phase (D-09) — no approval-gate coupling.
