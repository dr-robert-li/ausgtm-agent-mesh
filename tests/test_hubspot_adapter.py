"""Default-lane (creds-free, SDK-free) tests for the HubSpot direct adapter (04-05).

Proves the 04-03 dispatch contract for the ``hubspot`` provider:
- ONE dispatcher under key ``hubspot`` routing by ``spec.name`` to DISTINCT ops
  (collision regression guard against last-wins register-per-op).
- ``get_adapter("hubspot")`` is reachable via import-time registration once this
  module exists (the wave-4 half of the 04-03 lazy-import-on-miss seam).
- creds-absent AND SDK-absent both degrade to ``None`` so the engine stubs (D-11) —
  no real SDK is installed in the default lane.
- read result maps to the strict output schema shape ``{"records":[{"id","properties"}]}``.

All SDK interaction is faked: a synthetic ``hubspot`` module tree is injected into
``sys.modules`` so nothing imports the real ``hubspot-api-client`` (opt-in extra).
"""

from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path

import pytest

from agent_mesh.contracts.enums import ToolCategory
from agent_mesh.tools import adapters
from agent_mesh.tools.adapters import hubspot as hs
from agent_mesh.tools.gateway import ToolSpec

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


# Registry isolation — _REGISTRY is module-global; snapshot/restore per test so a
# fake registered in one test never leaks into another (mirrors test_gateway_engine).
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
        provider="hubspot",
        category=category,
        description="",
        approval_required=approval,
        credential_secret_name="HUBSPOT_PRIVATE_APP_TOKEN",
        resource_bindings={"pipeline_id": "sandbox-pipe-1"},
        integration_style="direct_api",
    )


def test_creds_absent_degrades_to_none_no_sdk():
    """credential=None -> each op returns None (engine then stubs, D-11). No SDK import."""
    read_spec = _spec("hubspot_lookup_company", category=ToolCategory.READ, approval=False)
    write_spec = _spec("hubspot_create_deal", category=ToolCategory.WRITE, approval=True)

    assert hs.hubspot_adapter(read_spec, {"query": "Acme"}, credential=None) is None
    assert hs.hubspot_adapter(write_spec, {"deal_name": "D", "stage": "s"}, credential=None) is None


def test_sdk_absent_with_credential_degrades_to_none():
    """A non-None credential but no installed SDK -> the op degrades to None (the SDK
    is an opt-in extra). This is what keeps the default-suite leak test green: the
    engine reaches the real adapter with a fake non-None cred and must NOT raise."""
    # Ensure the real SDK truly is not importable in this lane; if it ever gets
    # installed locally, force the ImportError branch via a sys.modules sentinel.
    if "hubspot" not in sys.modules:
        try:
            importlib.import_module("hubspot")
            pytest.skip("hubspot SDK is installed in this env; ImportError branch not exercised")
        except ImportError:
            pass  # genuinely absent -> the op's except ImportError branch runs
    else:
        pytest.skip("hubspot SDK already importable; ImportError branch not exercised")

    read_spec = _spec("hubspot_lookup_company", category=ToolCategory.READ, approval=False)
    # Non-None credential, but no SDK -> None (no raise).
    assert hs.hubspot_adapter(read_spec, {"query": "Acme"}, credential="fake-token") is None


def test_single_dispatcher_routes_distinct_ops(monkeypatch):
    """The collision guard: spec.name "hubspot_lookup_company" vs "hubspot_create_deal"
    reach DIFFERENT ops through the single hubspot_adapter dispatcher (not last-wins)."""
    seen: list[str] = []

    def lookup_spy(spec, params, *, credential):
        seen.append("lookup")
        return {"records": []}

    def create_spy(spec, params, *, credential):
        seen.append("create")
        return {"deal_id": "1", "status": "created"}

    monkeypatch.setitem(hs._HS_OPS, "hubspot_lookup_company", lookup_spy)
    monkeypatch.setitem(hs._HS_OPS, "hubspot_create_deal", create_spy)

    read_spec = _spec("hubspot_lookup_company", category=ToolCategory.READ, approval=False)
    write_spec = _spec("hubspot_create_deal", category=ToolCategory.WRITE, approval=True)

    hs.hubspot_adapter(read_spec, {"query": "Acme"}, credential="tok")
    hs.hubspot_adapter(write_spec, {"deal_name": "D", "stage": "s"}, credential="tok")

    assert seen == ["lookup", "create"]  # distinct ops, in order — no collision


def test_get_adapter_hubspot_is_reachable():
    """get_adapter("hubspot") returns the registered dispatcher via import-time
    registration once this module exists — the wave-4 half of the 04-03 seam.

    Deterministic against sys.modules caching: drop the cached module + registry key
    so get_adapter's import-on-miss re-runs the module body (re-firing register())."""
    sys.modules.pop("agent_mesh.tools.adapters.hubspot", None)
    adapters._REGISTRY.pop("hubspot", None)

    fn = adapters.get_adapter("hubspot")

    assert callable(fn)
    assert fn.__name__ == "hubspot_adapter"


def test_lookup_company_maps_to_output_schema(monkeypatch):
    """The read maps the SDK search result to the strict output schema shape:
    {"records":[{"id":str,"properties":obj}]} and NO extra top-level keys."""
    # Build a synthetic `hubspot` module tree so `from hubspot import HubSpot` and
    # `from hubspot.crm.companies import PublicObjectSearchRequest` resolve to fakes.
    class _FakeObj:
        def __init__(self, oid, props):
            self.id = oid
            self.properties = props

    class _FakeSearchResult:
        def __init__(self, results):
            self.results = results

    class _FakeSearchApi:
        def do_search(self, *, public_object_search_request):
            # id deliberately an int to prove the adapter coerces to str.
            return _FakeSearchResult([_FakeObj(1234, {"name": "Acme", "domain": "acme.io"})])

    class _FakeObjectApi:
        def __init__(self):
            self.search_api = _FakeSearchApi()

    class _FakeCrm:
        def __init__(self):
            self.companies = _FakeObjectApi()
            self.contacts = _FakeObjectApi()

    class _FakeHubSpot:
        def __init__(self, *, access_token):
            self.crm = _FakeCrm()

    fake_hubspot = types.ModuleType("hubspot")
    fake_hubspot.HubSpot = _FakeHubSpot
    fake_companies = types.ModuleType("hubspot.crm.companies")
    fake_companies.PublicObjectSearchRequest = lambda **kw: kw
    fake_crm_pkg = types.ModuleType("hubspot.crm")

    monkeypatch.setitem(sys.modules, "hubspot", fake_hubspot)
    monkeypatch.setitem(sys.modules, "hubspot.crm", fake_crm_pkg)
    monkeypatch.setitem(sys.modules, "hubspot.crm.companies", fake_companies)

    read_spec = _spec("hubspot_lookup_company", category=ToolCategory.READ, approval=False)
    result = hs.hubspot_adapter(
        read_spec, {"object_type": "companies", "query": "Acme", "limit": 5}, credential="tok"
    )

    # Conforms to schemas/hubspot_lookup_company.output.schema.json (strict).
    schema = json.loads((_SCHEMA_DIR / "hubspot_lookup_company.output.schema.json").read_text())
    from jsonschema import Draft202012Validator

    Draft202012Validator(schema).validate(result)
    assert result == {
        "records": [{"id": "1234", "properties": {"name": "Acme", "domain": "acme.io"}}]
    }
    assert list(result.keys()) == ["records"]  # no extra top-level keys
