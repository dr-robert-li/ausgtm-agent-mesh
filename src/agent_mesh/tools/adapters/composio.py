"""Composio aggregator adapter — the primary aggregator (TOOL-04, D-09).

Composio is the MCP-native managed-auth Tool Router (Spike 001 winner): one API key
brokers OAuth for hundreds of SaaS tools. This adapter performs one real READ through
the gateway via the ``composio`` SDK (``from composio import Composio``).

REGISTRATION KEY (the SC-3 contract, 04-03 adapter_key_for)
----------------------------------------------------------
``execute()`` dispatches aggregator tools by ``adapter_key_for(spec)``, which maps
``composio_aggregator`` -> ``"composio"`` (the bare aggregator name, == this module
filename), NOT the SaaS provider and NOT the integration_style string. So this module
registers under ``"composio"``. Registering under ``"composio_aggregator"`` would never
be looked up and a creds-present call would silently fall to the stub (SC-3 regression).

The ``register(...)`` call under key ``composio`` runs at MODULE IMPORT (top level) so
``get_adapter``'s import-on-miss populates the registry the first time it is looked up — even though
the ``composio`` SDK is NOT installed in the default lane. The SDK import is therefore
LAZY (inside the adapter fn): if it were at module top, ``get_adapter``'s ImportError
swallow would return ``None`` and the registered adapter would never be reachable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_mesh.contracts.enums import ToolCategory
from agent_mesh.tools import aggregate_schema
from agent_mesh.tools.adapters import register

if TYPE_CHECKING:  # pragma: no cover - typing only
    from agent_mesh.tools.gateway import ToolSpec


def _enforce_financial_draft(spec: ToolSpec, params: dict) -> dict:
    """FORCE financial writes to DRAFT (T-05-07-01).

    The aggregator seam is verb-agnostic and passes ``params`` to the Tool Router
    verbatim — so unlike the direct publishing adapters (webflow ``isDraft:true``,
    beehiiv ``status:"draft"``), there is no provider module to host a draft-force.
    This cross-cutting rule supplies the in-code FORCE counterpart, gated by
    ``category == FINANCIAL`` (currently only ``xero_create_invoice``) rather than by
    provider, so the seam stays generic: a financial write is NEVER auto-finalised.

    Any caller-supplied non-DRAFT ``Status`` (e.g. ``AUTHORISED``, ``SUBMITTED``) is
    rejected loudly — an agent trying to finalise a financial document is a real
    signal, not something to silently coerce. Otherwise ``Status: DRAFT`` is injected.
    Returns a new dict; never mutates the caller's params. The approval gate
    (payload-hash bound) remains the primary control; this is defence-in-depth.
    """
    if spec.category != ToolCategory.FINANCIAL:
        return params
    requested = params.get("Status")
    if requested is not None and str(requested).upper() != "DRAFT":
        raise ValueError(
            "composio financial write: refusing non-DRAFT "
            f"Status={requested!r} — POC financial writes are DRAFT-only "
            "(never auto-finalised or authorised)"
        )
    return {**params, "Status": "DRAFT"}


def composio_adapter(spec: ToolSpec, params: dict, *, credential: str | None) -> dict:
    """Execute one Composio read through the managed-auth Tool Router.

    ``credential`` is the resolved ``COMPOSIO_API_KEY`` (resolved only inside
    ``execute()``, never logged/returned by the engine — D-02). The engine
    short-circuits to the deterministic stub before reaching this adapter when the
    credential is absent (D-11), so a credential is normally present here; the
    defensive ``None`` guard returns ``None`` so the engine still degrades cleanly.

    The read flow (RESEARCH A2 — confirm ``session.execute`` at impl with a live key):
      composio = Composio(api_key=credential)
      session  = composio.create(user_id=<resource_bindings.user_id>)
      schema   = aggregate_schema.fetch_runtime_schema(spec, session=session)  # D-04
      result   = session.execute(tool=<tool_slug>, arguments=params)
    """
    if credential is None:
        return None  # type: ignore[return-value]  # defensive; engine stubs before here

    # T-05-07-01: force financial writes to DRAFT BEFORE the SDK import, so the
    # non-DRAFT rejection path is exercisable in the default lane (no composio SDK).
    params = _enforce_financial_draft(spec, params)

    # LAZY SDK import — keeps the module import-safe (and the registration reachable)
    # without the composio package installed in the default lane.
    from composio import Composio  # noqa: PLC0415

    bindings = spec.resource_bindings or {}
    user_id = bindings.get("user_id", "mesh-tenant-example")
    tool_slug = bindings.get("tool_slug", spec.name)

    composio = Composio(api_key=credential)
    session = composio.create(user_id=user_id)

    # Feed the validator's aggregate branch the runtime provider schema (D-04). A
    # missing schema NEVER blocks the call; we record it for completeness and could
    # validate params against it here when present.
    runtime_schema = aggregate_schema.fetch_runtime_schema(spec, session=session)

    raw: Any = session.execute(tool=tool_slug, arguments=params)

    return {
        "tool": spec.name,
        "provider": spec.provider,
        "category": spec.category.value,
        "aggregator": "composio",
        "result": raw,
        "runtime_schema_present": runtime_schema is not None,
    }


# Register at import time under the aggregator-name key adapter_key_for produces.
register("composio", composio_adapter)
