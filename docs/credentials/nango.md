# Nango aggregator credential setup (D-12)

Nango is the **fallback** aggregator: the open-source unified-API broker. You self-host
it (docker compose), connect a provider, and the mesh calls Nango's REST **proxy** — Nango
injects the provider credential and handles rate-limit/retry server-side.

This is **opt-in**: the default test suite never touches Nango. You only need this to run
the live read (`tests/test_nango_live.py`).

> **NO Python package (RESEARCH Pitfall 1, threat T-04-08-02).** Nango's only SDK is npm
> `@nangohq/node`. The PyPI `nango` package (0.1.2) is an UNRELATED third-party package
> (author "Nick Farrell", "Provide model integrity between requests") — it is NOT NangoHQ
> and is **DO-NOT-INSTALL** (confirmed at the package-legitimacy checkpoint). The Python
> path is the REST proxy over the core `httpx` dependency; the adapter has zero `nango`
> imports.

## 1. Self-host Nango (docker compose)

```bash
mkdir nango && cd nango
# Fetch the official compose file from NangoHQ/nango (master):
wget https://raw.githubusercontent.com/NangoHQ/nango/master/docker/docker-compose.yaml
docker compose up -d
```

Nango comes up on `http://localhost:3003` by default (its dashboard + API + proxy).

## 2. Create a provider config + connection

In the Nango dashboard:

1. **Integrations -> New** — add the provider you want to read (e.g. HubSpot). This gives
   you a **provider config key**.
2. **Connections -> New** — run the OAuth flow for that provider. This gives you a
   **connection id**.
3. **Environment Settings** — copy the environment **secret key**.

## 3. Export the four env vars

The manifest declares `credential_secret_name: NANGO_SECRET_KEY`; the adapter also reads
the host, connection id, and provider config key from the environment:

```bash
export NANGO_HOST="http://localhost:3003"
export NANGO_SECRET_KEY="<environment secret key>"
export NANGO_CONNECTION_ID="<connection id>"
export NANGO_PROVIDER_CONFIG_KEY="<provider config key>"
```

## 4. Run the live read

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q -m live tests/test_nango_live.py
```

The adapter issues:

```
GET {NANGO_HOST}/proxy/<endpoint>
  Authorization:       Bearer {NANGO_SECRET_KEY}
  Connection-Id:       {NANGO_CONNECTION_ID}
  Provider-Config-Key: {NANGO_PROVIDER_CONFIG_KEY}
```

where `<endpoint>` is the manifest seam's `resource_bindings.proxy_endpoint`
(`crm/v3/objects/contacts` for `nango_hubspot_list_contacts`).

- With all four env vars set + a self-hosted Nango + connection, this performs one real
  proxy read through `ToolGateway.execute()` and asserts the registered adapter ran (not
  the stub).
- If ANY of the four is absent it **SKIPS** cleanly.

## Notes

- The adapter (`src/agent_mesh/tools/adapters/nango.py`) registers under the key `nango`
  (the `adapter_key_for` aggregator-name key) and uses `httpx` only.
- Nango's proxy exposes no per-tool JSON Schema, so the runtime aggregate schema is `None`
  -> permissive (D-04: a missing aggregate schema never blocks).
- The credential is resolved ONLY inside `execute()` and is never logged or returned
  (D-02). Reads only this phase (D-09).
