"""Runtime aggregate-schema fetch + in-process cache (D-04 / RESEARCH Pattern 3).

Aggregator providers (Composio, Nango) expose hundreds of per-tool input JSON
Schemas that we cannot hand-author into the manifest (D-04). Instead the aggregate
validation branch (04-02) validates against a *runtime* provider-supplied schema:

- **Composio**: ``session.tools()`` returns tool defs carrying an input JSON Schema.
  This module looks the tool up by ``spec.name`` and returns its schema.
- **Nango**: the REST proxy exposes NO per-tool schema, so the runtime schema is
  ``None`` -> the aggregate validation branch is permissive (D-04: a missing runtime
  schema NEVER blocks for an aggregate tool — its schema simply arrives later, or
  not at all).

The result (INCLUDING ``None``) is cached in a module-global dict keyed by
``(provider, tool_name)``, mirroring the ``orchestrator._PG_SAVER`` process-cache
idiom: build once, reuse for the life of the process. A second ``fetch_runtime_schema``
for the same tool does NOT re-query the provider session.

The module is import-safe WITHOUT the ``composio`` SDK: the SDK is never imported
here (the caller passes a live ``session``); we only call duck-typed ``.tools()``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from agent_mesh.tools.gateway import ToolSpec

# (provider, tool_name) -> runtime input JSON Schema (or None when the provider
# exposes none / the tool was not found). Module-global, process-lived; tests
# clear it between cases for isolation (it caches None too, so a stale None would
# otherwise mask a later positive fetch).
_SCHEMA_CACHE: dict[tuple[str, str], dict | None] = {}

# integration_style values that carry a per-tool runtime schema via a Composio
# session. Nango (and the bare aggregate_mcp style) expose none -> permissive None.
_COMPOSIO_STYLES = {"composio_aggregator"}


def _extract_input_schema(tool_def: Any) -> dict | None:
    """Pull the input JSON Schema off a Composio tool def.

    Composio is a 0.x SDK with documented key churn (RESEARCH A1: the exact key
    on the tool def — ``input_parameters`` vs ``inputSchema`` — is not pinned from
    docs and is confirmed with one live ``session.tools()`` dump at implementation).
    Probe the documented candidates in order; return ``None`` if none is present so
    the call degrades to permissive rather than raising.
    """
    if tool_def is None:
        return None
    # Tool defs may be dict-like or attribute objects depending on the SDK build.
    for key in ("input_parameters", "inputSchema", "input_schema", "parameters"):
        if isinstance(tool_def, dict):
            val = tool_def.get(key)
        else:
            val = getattr(tool_def, key, None)
        if isinstance(val, dict):
            return val
    return None


def _tool_name(tool_def: Any) -> str | None:
    """Read the identifying name/slug off a Composio tool def (dict or object)."""
    for key in ("name", "slug"):
        if isinstance(tool_def, dict):
            val = tool_def.get(key)
        else:
            val = getattr(tool_def, key, None)
        if isinstance(val, str):
            return val
    return None


def fetch_runtime_schema(spec: ToolSpec, *, session: Any = None) -> dict | None:
    """Return the runtime input JSON Schema for ``spec``, cached per (provider, tool).

    - Composio-style spec WITH a live ``session``: scan ``session.tools()`` for the
      tool whose name/slug matches ``spec.name`` and return its input JSON Schema
      (or ``None`` if not found / no schema key present).
    - Nango-style (and any non-Composio aggregate) spec, or a Composio spec with no
      session: return ``None`` (the proxy exposes no per-tool schema -> permissive).

    The result is cached (including ``None``) so a second call for the same tool does
    NOT re-query ``session.tools()``. Import-safe without the composio SDK: the SDK is
    never imported here; only the caller-supplied ``session`` is duck-typed.
    """
    key = (spec.provider, spec.name)
    if key in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[key]

    schema: dict | None = None
    if spec.integration_style in _COMPOSIO_STYLES and session is not None:
        try:
            tool_defs = session.tools()
        except Exception:  # noqa: BLE001 - a provider error must not block the call (D-04)
            tool_defs = []
        for tool_def in tool_defs or []:
            if _tool_name(tool_def) == spec.name:
                schema = _extract_input_schema(tool_def)
                break

    _SCHEMA_CACHE[key] = schema
    return schema
