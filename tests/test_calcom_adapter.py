"""Default-lane (creds-free, SDK-free) tests for the Cal.com direct adapter (05-04).

Proves the 04-03 dispatch contract for the ``calcom`` provider:
- ONE dispatcher under key ``calcom`` routing by ``spec.name`` to DISTINCT ops
  (collision regression guard against last-wins register-per-op — Pitfall 3).
- ``get_adapter("calcom")`` is reachable via import-time registration once this module
  exists (the wave-2 half of the 04-03 lazy-import-on-miss seam).
- creds-absent degrades to ``None`` so the engine stubs (D-11). httpx is CORE — there is
  NO ImportError branch to test.
- BOTH ops send the MANDATORY ``cal-api-version: 2026-05-01`` header + Bearer auth
  (captured off a fake ``httpx.request``).
- the read maps to ``schemas/calcom_list_bookings.output.schema.json`` and the write
  response maps to ``schemas/calcom_create_booking.output.schema.json`` (the write
  output-quarantine guard — the only place the create shape is checked this milestone).

No real Cal.com call happens: ``httpx.request`` is monkeypatched to a spy that records
the headers and returns a fake response.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

from agent_mesh.contracts.enums import ToolCategory
from agent_mesh.tools import adapters
from agent_mesh.tools.adapters import calcom as cc
from agent_mesh.tools.gateway import ToolSpec

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


# Registry isolation — _REGISTRY is module-global; snapshot/restore per test so a fake
# registered in one test never leaks into another (mirrors test_hubspot_adapter).
@pytest.fixture(autouse=True)
def _isolate_registry():
    saved = dict(adapters._REGISTRY)
    try:
        yield
    finally:
        adapters._REGISTRY.clear()
        adapters._REGISTRY.update(saved)


def _spec(name: str, *, category: ToolCategory, approval: bool) -> ToolSpec:
    return ToolSpec(
        name=name,
        provider="calcom",
        category=category,
        description="",
        approval_required=approval,
        credential_secret_name="CALCOM_API_KEY",
        resource_bindings={"event_type_id": 12345},
        integration_style="direct_api",
    )


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:  # no-op — the fake call always "succeeds"
        return None

    def json(self) -> dict:
        return self._payload


def _install_spy(monkeypatch, payload: dict) -> list[dict]:
    """Monkeypatch ``httpx.request`` (the same module object the adapter imports) with a
    spy that records each call's kwargs and returns ``_FakeResponse(payload)``."""
    calls: list[dict] = []

    def spy(method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        return _FakeResponse(payload)

    monkeypatch.setattr(httpx, "request", spy)
    return calls


def test_creds_absent_degrades_to_none():
    """credential=None -> each op returns None (engine then stubs, D-11). No httpx call."""
    read_spec = _spec("calcom_list_bookings", category=ToolCategory.READ, approval=False)
    write_spec = _spec("calcom_create_booking", category=ToolCategory.WRITE, approval=True)

    assert cc.calcom_adapter(read_spec, {}, credential=None) is None
    assert cc.calcom_adapter(write_spec, {"start": "x", "attendee": {}}, credential=None) is None


def test_single_dispatcher_routes_distinct_ops(monkeypatch):
    """The collision guard: spec.name "calcom_list_bookings" vs "calcom_create_booking"
    reach DIFFERENT ops through the single calcom_adapter dispatcher (not last-wins)."""
    seen: list[str] = []

    def list_spy(spec, params, *, credential):
        seen.append("list")
        return {"status": "success", "data": []}

    def create_spy(spec, params, *, credential):
        seen.append("create")
        return {"status": "success", "data": {"id": 1}}

    monkeypatch.setitem(cc._CALCOM_OPS, "calcom_list_bookings", list_spy)
    monkeypatch.setitem(cc._CALCOM_OPS, "calcom_create_booking", create_spy)

    read_spec = _spec("calcom_list_bookings", category=ToolCategory.READ, approval=False)
    write_spec = _spec("calcom_create_booking", category=ToolCategory.WRITE, approval=True)

    cc.calcom_adapter(read_spec, {}, credential="tok")
    cc.calcom_adapter(write_spec, {"start": "x", "attendee": {}}, credential="tok")

    assert seen == ["list", "create"]  # distinct ops, in order — no collision


def test_get_adapter_calcom_is_reachable():
    """get_adapter("calcom") returns the registered dispatcher via import-time
    registration once this module exists — the wave-2 half of the 04-03 seam.

    Deterministic against sys.modules caching: drop the cached module + registry key so
    get_adapter's import-on-miss re-runs the module body (re-firing register())."""
    sys.modules.pop("agent_mesh.tools.adapters.calcom", None)
    adapters._REGISTRY.pop("calcom", None)

    fn = adapters.get_adapter("calcom")

    assert callable(fn)
    assert fn.__name__ == "calcom_adapter"


def test_both_ops_send_cal_api_version_header(monkeypatch):
    """BOTH ops MUST send cal-api-version: 2026-05-01 + Bearer auth (T-05-04-03).
    Capture the headers the fake transport receives and assert the version + Bearer."""
    # Read: payload conforms to the list-bookings output shape.
    read_calls = _install_spy(monkeypatch, {"status": "success", "data": [], "pagination": {}})
    read_spec = _spec("calcom_list_bookings", category=ToolCategory.READ, approval=False)
    cc.calcom_adapter(read_spec, {"status": "upcoming"}, credential="cal_secret")

    assert len(read_calls) == 1
    read_headers = read_calls[0]["headers"]
    assert read_headers["cal-api-version"] == "2026-05-01"
    assert read_headers["Authorization"] == "Bearer cal_secret"

    # Write: payload conforms to the create-booking output shape.
    write_calls = _install_spy(monkeypatch, {"status": "success", "data": {"id": 99, "uid": "u"}})
    write_spec = _spec("calcom_create_booking", category=ToolCategory.WRITE, approval=True)
    cc.calcom_adapter(
        write_spec,
        {"start": "2026-07-01T10:00:00Z", "attendee": {"name": "A", "email": "a@x.io", "timeZone": "UTC"}},
        credential="cal_secret",
    )

    assert len(write_calls) == 1
    write_headers = write_calls[0]["headers"]
    assert write_headers["cal-api-version"] == "2026-05-01"
    assert write_headers["Authorization"] == "Bearer cal_secret"


def test_list_bookings_maps_to_output_schema(monkeypatch):
    """The read maps the v2 response to the strict output schema shape
    {status, data:[...], pagination:{...}}."""
    payload = {
        "status": "success",
        "data": [
            {
                "id": 7,
                "uid": "abc",
                "title": "Intro call",
                "status": "accepted",
                "start": "2026-07-01T10:00:00Z",
                "end": "2026-07-01T10:30:00Z",
                "attendees": [{"name": "A", "email": "a@x.io"}],
                "eventTypeId": 12345,
            }
        ],
        "pagination": {"nextCursor": None, "hasMore": False},
    }
    _install_spy(monkeypatch, payload)

    read_spec = _spec("calcom_list_bookings", category=ToolCategory.READ, approval=False)
    result = cc.calcom_adapter(read_spec, {}, credential="tok")

    schema = json.loads((_SCHEMA_DIR / "calcom_list_bookings.output.schema.json").read_text())
    from jsonschema import Draft202012Validator

    Draft202012Validator(schema).validate(result)
    assert result["status"] == "success"
    assert result["data"][0]["id"] == 7
    assert result["pagination"] == {"nextCursor": None, "hasMore": False}


def test_create_booking_response_conforms_to_output_schema(monkeypatch):
    """Write output-quarantine guard: the create_booking response, after mapping,
    conforms to schemas/calcom_create_booking.output.schema.json. This is the ONLY place
    the write shape is checked this milestone (the live lane never runs the write)."""
    payload = {"status": "success", "data": {"id": 4321, "uid": "bk_x", "title": "Booked"}}
    _install_spy(monkeypatch, payload)

    write_spec = _spec("calcom_create_booking", category=ToolCategory.WRITE, approval=True)
    result = cc.calcom_adapter(
        write_spec,
        {"start": "2026-07-01T10:00:00Z", "attendee": {"name": "A", "email": "a@x.io", "timeZone": "UTC"}},
        credential="tok",
    )

    schema = json.loads((_SCHEMA_DIR / "calcom_create_booking.output.schema.json").read_text())
    from jsonschema import Draft202012Validator

    Draft202012Validator(schema).validate(result)
    assert result["status"] == "success"
    assert result["data"]["id"] == 4321
