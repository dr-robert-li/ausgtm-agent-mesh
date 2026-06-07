"""Bitscale direct adapter (05-03, TOOL-03, D-07) — the 5th real direct adapter.

ONE dispatcher registered under provider key ``bitscale`` (04-03 invariant). The
three Bitscale tools (``bitscale_list_grids`` read + ``bitscale_get_workspace`` read +
``bitscale_run_grid`` approval-gated write) all share ``provider: bitscale``, so this
module registers EXACTLY ONE adapter that routes by ``spec.name`` internally via
``_BITSCALE_OPS`` — NOT one registration per op under the same provider key (last-wins
would silently make two of the three ops unreachable, an SC-1 defect).

Transport: core ``httpx`` against ``https://api.bitscale.ai/api/v1`` — NO SDK, NO new
dependency (live-curl validated). Auth header is ``X-API-Key: <key>`` (NOT a bearer
token; ``api-key``/``apikey`` 401 — only ``X-API-Key``/``x-api-key`` return 200).

Degradation (D-11): ``httpx`` is a CORE dependency, so there is no opt-in-SDK
ImportError branch. The sole degrade path is ``credential is None`` -> each op returns
``None`` so the engine falls back to the deterministic stub. ``make test`` stays green
and creds-free.

CREDIT-SAFETY (LOCKED): ``bitscale_run_grid`` appends a row + triggers enrichment on
the client's REAL ``australiagtm.com`` workspace and CONSUMES PAID CREDITS. It is
approval-gated upstream (manifest ``category: write`` -> ``approval_required: true``,
05-01) and is NEVER exercised in the live lane — its mapping is proven only through the
default-lane fake-httpx test + the upstream approval gate, never a live call.

Approval (D-07 / SEC-01/02): ``_run_grid`` performs NO gating of its own. It is reached
only after the worker approval gate (``runner._resume_after_approval``) has approved the
payload-hash-bound write; the adapter is a pure executor.

Token (D-02): the key is received as ``credential`` and is never logged, never returned,
and never read from the environment here; the engine resolves it inside ``execute()``
and discards it on return. This module does not read ``os`` env vars (keeping the
credential-docs guard scan clean).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_mesh.tools.adapters import register

if TYPE_CHECKING:  # pragma: no cover - typing only
    from agent_mesh.tools.gateway import ToolSpec

_BASE_URL = "https://api.bitscale.ai/api/v1"


def _headers(credential: str) -> dict[str, str]:
    """Build the Bitscale auth header — ``X-API-Key`` (the verified header form)."""
    return {"X-API-Key": credential, "Accept": "application/json"}


def _list_grids(
    spec: ToolSpec, params: dict[str, Any], *, credential: str | None
) -> dict[str, Any] | None:
    """READ (credit-free): GET /grids -> ``{"grids":[...]}`` (output-schema-shaped).

    Maps to ``schemas/bitscale_list_grids.output.schema.json`` — emit ``{"grids": [...]}``
    with each grid's ``id`` coerced to a string (the schema types ``id`` as ``string``).
    """
    if credential is None:
        return None
    import httpx  # noqa: PLC0415 - httpx is CORE; local import mirrors the adapter idiom

    resp = httpx.request(
        "GET", f"{_BASE_URL}/grids", headers=_headers(credential), timeout=30
    )
    resp.raise_for_status()
    payload = resp.json()

    raw_grids = payload.get("grids", payload) if isinstance(payload, dict) else payload
    grids: list[dict[str, Any]] = []
    for raw in raw_grids or []:
        if not isinstance(raw, dict):
            continue
        grid = dict(raw)
        if "id" in grid and grid["id"] is not None:
            grid["id"] = str(grid["id"])
        grids.append(grid)
    return {"grids": grids}


def _get_workspace(
    spec: ToolSpec, params: dict[str, Any], *, credential: str | None
) -> dict[str, Any] | None:
    """READ (credit-free): GET /workspace -> the permissive workspace-details object.

    Maps to ``schemas/bitscale_get_workspace.output.schema.json`` (permissive,
    ``additionalProperties: true``) — return the provider object as-is.
    """
    if credential is None:
        return None
    import httpx  # noqa: PLC0415

    resp = httpx.request(
        "GET", f"{_BASE_URL}/workspace", headers=_headers(credential), timeout=30
    )
    resp.raise_for_status()
    payload = resp.json()
    return payload if isinstance(payload, dict) else {"raw": payload}


def _run_grid(
    spec: ToolSpec, params: dict[str, Any], *, credential: str | None
) -> dict[str, Any] | None:
    """WRITE (approval-gated upstream, CREDIT-CONSUMING): POST /grids/{grid_id}/run.

    Body ``{"inputs": params["inputs"]}`` — appends a row + triggers enrichment, which
    spends the client's paid credits. ``grid_id`` comes from
    ``spec.resource_bindings["grid_id"]`` (falling back to ``params``). Reached only
    after the upstream approval gate; NEVER called in the live lane (credit-safety).
    Maps to ``schemas/bitscale_run_grid.output.schema.json`` (minimal/permissive).
    """
    if credential is None:
        return None
    import httpx  # noqa: PLC0415

    grid_id = (spec.resource_bindings or {}).get("grid_id") or params.get("grid_id")
    body = {"inputs": params.get("inputs", {})}
    resp = httpx.request(
        "POST",
        f"{_BASE_URL}/grids/{grid_id}/run",
        headers=_headers(credential),
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if isinstance(payload, dict):
        result = dict(payload)
        if "id" in result and result["id"] is not None:
            result["id"] = str(result["id"])
        return result
    return {"raw": payload}


# spec.name -> op. The SINGLE dispatcher routes by spec.name; registering one op per
# provider key would last-wins-collide and make the other ops unreachable (SC-1). The
# keys MUST match the manifest op names 05-01 froze.
_BITSCALE_OPS = {
    "bitscale_list_grids": _list_grids,
    "bitscale_get_workspace": _get_workspace,
    "bitscale_run_grid": _run_grid,
}


def bitscale_adapter(
    spec: ToolSpec, params: dict[str, Any], *, credential: str | None
) -> dict[str, Any] | None:
    """The ONE ``bitscale`` dispatcher — routes by ``spec.name`` to the matching op."""
    return _BITSCALE_OPS[spec.name](spec, params, credential=credential)


# Register EXACTLY ONCE under the provider key (04-03: registry keyed on spec.provider;
# execute() dispatches get_adapter(adapter_key_for(spec))="bitscale").
register("bitscale", bitscale_adapter)
