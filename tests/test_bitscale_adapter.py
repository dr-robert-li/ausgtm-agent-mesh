"""Default-lane (creds-free, network-free) tests for the Bitscale direct adapter (05-03).

Proves the 04-03 dispatch contract for the ``bitscale`` provider:
- ONE dispatcher under key ``bitscale`` routing by ``spec.name`` to THREE DISTINCT ops
  (collision regression guard against last-wins register-per-op).
- ``get_adapter("bitscale")`` is reachable via import-time registration (the wave-2
  half of the 04-03 lazy-import-on-miss seam).
- creds-absent degrades to ``None`` so the engine stubs (D-11). ``httpx`` is a CORE dep,
  so there is NO opt-in-SDK ImportError branch to test — the only degrade is
  ``credential is None``.
- the ``_list_grids`` read maps the provider response to the strict-ish output schema
  ``{"grids":[...]}`` with ``id`` coerced to a string.
- the ``_run_grid`` WRITE mapping is proven here against a FAKE httpx transport (NO real
  network, NO credit spend) — this is the ONLY place run_grid is exercised, and only
  against a fake. The live lane never touches it (credit-safety).

All httpx interaction is faked: ``httpx.request`` is monkeypatched so nothing hits the
real ``api.bitscale.ai`` and no credits are spent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from agent_mesh.contracts.enums import ToolCategory
from agent_mesh.tools import adapters
from agent_mesh.tools.adapters import bitscale as bs
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
        provider="bitscale",
        category=category,
        description="",
        approval_required=approval,
        credential_secret_name="BITSCALE_API_KEY",
        resource_bindings={"grid_id": "grid-test-1"},
        integration_style="direct_api",
    )


class _FakeResponse:
    """Minimal httpx.Response stand-in: no-op raise_for_status + a canned .json()."""

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


def test_creds_absent_degrades_to_none():
    """credential=None -> each of the THREE ops returns None (engine then stubs, D-11).

    No httpx call is made (the None guard returns before any network)."""
    read_grids = _spec("bitscale_list_grids", category=ToolCategory.READ, approval=False)
    read_ws = _spec("bitscale_get_workspace", category=ToolCategory.READ, approval=False)
    write_run = _spec("bitscale_run_grid", category=ToolCategory.WRITE, approval=True)

    assert bs.bitscale_adapter(read_grids, {}, credential=None) is None
    assert bs.bitscale_adapter(read_ws, {}, credential=None) is None
    assert bs.bitscale_adapter(write_run, {"inputs": {}}, credential=None) is None


def test_single_dispatcher_routes_three_distinct_ops(monkeypatch):
    """The collision guard: the THREE spec.names reach THREE DIFFERENT ops through the
    single bitscale_adapter dispatcher (not last-wins onto one op)."""
    seen: list[str] = []

    def list_spy(spec, params, *, credential):
        seen.append("list")
        return {"grids": []}

    def ws_spy(spec, params, *, credential):
        seen.append("workspace")
        return {"plan": "starter"}

    def run_spy(spec, params, *, credential):
        seen.append("run")
        return {"id": "1", "status": "queued"}

    monkeypatch.setitem(bs._BITSCALE_OPS, "bitscale_list_grids", list_spy)
    monkeypatch.setitem(bs._BITSCALE_OPS, "bitscale_get_workspace", ws_spy)
    monkeypatch.setitem(bs._BITSCALE_OPS, "bitscale_run_grid", run_spy)

    bs.bitscale_adapter(
        _spec("bitscale_list_grids", category=ToolCategory.READ, approval=False),
        {},
        credential="tok",
    )
    bs.bitscale_adapter(
        _spec("bitscale_get_workspace", category=ToolCategory.READ, approval=False),
        {},
        credential="tok",
    )
    bs.bitscale_adapter(
        _spec("bitscale_run_grid", category=ToolCategory.WRITE, approval=True),
        {"inputs": {}},
        credential="tok",
    )

    # Three distinct ops, in order — no collision / no last-wins.
    assert seen == ["list", "workspace", "run"]


def test_get_adapter_bitscale_is_reachable():
    """get_adapter("bitscale") returns the registered dispatcher via import-time
    registration — the wave-2 half of the 04-03 lazy-import-on-miss seam.

    Deterministic against sys.modules caching: drop the cached module + registry key so
    get_adapter's import-on-miss re-runs the module body (re-firing register())."""
    sys.modules.pop("agent_mesh.tools.adapters.bitscale", None)
    adapters._REGISTRY.pop("bitscale", None)

    fn = adapters.get_adapter("bitscale")

    assert callable(fn)
    assert fn.__name__ == "bitscale_adapter"


def test_list_grids_maps_to_output_schema(monkeypatch):
    """The read maps the provider response to {"grids":[...]} with id coerced to str and
    conforms to schemas/bitscale_list_grids.output.schema.json."""

    def fake_request(method, url, **kwargs):
        assert method == "GET"
        assert url.endswith("/grids")
        # id deliberately an int to prove the adapter coerces it to str.
        return _FakeResponse(
            {
                "grids": [
                    {
                        "id": 1234,
                        "name": "Leads",
                        "description": None,
                        "row_count": 10,
                        "column_count": 3,
                        "columns": [{"id": "c1", "name": "Email", "type": "text"}],
                    }
                ]
            }
        )

    import httpx

    monkeypatch.setattr(httpx, "request", fake_request)

    read_spec = _spec("bitscale_list_grids", category=ToolCategory.READ, approval=False)
    result = bs.bitscale_adapter(read_spec, {}, credential="tok")

    schema = json.loads((_SCHEMA_DIR / "bitscale_list_grids.output.schema.json").read_text())
    from jsonschema import Draft202012Validator

    Draft202012Validator(schema).validate(result)
    assert list(result.keys()) == ["grids"]
    assert result["grids"][0]["id"] == "1234"  # coerced to str


def test_run_grid_write_maps_to_output_schema_no_network(monkeypatch):
    """The WRITE op maps to schemas/bitscale_run_grid.output.schema.json against a FAKE
    httpx transport — proving the write path WITHOUT a live call / credit spend. This is
    the only place run_grid is exercised, and only against a fake transport."""
    captured: dict = {}

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        captured["headers"] = kwargs.get("headers")
        return _FakeResponse({"id": 9001, "status": "queued"})

    import httpx

    monkeypatch.setattr(httpx, "request", fake_request)

    write_spec = _spec("bitscale_run_grid", category=ToolCategory.WRITE, approval=True)
    result = bs.bitscale_adapter(
        write_spec, {"inputs": {"email": "a@b.com"}}, credential="tok"
    )

    # Routed to the inferred POST /grids/{grid_id}/run with the inputs body + X-API-Key.
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/grids/grid-test-1/run")
    assert captured["json"] == {"inputs": {"email": "a@b.com"}}
    assert captured["headers"]["X-API-Key"] == "tok"
    assert "Authorization" not in captured["headers"]  # X-API-Key auth, never Bearer

    schema = json.loads((_SCHEMA_DIR / "bitscale_run_grid.output.schema.json").read_text())
    from jsonschema import Draft202012Validator

    Draft202012Validator(schema).validate(result)
    assert result["id"] == "9001"  # coerced to str
