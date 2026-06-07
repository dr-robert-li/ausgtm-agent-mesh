"""Webflow direct adapter (05-02, TOOL-03, D-07).

ONE dispatcher registered under provider key ``webflow`` (04-03 invariant). The two
Webflow tools (``webflow_list_cms_items`` read + ``webflow_create_cms_item``
approval-gated publishing write) share ``provider: webflow``, so this module exposes
EXACTLY ONE adapter that routes by ``spec.name`` internally via ``_WEBFLOW_OPS`` — NOT
one registration per op under the same provider key (last-wins would silently make the
read or the write unreachable, an SC-1 defect).

Transport (D-11, no new dependency): the Webflow Data API v2 is called over the CORE
``httpx`` dependency — there is NO SDK and NO lazy ImportError branch. The ONLY stub
path is ``credential is None`` -> return ``None`` so the engine degrades to the
deterministic gateway stub. With the token absent ``make test`` stays green and
creds-free.

Endpoints (Data API v2 — host ``https://api.webflow.com``, paths already INCLUDE
``/v2``; never concat ``/v2/v2``):
- READ  GET  ``/v2/collections/{collection_id}/items``  -> ``{items, pagination}``
- WRITE POST ``/v2/collections/{collection_id}/items``  -> HTTP 202 ``{id, fieldData, ...}``

Draft-only publish (T-05-02-01): ``_create_cms_item`` ALWAYS forces ``isDraft: True``
in the POST body — even if a caller passes ``isDraft: False`` — so a create never
publishes a live CMS item; it only stages a draft.

Approval (D-07 / T-05-02-02): ``_create_cms_item`` performs no gating of its own. The
manifest marks ``webflow_create_cms_item`` ``category: publishing`` /
``approval_required: true``, so it is reached only after the worker's approval gate has
approved the payload-hash-bound write; the adapter is a pure executor.

Token (D-02 / T-05-02-03): the bearer token arrives as ``credential`` (resolved inside
``execute()``), is sent only as the ``Authorization`` header, and is never logged or
returned. The adapter reads NO ``os.getenv`` — the token is never sourced from the
environment here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_mesh.tools.adapters import register

if TYPE_CHECKING:  # pragma: no cover - typing only
    from agent_mesh.tools.gateway import ToolSpec

_API_BASE = "https://api.webflow.com"  # paths already carry /v2; do NOT add it twice.


def _headers(credential: str) -> dict[str, str]:
    """Bearer auth headers for the Data API v2. The token is never logged/returned."""
    return {
        "Authorization": f"Bearer {credential}",
        "Accept": "application/json",
    }


def _list_cms_items(
    spec: ToolSpec, params: dict[str, Any], *, credential: str | None
) -> dict[str, Any] | None:
    """READ: list a collection's CMS items -> output-schema-shaped ``{items, pagination}``.

    Maps to ``schemas/webflow_list_cms_items.output.schema.json``. ``collection_id``
    comes from ``spec.resource_bindings`` (never from params). Pagination is forwarded
    only when present (the schema types ``pagination`` as a non-nullable object).
    """
    if credential is None:
        return None
    import httpx  # noqa: PLC0415 - core dep; local import mirrors the adapter idiom.

    collection_id = spec.resource_bindings["collection_id"]
    query: dict[str, Any] = {}
    if params.get("offset") is not None:
        query["offset"] = params["offset"]
    if params.get("limit") is not None:
        query["limit"] = params["limit"]

    resp = httpx.get(
        f"{_API_BASE}/v2/collections/{collection_id}/items",
        headers=_headers(credential),
        params=query or None,
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()

    result: dict[str, Any] = {"items": body.get("items", [])}
    pagination = body.get("pagination")
    if pagination is not None:
        result["pagination"] = pagination
    return result


def _create_cms_item(
    spec: ToolSpec, params: dict[str, Any], *, credential: str | None
) -> dict[str, Any] | None:
    """WRITE (approval-gated upstream): create a CMS item, ALWAYS as a draft.

    Maps to ``schemas/webflow_create_cms_item.output.schema.json`` (the HTTP 202
    staged-item body ``{id, fieldData, ...}``). The POST body forces ``isDraft: True``
    unconditionally (T-05-02-01) — a caller-supplied ``isDraft: False`` is ignored, so
    a create never publishes. Reached only after the worker approval gate (T-05-02-02).
    """
    if credential is None:
        return None
    import httpx  # noqa: PLC0415 - core dep; local import mirrors the adapter idiom.

    collection_id = spec.resource_bindings["collection_id"]
    # ALWAYS draft — never honour a caller's isDraft:False (T-05-02-01).
    payload = {"isDraft": True, "fieldData": params["fieldData"]}

    resp = httpx.post(
        f"{_API_BASE}/v2/collections/{collection_id}/items",
        headers=_headers(credential),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()  # accept the 202 staged-item response
    body = resp.json()

    if not isinstance(body, dict) or body.get("id") is None:
        raise ValueError(
            "webflow_create_cms_item: unexpected response shape (missing 'id'); "
            "refusing to map"
        )
    result: dict[str, Any] = {"id": str(body["id"])}
    for key in ("fieldData", "isDraft", "lastPublished", "lastUpdated", "createdOn"):
        if key in body and body[key] is not None:
            result[key] = body[key]
    return result


# spec.name -> op. The SINGLE dispatcher routes by spec.name; one op per provider key
# would last-wins-collide and make the other op unreachable (SC-1).
_WEBFLOW_OPS = {
    "webflow_list_cms_items": _list_cms_items,
    "webflow_create_cms_item": _create_cms_item,
}


def webflow_adapter(
    spec: ToolSpec, params: dict[str, Any], *, credential: str | None
) -> dict[str, Any] | None:
    """The ONE ``webflow`` dispatcher — routes by ``spec.name`` to the matching op."""
    return _WEBFLOW_OPS[spec.name](spec, params, credential=credential)


register("webflow", webflow_adapter)
