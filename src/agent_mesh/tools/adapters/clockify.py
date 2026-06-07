"""Clockify direct adapter (05-05, TOOL-03, D-02/D-11) — READ-ONLY this phase.

ONE dispatcher registered under provider key ``clockify`` (04-03 invariant). Clockify
exposes a single op this phase — ``clockify_read_time_entries`` (read) — but the
dispatcher routes by ``spec.name`` via ``_CLOCKIFY_OPS`` exactly like the multi-op
adapters (HubSpot/GWS), so a future second op slots in without a register-per-op
last-wins collision. 05-01 froze: no Clockify write op this phase.

httpx, NOT an SDK (RESEARCH "Clockify"):
- ``httpx`` is a CORE dependency, so there is NO opt-in extra and NO lazy
  ``ImportError`` degrade branch (contrast HubSpot's SDK extra). The only degrade
  path is ``credential is None`` -> ``None`` -> the engine stubs (D-11). In practice
  the engine stubs BEFORE reaching the adapter when the secret is absent; the
  ``None`` guard is the defensive mirror of that.

The READ endpoint needs BOTH segments (RESEARCH):
    GET /workspaces/{workspaceId}/user/{userId}/time-entries
``workspace_id`` and ``user_id`` are resolved from ``spec.resource_bindings``
(operator-bound, NOT free agent input — T-05-05-02). The raw Clockify response is a
BARE ARRAY; the adapter wraps it under ``{"entries": [...]}`` to match
``schemas/clockify_read_time_entries.output.schema.json`` (an OBJECT, never a bare
list — the live-lane ``result.get("stub")`` assertion would raise on a list).

Auth (RESEARCH): the ``X-Api-Key`` header carries the resolved key — NOT a Bearer
token. Subdomain workspaces need a subdomain-specific key (see the credential doc).

Token (D-02): the key arrives as ``credential`` and is never logged or returned; the
engine resolves it inside ``execute()`` and discards it on return. The adapter reads
NO ``os.getenv`` — the key only ever arrives via the ``credential`` arg.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from agent_mesh.tools.adapters import register

if TYPE_CHECKING:  # pragma: no cover - typing only
    from agent_mesh.tools.gateway import ToolSpec

# Clockify API v1 base. The two-segment path is built per call.
_CLOCKIFY_API_BASE = "https://api.clockify.me/api/v1"

# Pass-through query filters the input schema permits (D-05). Absent keys are dropped.
_QUERY_PARAMS = ("start", "end", "page-size")


def _read_time_entries(
    spec: ToolSpec, params: dict[str, Any], *, credential: str | None
) -> dict[str, Any] | None:
    """READ: Clockify time entries -> output-schema-shaped ``{"entries": [...]}``.

    Maps to ``schemas/clockify_read_time_entries.output.schema.json``: the raw
    Clockify response is a BARE ARRAY of entry objects, wrapped here under
    ``entries`` (the schema is an object, never a bare list).
    """
    if credential is None:
        # Engine stubs before reaching here when the key is absent (D-11); this
        # defensive guard returns None so the engine still degrades cleanly.
        return None

    workspace_id = spec.resource_bindings["workspace_id"]
    user_id = spec.resource_bindings["user_id"]
    url = (
        f"{_CLOCKIFY_API_BASE}/workspaces/{workspace_id}"
        f"/user/{user_id}/time-entries"
    )
    query = {k: params[k] for k in _QUERY_PARAMS if params.get(k) is not None}

    resp = httpx.get(
        url,
        headers={"X-Api-Key": credential},  # Clockify uses X-Api-Key, NOT Bearer.
        params=query or None,
        timeout=30,
    )
    resp.raise_for_status()
    entries = resp.json()
    if not isinstance(entries, list):
        # Defensive: Clockify returns a bare array; anything else is wrapped as-is so
        # the output stays an object the schema/quarantine path can reason about.
        entries = [entries]
    return {"entries": entries}


# spec.name -> op. The SINGLE dispatcher routes by spec.name; one register() per op
# under the same provider key would last-wins-collide (SC-1). The key MUST match the
# manifest op name 05-01 froze.
_CLOCKIFY_OPS = {
    "clockify_read_time_entries": _read_time_entries,
}


def clockify_adapter(
    spec: ToolSpec, params: dict[str, Any], *, credential: str | None
) -> dict[str, Any] | None:
    """The ONE ``clockify`` dispatcher — routes by ``spec.name`` to the matching op."""
    return _CLOCKIFY_OPS[spec.name](spec, params, credential=credential)


# Register EXACTLY ONCE under the provider key (04-03: registry keyed on spec.provider;
# execute() dispatches get_adapter(adapter_key_for(spec))="clockify").
register("clockify", clockify_adapter)
