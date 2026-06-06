"""Nango aggregator adapter — the fallback aggregator (TOOL-04, D-09).

Nango is the open-source unified-API aggregator; it self-hosts and brokers OAuth +
rate-limit/retry server-side. This adapter performs one real READ through the gateway
via the Nango REST **proxy** over the core ``httpx`` dependency.

NO NANGO PYTHON PACKAGE (RESEARCH Pitfall 1, threat T-04-08-02)
--------------------------------------------------------------
Nango's only SDK is npm ``@nangohq/node``. The PyPI ``nango`` package (0.1.2) is an
UNRELATED third-party package (confirmed at the package-legitimacy checkpoint) and is
DO-NOT-INSTALL. The Python integration path is the REST proxy over ``httpx`` — there is
zero ``nango`` import in this module.

REGISTRATION KEY (the SC-3 contract, 04-03 adapter_key_for)
----------------------------------------------------------
``execute()`` dispatches aggregator tools by ``adapter_key_for(spec)``, which maps
``nango_aggregator`` -> ``"nango"`` (the bare aggregator name == this module filename),
NOT the SaaS provider and NOT the integration_style string. So this module registers
under ``"nango"``. Registering under ``"nango_aggregator"`` would never be looked up and
a creds-present call would silently fall to the stub (SC-3 regression). ``register`` runs
at module top so ``get_adapter``'s import-on-miss populates the registry on first lookup.

THE PROXY CALL (RESEARCH A3)
---------------------------
    GET {NANGO_HOST}/proxy/<endpoint>
    headers:
      Authorization:      Bearer {NANGO_SECRET_KEY}   # == the resolved credential
      Connection-Id:      {NANGO_CONNECTION_ID}
      Provider-Config-Key:{NANGO_PROVIDER_CONFIG_KEY}

Nango exposes NO per-tool JSON Schema via the proxy, so the runtime schema is permissive
(``None``) per D-04 — a missing aggregate schema NEVER blocks the call.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from agent_mesh.tools.adapters import register

if TYPE_CHECKING:  # pragma: no cover - typing only
    from agent_mesh.tools.gateway import ToolSpec

# The three env vars (besides the resolved NANGO_SECRET_KEY credential) the proxy needs.
_NANGO_HOST = "NANGO_HOST"
_NANGO_CONNECTION_ID = "NANGO_CONNECTION_ID"
_NANGO_PROVIDER_CONFIG_KEY = "NANGO_PROVIDER_CONFIG_KEY"


def nango_adapter(spec: ToolSpec, params: dict, *, credential: str | None) -> dict:
    """Execute one Nango read via the REST ``/proxy`` endpoint over ``httpx``.

    ``credential`` is the resolved ``NANGO_SECRET_KEY`` (D-02). The engine stubs before
    reaching this adapter when the secret is absent (D-11) -> a ``None`` credential here
    is the defensive degrade-to-stub path. But when the credential IS present the user
    intended a live call, so a misconfigured proxy (missing ``NANGO_HOST`` /
    ``NANGO_CONNECTION_ID`` / ``NANGO_PROVIDER_CONFIG_KEY``) raises a clear ``RuntimeError``
    naming the missing vars (NO secret values) rather than silently returning ``None`` a
    caller would ``.get()`` on. The live test gates on all four vars, so this never fires
    in the default or live lane.
    """
    if not credential:
        # Engine stubs before reaching here when the credential is absent (D-11);
        # this defensive path returns None so the engine still degrades cleanly.
        return None  # type: ignore[return-value]

    host = os.getenv(_NANGO_HOST)
    connection_id = os.getenv(_NANGO_CONNECTION_ID)
    provider_config_key = os.getenv(_NANGO_PROVIDER_CONFIG_KEY)
    missing = [
        name
        for name, val in (
            (_NANGO_HOST, host),
            (_NANGO_CONNECTION_ID, connection_id),
            (_NANGO_PROVIDER_CONFIG_KEY, provider_config_key),
        )
        if not val
    ]
    if missing:
        # The credential is PRESENT, so the user intended a live call — a silent stub
        # would mask a misconfiguration. Fail loud with the missing var names (no secret
        # values). The live test gates on all four vars, so this never fires in tests.
        raise RuntimeError(
            "Nango credential resolved but the proxy is misconfigured; "
            f"missing env: {', '.join(missing)} (see docs/credentials/nango.md)"
        )

    # ``httpx`` is a CORE dependency — import is safe at module level, but kept local to
    # mirror the lazy-adapter pattern and avoid a top-level cost on every registry import.
    import httpx  # noqa: PLC0415

    bindings = spec.resource_bindings or {}
    endpoint = str(bindings.get("proxy_endpoint", "")).lstrip("/")
    url = f"{host.rstrip('/')}/proxy/{endpoint}"

    resp = httpx.request(
        "GET",
        url,
        params=params or None,
        headers={
            "Authorization": f"Bearer {credential}",
            "Connection-Id": connection_id,
            "Provider-Config-Key": provider_config_key,
        },
        timeout=30,
    )
    resp.raise_for_status()
    try:
        payload = resp.json()
    except ValueError:
        payload = {"raw_text": resp.text}

    return {
        "tool": spec.name,
        "provider": spec.provider,
        "category": spec.category.value,
        "aggregator": "nango",
        "result": payload,
    }


# Register at import time under the aggregator-name key adapter_key_for produces.
register("nango", nango_adapter)
