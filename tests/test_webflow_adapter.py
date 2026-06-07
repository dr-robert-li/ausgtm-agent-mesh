"""Default-lane (creds-free, SDK-free) tests for the Webflow direct adapter (05-02).

Proves the 04-03 dispatch contract for the ``webflow`` provider:
- ONE dispatcher under key ``webflow`` routing by ``spec.name`` to DISTINCT ops
  (collision regression guard against last-wins register-per-op).
- ``get_adapter("webflow")`` is reachable via import-time registration.
- creds-absent -> both ops return ``None`` so the engine stubs (D-11). httpx is a CORE
  dep, so the stub path is driven by ``credential is None``, NOT an ImportError branch
  (there is no SDK to be absent — and therefore NO ImportError test).
- the read result conforms to ``schemas/webflow_list_cms_items.output.schema.json``.
- the create FORCES ``isDraft: true`` (T-05-02-01) even when a caller passes
  ``isDraft: False``, and its mapped 202 body conforms to
  ``schemas/webflow_create_cms_item.output.schema.json`` (write output-quarantine guard:
  the live lane never exercises create, so this default-lane check is the only thing
  catching a write-output mismatch).

httpx is never hit over the network: ``httpx.get`` / ``httpx.post`` are monkeypatched
with a fake transport that records the request and returns a canned Webflow response.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from agent_mesh.contracts.enums import ToolCategory
from agent_mesh.tools import adapters
from agent_mesh.tools.adapters import webflow as wf
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
        provider="webflow",
        category=category,
        description="",
        approval_required=approval,
        credential_secret_name="WEBFLOW_API_TOKEN",
        resource_bindings={"site_id": "site-1", "collection_id": "coll-1"},
        integration_style="direct_api",
    )


class _FakeResponse:
    """Minimal httpx.Response stand-in: ``raise_for_status`` + ``json``."""

    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:  # noqa: D401 - no error in the happy path
        return None

    def json(self) -> dict:
        return self._payload


def test_creds_absent_degrades_to_none():
    """credential=None -> each op returns None (engine then stubs, D-11). No network."""
    read_spec = _spec("webflow_list_cms_items", category=ToolCategory.READ, approval=False)
    write_spec = _spec(
        "webflow_create_cms_item", category=ToolCategory.PUBLISHING, approval=True
    )

    assert wf.webflow_adapter(read_spec, {}, credential=None) is None
    assert (
        wf.webflow_adapter(write_spec, {"fieldData": {"name": "x"}}, credential=None)
        is None
    )


def test_single_dispatcher_routes_distinct_ops(monkeypatch):
    """The collision guard: spec.name "webflow_list_cms_items" vs "webflow_create_cms_item"
    reach DIFFERENT ops through the single webflow_adapter dispatcher (not last-wins)."""
    seen: list[str] = []

    def list_spy(spec, params, *, credential):
        seen.append("list")
        return {"items": []}

    def create_spy(spec, params, *, credential):
        seen.append("create")
        return {"id": "1"}

    monkeypatch.setitem(wf._WEBFLOW_OPS, "webflow_list_cms_items", list_spy)
    monkeypatch.setitem(wf._WEBFLOW_OPS, "webflow_create_cms_item", create_spy)

    read_spec = _spec("webflow_list_cms_items", category=ToolCategory.READ, approval=False)
    write_spec = _spec(
        "webflow_create_cms_item", category=ToolCategory.PUBLISHING, approval=True
    )

    wf.webflow_adapter(read_spec, {}, credential="tok")
    wf.webflow_adapter(write_spec, {"fieldData": {"name": "x"}}, credential="tok")

    assert seen == ["list", "create"]  # distinct ops, in order — no collision


def test_get_adapter_webflow_is_reachable():
    """get_adapter("webflow") returns the registered dispatcher via import-time
    registration. Deterministic against sys.modules caching: drop the cached module +
    registry key so get_adapter's import-on-miss re-runs the module body."""
    sys.modules.pop("agent_mesh.tools.adapters.webflow", None)
    adapters._REGISTRY.pop("webflow", None)

    fn = adapters.get_adapter("webflow")

    assert callable(fn)
    assert fn.__name__ == "webflow_adapter"


def test_list_cms_items_maps_to_output_schema(monkeypatch):
    """The read maps the Data-API-v2 response to {items, pagination} and conforms to
    schemas/webflow_list_cms_items.output.schema.json. The bound collection_id lands in
    the URL; the token never appears in the result."""
    captured: dict = {}

    def fake_get(url, *, headers, params, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        return _FakeResponse(
            {
                "items": [
                    {"id": "item-1", "isDraft": False, "fieldData": {"name": "Post"}}
                ],
                "pagination": {"limit": 10, "offset": 0, "total": 1},
            }
        )

    monkeypatch.setattr("httpx.get", fake_get)

    read_spec = _spec("webflow_list_cms_items", category=ToolCategory.READ, approval=False)
    result = wf.webflow_adapter(read_spec, {"limit": 10, "offset": 0}, credential="tok")

    schema = json.loads(
        (_SCHEMA_DIR / "webflow_list_cms_items.output.schema.json").read_text()
    )
    Draft202012Validator(schema).validate(result)

    # Bound collection_id is in the URL; /v2 is NOT doubled.
    assert captured["url"] == "https://api.webflow.com/v2/collections/coll-1/items"
    assert "/v2/v2/" not in captured["url"]
    # Token carried only in the Authorization header, never in the result.
    assert captured["headers"]["Authorization"] == "Bearer tok"
    assert "tok" not in json.dumps(result)
    assert result["items"][0]["id"] == "item-1"


def test_create_forces_isdraft_and_maps_output_schema(monkeypatch):
    """The create ALWAYS forces isDraft:true (T-05-02-01) — even when the caller passes
    isDraft:False — and the mapped 202 body conforms to
    schemas/webflow_create_cms_item.output.schema.json (write output-quarantine guard)."""
    captured: dict = {}

    def fake_post(url, *, headers, json, timeout):  # noqa: A002 - mirror httpx kw name
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = json
        return _FakeResponse(
            {
                "id": "new-item-1",
                "isDraft": True,
                "fieldData": {"name": "Draft Post", "slug": "draft-post"},
                "lastPublished": None,
                "createdOn": "2026-06-07T00:00:00Z",
            }
        )

    monkeypatch.setattr("httpx.post", fake_post)

    write_spec = _spec(
        "webflow_create_cms_item", category=ToolCategory.PUBLISHING, approval=True
    )
    # Caller maliciously/accidentally asks to publish — the adapter must override it.
    result = wf.webflow_adapter(
        write_spec,
        {"fieldData": {"name": "Draft Post"}, "isDraft": False},
        credential="tok",
    )

    # The POST body ALWAYS forces isDraft true regardless of caller input.
    assert captured["body"]["isDraft"] is True
    assert captured["url"] == "https://api.webflow.com/v2/collections/coll-1/items"
    assert "/v2/v2/" not in captured["url"]

    # The mapped 202 body conforms to the strict-shaped create output schema.
    schema = json.loads(
        (_SCHEMA_DIR / "webflow_create_cms_item.output.schema.json").read_text()
    )
    Draft202012Validator(schema).validate(result)
    assert result["id"] == "new-item-1"
    assert result["isDraft"] is True
    # Null fields are dropped, not emitted as null (lastPublished was None).
    assert "lastPublished" not in result
    assert "lastUpdated" not in result
