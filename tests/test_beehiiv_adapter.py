"""Default-lane (creds-free, dependency-free) tests for the Beehiiv direct adapter (05-06).

Proves the 04-03 dispatch contract for the ``beehiiv`` provider plus the two Beehiiv
gotchas:

- ONE dispatcher under key ``beehiiv`` routing by ``spec.name`` via ``_BEEHIIV_OPS``
  (the one-dispatcher-per-provider shape, NOT a bare register-per-op).
- ``get_adapter("beehiiv")`` is reachable via import-time registration (the wave-2 half
  of the 04-03 lazy-import-on-miss seam).
- credential-absent degrades to ``None`` so the engine stubs (D-11). httpx is CORE, so
  there is NO ImportError branch to test (unlike HubSpot's opt-in SDK).
- the create maps to the NESTED ``{"data": {"id": ...}}`` output shape (conforms to the
  strict-ish output schema requiring ``data``), NOT a flat ``{id}`` — the canonical
  quarantine-avoidance assertion.
- ``status`` is FORCED to ``"draft"`` even when the caller passes ``status:"confirmed"``
  — the draft-only / never-auto-publish guarantee (T-05-06-01).

The HTTP call is faked with ``httpx.MockTransport`` (httpx is core), monkeypatched onto
``httpx.post`` so nothing leaves the process and the request body sent to Beehiiv can be
captured and asserted.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from agent_mesh.contracts.enums import ToolCategory
from agent_mesh.tools import adapters
from agent_mesh.tools.adapters import beehiiv as bh
from agent_mesh.tools.gateway import ToolSpec

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


# Registry isolation — _REGISTRY is module-global; snapshot/restore per test so a
# fake registered in one test never leaks into another (mirrors test_hubspot_adapter).
@pytest.fixture(autouse=True)
def _isolate_registry():
    saved = dict(adapters._REGISTRY)
    try:
        yield
    finally:
        adapters._REGISTRY.clear()
        adapters._REGISTRY.update(saved)


def _spec() -> ToolSpec:
    return ToolSpec(
        name="beehiiv_create_post",
        provider="beehiiv",
        category=ToolCategory.PUBLISHING,
        description="",
        approval_required=True,
        credential_secret_name="BEEHIIV_API_KEY",
        resource_bindings={"publication_id": "pub_test_123"},
        integration_style="direct_api",
    )


def test_creds_absent_degrades_to_none():
    """credential=None -> the op returns None (engine then stubs, D-11). No HTTP call."""
    assert bh.beehiiv_adapter(_spec(), {"title": "Hello"}, credential=None) is None


def test_get_adapter_beehiiv_is_reachable():
    """get_adapter("beehiiv") returns the registered dispatcher via import-time
    registration — the wave-2 half of the 04-03 seam.

    Deterministic against sys.modules caching: drop the cached module + registry key so
    get_adapter's import-on-miss re-runs the module body (re-firing register())."""
    import sys

    sys.modules.pop("agent_mesh.tools.adapters.beehiiv", None)
    adapters._REGISTRY.pop("beehiiv", None)

    fn = adapters.get_adapter("beehiiv")

    assert callable(fn)
    assert fn.__name__ == "beehiiv_adapter"


def test_single_dispatcher_routes_by_name(monkeypatch):
    """The dispatcher routes by spec.name through _BEEHIIV_OPS (not a hardcoded op)."""
    seen: list[str] = []

    def create_spy(spec, params, *, credential):
        seen.append("create")
        return {"data": {"id": "post_1"}}

    monkeypatch.setitem(bh._BEEHIIV_OPS, "beehiiv_create_post", create_spy)
    bh.beehiiv_adapter(_spec(), {"title": "X"}, credential="tok")

    assert seen == ["create"]


def _capture_transport(captured: dict, *, status_code: int = 201):
    """A MockTransport handler that records the outgoing request and returns the real
    nested {"data": {"id": ...}} create-response shape."""

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            status_code,
            json={"data": {"id": "post_abc123", "title": "ignored-extra"}},
        )

    return httpx.MockTransport(_handler)


def test_create_post_maps_to_nested_output_and_forces_draft(monkeypatch):
    """The create (a) maps to the NESTED {"data":{"id":...}} output conforming to the
    schema (NOT a flat {id}), and (b) FORCES status:"draft" even when the caller passes
    status:"confirmed" — capturing the body actually sent to Beehiiv."""
    captured: dict = {}
    transport = _capture_transport(captured)

    def _fake_post(url, *, headers=None, json=None, timeout=None):  # noqa: A002
        # Route the adapter's httpx.post through the MockTransport (no network).
        with httpx.Client(transport=transport) as client:
            return client.post(url, headers=headers, json=json)

    monkeypatch.setattr(httpx, "post", _fake_post)

    # Caller maliciously/accidentally asks to publish — the adapter MUST override it.
    result = bh.beehiiv_adapter(
        _spec(),
        {"title": "Launch", "status": "confirmed", "subtitle": "sub", "body_content": "B"},
        credential="tok",
    )

    # (a) Output is the NESTED {"data":{"id":...}} shape and conforms to the schema.
    schema = json.loads((_SCHEMA_DIR / "beehiiv_create_post.output.schema.json").read_text())
    from jsonschema import Draft202012Validator

    Draft202012Validator(schema).validate(result)
    assert result == {"data": {"id": "post_abc123"}}
    assert "id" not in result  # NOT flattened to a top-level id

    # (b) The body sent to Beehiiv forced status:"draft" despite the caller's "confirmed".
    assert captured["body"]["status"] == "draft"
    assert captured["body"]["title"] == "Launch"
    assert captured["body"]["subtitle"] == "sub"
    assert captured["body"]["body_content"] == "B"
    # Never auto-publishes.
    assert captured["body"]["status"] != "confirmed"
    assert captured["body"]["status"] != "published"

    # The publication_id binding shaped the URL; the bearer key was sent (never logged).
    assert "/publications/pub_test_123/posts" in captured["url"]
    assert captured["auth"] == "Bearer tok"
