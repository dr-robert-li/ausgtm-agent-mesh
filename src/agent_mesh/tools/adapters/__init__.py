"""Adapter-dispatch registry — the parallel-adapter seam (04-03).

This package is the load-bearing contract that lets every Wave-4 adapter plan
(04-05 HubSpot, 04-06 Google Workspace, 04-08 Composio/Nango) ship as an additive
own-file module instead of an edit to ``ToolGateway.execute()``. Without it, all
three would edit ``gateway.py`` and Wave 4 collapses to serial.

THE INVARIANT
-------------
    registration key == adapter module filename == lookup key

- A **direct** tool registers under ``spec.provider`` (``hubspot``, ``google_workspace``
  — unique across the direct adapters). ``hubspot.py`` calls ``register("hubspot", fn)``.
- An **aggregator** tool registers under its aggregator name derived from
  ``integration_style`` (``composio_aggregator`` -> ``composio``,
  ``nango_aggregator`` -> ``nango``). ``composio.py`` calls ``register("composio", fn)``.
- A provider exposing **multiple tools** (e.g. ``google_workspace`` has gmail/calendar/
  drive/...) registers **EXACTLY ONE** dispatcher under its provider key that routes by
  ``spec.name`` internally — NEVER one ``register()`` per op (last-wins would make most
  ops unreachable).

DISPATCH-KEY DERIVATION
-----------------------
``adapter_key_for(spec)`` is the single source of truth for the dispatch key:

    direct_api          -> spec.provider          (hubspot / google_workspace)
    composio_aggregator -> "composio"
    nango_aggregator    -> "nango"
    aggregate_mcp       -> spec.provider           (no adapter this phase -> import-miss -> stub)

``integration_style`` selects the validator branch (04-02) AND, for aggregators only,
the adapter key; it does NOT key direct-adapter dispatch (HubSpot and GWS are BOTH
``direct_api`` and would collide — ``provider`` disambiguates them).

LAZY-IMPORT-ON-MISS (the blocker fix)
-------------------------------------
Adapter modules call ``register()`` at import time, but no runtime path imports them.
``get_adapter(key)`` does import-on-miss: a registry miss attempts
``importlib.import_module(f"agent_mesh.tools.adapters.{key}")`` so the matching module
is loaded (firing its module-level ``register()``) the first time it is looked up. An
``ImportError`` (module absent / SDK not installed / unknown key) is swallowed and the
lookup returns ``None`` -> the engine degrades to the deterministic stub (D-11). This
mirrors observability.py's optional-dep lazy-import idiom.

ADAPTER CALL CONTRACT
---------------------
    adapter(spec: ToolSpec, params: dict, *, credential: str | None) -> dict

The adapter lazy-imports its own SDK, uses ``credential`` (never logged/returned by
the engine), and returns the SaaS result dict. When ``credential`` is ``None`` the
engine never reaches the adapter (it degrades to the stub before dispatch), so an
adapter may assume a credential is present — but defensive degradation is welcome.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from agent_mesh.tools.gateway import ToolSpec

# key -> adapter callable. Module-global; tests snapshot/restore it for isolation.
_REGISTRY: dict[str, Callable] = {}

# integration_style -> aggregator dispatch key. Only aggregators remap; every other
# style falls through to spec.provider in adapter_key_for.
_AGGREGATOR_KEY = {
    "composio_aggregator": "composio",
    "nango_aggregator": "nango",
}


def register(key: str, fn: Callable) -> None:
    """Register adapter ``fn`` under ``key`` (== module filename == lookup key)."""
    _REGISTRY[key] = fn


def get_adapter(key: str) -> Callable | None:
    """Return the adapter registered under ``key``, lazy-importing on a miss.

    On a registry miss, attempt to import ``agent_mesh.tools.adapters.{key}`` so a
    module that registers itself at import time is loaded the first time it is
    looked up. A missing/unimportable module degrades to ``None`` (D-11 stub).
    """
    if key not in _REGISTRY:
        try:
            importlib.import_module(f"agent_mesh.tools.adapters.{key}")
        except ImportError:
            return None
    return _REGISTRY.get(key)


def adapter_key_for(spec: "ToolSpec") -> str:
    """Derive the adapter dispatch key for ``spec`` (see module docstring).

    Aggregator styles map to their aggregator name; every other style (direct_api,
    aggregate_mcp, mcp_server) dispatches on ``spec.provider``.
    """
    return _AGGREGATOR_KEY.get(spec.integration_style, spec.provider)
