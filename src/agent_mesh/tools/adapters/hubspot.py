"""HubSpot direct adapter (04-05, TOOL-01, D-07).

ONE dispatcher registered under provider key ``hubspot`` (04-03 invariant). The
two HubSpot tools (``hubspot_lookup_company`` read + ``hubspot_create_deal``
approval-gated write) share ``provider: hubspot``, so this module registers EXACTLY
ONE adapter that routes by ``spec.name`` internally via ``_HS_OPS`` — NOT one
registration per op under the same provider key (last-wins would silently make the
read or write unreachable, an SC-1 defect).

Degradation (D-11):
- ``credential is None`` -> the engine degrades to the stub BEFORE reaching the
  adapter, but each op still returns ``None`` defensively if reached.
- the SDK (``hubspot-api-client``, the ``hubspot`` import) is an OPT-IN ``tools``
  extra and is NOT installed in the default lane. Each op lazy-imports
  ``from hubspot import HubSpot`` INSIDE the function and degrades to ``None`` on
  ``ImportError`` so this module stays importable and the engine stubs cleanly when
  the SDK is absent (even if a non-None credential is supplied — keeping the
  default-suite leak test green without the SDK).

Approval (D-07 / SEC-01/02): ``_create_deal`` performs no gating of its own. It is
reached only after the worker's approval gate (``runner._resume_after_approval``)
has approved the payload-hash-bound write; the adapter is a pure executor.

Token (D-02): the bearer token is received as ``credential`` and is never logged or
returned; the engine resolves it inside ``execute()`` and discards it on return.

Package-legitimacy gate (T-04-05-SC): ``hubspot-api-client>=12,<13`` was verified
official on PyPI (publisher HubSpot; home github.com/HubSpot/hubspot-api-python) and
operator-approved 2026-06-06 before this module was authored. The import path is
``from hubspot import HubSpot`` (the package installs the ``hubspot`` module).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_mesh.tools.adapters import register

if TYPE_CHECKING:  # pragma: no cover - typing only
    from agent_mesh.tools.gateway import ToolSpec


def _lookup_company(
    spec: ToolSpec, params: dict[str, Any], *, credential: str | None
) -> dict[str, Any] | None:
    """READ: HubSpot CRM Search API -> output-schema-shaped records.

    Maps to ``schemas/hubspot_lookup_company.output.schema.json``:
    ``{"records": [{"id": <str>, "properties": <obj>}, ...]}`` (top-level
    ``additionalProperties:false`` — emit ONLY ``records``).
    """
    if credential is None:
        return None
    try:
        from hubspot import HubSpot
        from hubspot.crm.companies import PublicObjectSearchRequest
    except ImportError:
        # SDK not installed (opt-in tools extra) -> degrade to the engine stub (D-11).
        return None

    client = HubSpot(access_token=credential)
    object_type = params.get("object_type", "companies")
    search_request = PublicObjectSearchRequest(
        query=params["query"],
        limit=params.get("limit", 5),
    )
    # Route by the requested object type (companies | contacts); both expose the
    # same search_api.do_search shape.
    search_api = getattr(client.crm, object_type).search_api
    res = search_api.do_search(public_object_search_request=search_request)

    records = [
        {"id": str(obj.id), "properties": obj.properties or {}}
        for obj in (res.results or [])
    ]
    return {"records": records}


def _create_deal(
    spec: ToolSpec, params: dict[str, Any], *, credential: str | None
) -> dict[str, Any] | None:
    """WRITE (approval-gated upstream): HubSpot CRM objects API -> create a deal.

    Maps to ``schemas/hubspot_create_deal.output.schema.json``:
    ``{"deal_id": <str>, "status": <str>, "pipeline_id"?: <str>}`` (top-level
    ``additionalProperties:false``). Reached only after the worker approval gate.
    Writes hit a HubSpot dev/test SANDBOX (resource_bindings.pipeline_id) — never
    production (T-04-05-01).
    """
    if credential is None:
        return None
    try:
        from hubspot import HubSpot
        from hubspot.crm.deals import SimplePublicObjectInputForCreate
    except ImportError:
        return None

    client = HubSpot(access_token=credential)
    properties: dict[str, Any] = {
        "dealname": params["deal_name"],
        "dealstage": params["stage"],
    }
    if params.get("amount") is not None:
        properties["amount"] = str(params["amount"])
    pipeline_id = spec.resource_bindings.get("pipeline_id")
    if pipeline_id:
        properties["pipeline"] = pipeline_id

    deal = client.crm.deals.basic_api.create(
        simple_public_object_input_for_create=SimplePublicObjectInputForCreate(
            properties=properties
        )
    )

    result: dict[str, Any] = {"deal_id": str(deal.id), "status": "created"}
    if pipeline_id:
        result["pipeline_id"] = str(pipeline_id)
    return result


# spec.name -> op. The SINGLE dispatcher routes by spec.name; registering one op per
# provider key would last-wins-collide and make the other op unreachable (SC-1).
_HS_OPS = {
    "hubspot_lookup_company": _lookup_company,
    "hubspot_create_deal": _create_deal,
}


def hubspot_adapter(
    spec: ToolSpec, params: dict[str, Any], *, credential: str | None
) -> dict[str, Any] | None:
    """The ONE ``hubspot`` dispatcher — routes by ``spec.name`` to the matching op."""
    return _HS_OPS[spec.name](spec, params, credential=credential)


# Register EXACTLY ONCE under the provider key (04-03: registry keyed on
# spec.provider; execute() dispatches get_adapter(adapter_key_for(spec))="hubspot").
register("hubspot", hubspot_adapter)
