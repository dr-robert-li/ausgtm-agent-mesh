"""Cal.com direct adapter (05-04, TOOL-03, D-07).

ONE dispatcher registered under provider key ``calcom`` (04-03 invariant). The two
Cal.com tools — ``calcom_list_bookings`` (read) and ``calcom_create_booking``
(approval-gated write) — share ``provider: calcom``, so this module registers EXACTLY
ONE adapter that routes by ``spec.name`` internally via ``_CALCOM_OPS`` — NOT one
registration per op under the same provider key (last-wins would silently make the read
or write unreachable, the canonical multi-op collision defect — RESEARCH Pitfall 3).

Transport (no SDK):
- Cal.com API v2 is called over the CORE ``httpx`` dependency; there is NO Cal.com
  Python package and no new dependency. The stub fallback is purely credential-driven
  (``credential is None`` -> ``None``); there is no ImportError branch because httpx is
  always importable.

Mandatory dated header (T-05-04-03):
- EVERY Cal.com v2 bookings call MUST send the dated header
  ``cal-api-version: 2026-05-01`` (pinned as ``_CAL_API_VERSION``) in addition to
  ``Authorization: Bearer <key>``. A missing or wrong version 400s every call, so the
  version is pinned as a module constant and asserted in a default-lane header test.

Degradation (D-11):
- ``credential is None`` -> the engine degrades to the stub BEFORE reaching the adapter,
  but each op still returns ``None`` defensively if reached. ``make test`` stays green
  and creds-free.

Approval (D-07 / SEC-01/02): ``_create_booking`` performs no gating of its own. It is
reached only after the worker's approval gate has approved the payload-hash-bound write;
the adapter is a pure executor and never self-gates.

Token + bindings (D-02): the API key arrives as ``credential`` and is never logged or
returned; the engine resolves it inside ``execute()`` and discards it on return. The
``event_type_id`` for the write comes from ``spec.resource_bindings`` (the manifest
binding), NOT from the environment — this adapter reads no environment variable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_mesh.tools.adapters import register

if TYPE_CHECKING:  # pragma: no cover - typing only
    from agent_mesh.tools.gateway import ToolSpec

# Cal.com API v2 host. Paths already include /v2 (GET/POST /v2/bookings) — do NOT
# concat a host that already carries /v2.
_CAL_API_BASE = "https://api.cal.com"

# MANDATORY dated API-version header. A missing/wrong value 400s every bookings call
# (T-05-04-03). Pinned here and asserted by a default-lane header test.
_CAL_API_VERSION = "2026-05-01"


def _headers(credential: str) -> dict[str, str]:
    """Both ops send Bearer auth + the mandatory dated cal-api-version header."""
    return {
        "Authorization": f"Bearer {credential}",
        "cal-api-version": _CAL_API_VERSION,
    }


def _list_bookings(
    spec: ToolSpec, params: dict[str, Any], *, credential: str | None
) -> dict[str, Any] | None:
    """READ: GET /v2/bookings -> ``{status, data:[...], pagination:{...}}``.

    Maps to ``schemas/calcom_list_bookings.output.schema.json`` (permissive: required
    ``status`` + ``data``; ``pagination`` passed through when present).
    """
    if credential is None:
        return None

    import httpx  # noqa: PLC0415 - CORE dep; kept local to mirror the lazy-adapter idiom

    resp = httpx.request(
        "GET",
        f"{_CAL_API_BASE}/v2/bookings",
        params=params or None,
        headers=_headers(credential),
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()

    result: dict[str, Any] = {
        "status": payload.get("status", "success"),
        "data": payload.get("data", []),
    }
    if "pagination" in payload:
        result["pagination"] = payload["pagination"]
    return result


def _create_booking(
    spec: ToolSpec, params: dict[str, Any], *, credential: str | None
) -> dict[str, Any] | None:
    """WRITE (approval-gated upstream): POST /v2/bookings -> ``{status, data:{id,uid,...}}``.

    Body: ``{start, eventTypeId, attendee}`` where ``eventTypeId`` comes from
    ``spec.resource_bindings["event_type_id"]`` (the manifest binding) and ``attendee``
    from ``params["attendee"]``. Maps to
    ``schemas/calcom_create_booking.output.schema.json`` (required ``status`` +
    ``data.id``). Reached only after the worker approval gate; the adapter never gates.
    """
    if credential is None:
        return None

    import httpx  # noqa: PLC0415 - CORE dep; kept local to mirror the lazy-adapter idiom

    body = {
        "start": params["start"],
        "eventTypeId": spec.resource_bindings["event_type_id"],
        "attendee": params["attendee"],
    }
    resp = httpx.request(
        "POST",
        f"{_CAL_API_BASE}/v2/bookings",
        json=body,
        headers=_headers(credential),
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()

    return {
        "status": payload.get("status", "success"),
        "data": payload.get("data", {}),
    }


# spec.name -> op. The SINGLE dispatcher routes by spec.name; registering one op per
# provider key would last-wins-collide and make the other op unreachable (Pitfall 3).
_CALCOM_OPS = {
    "calcom_list_bookings": _list_bookings,
    "calcom_create_booking": _create_booking,
}


def calcom_adapter(
    spec: ToolSpec, params: dict[str, Any], *, credential: str | None
) -> dict[str, Any] | None:
    """The ONE ``calcom`` dispatcher — routes by ``spec.name`` to the matching op."""
    return _CALCOM_OPS[spec.name](spec, params, credential=credential)


# Register EXACTLY ONCE under the provider key (04-03: registry keyed on spec.provider;
# execute() dispatches get_adapter(adapter_key_for(spec))="calcom").
register("calcom", calcom_adapter)
