"""Default-lane (creds-free, dependency-free) tests for the Clockify direct adapter (05-05).

Proves the 04-03 dispatch contract for the ``clockify`` provider:
- ONE dispatcher under key ``clockify`` routing by ``spec.name`` via ``_CLOCKIFY_OPS``.
- ``get_adapter("clockify")`` is reachable via import-time registration (the 04-03
  lazy-import-on-miss seam).
- creds-absent degrades to ``None`` so the engine stubs (D-11). ``httpx`` is core, so
  there is NO ImportError branch to test.
- the read maps Clockify's BARE ARRAY into the strict ``{"entries":[...]}`` output
  shape, the request URL carries BOTH the workspace_id and user_id segments, and auth
  is the ``X-Api-Key`` header (NOT Bearer).

The Clockify HTTP call is faked by monkeypatching ``clockify.httpx.get`` with a
capturing fake — nothing leaves the process and no credential is needed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from agent_mesh.contracts.enums import ToolCategory
from agent_mesh.tools import adapters
from agent_mesh.tools.adapters import clockify as ck
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


def _spec(name: str = "clockify_read_time_entries") -> ToolSpec:
    return ToolSpec(
        name=name,
        provider="clockify",
        category=ToolCategory.READ,
        description="",
        approval_required=False,
        credential_secret_name="CLOCKIFY_API_KEY",
        resource_bindings={"workspace_id": "ws-abc", "user_id": "usr-xyz"},
        integration_style="direct_api",
    )


class _FakeResponse:
    """Minimal stand-in for httpx.Response: raise_for_status + json."""

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_creds_absent_degrades_to_none():
    """credential=None -> the op returns None (engine then stubs, D-11). No HTTP call."""
    assert ck.clockify_adapter(_spec(), {}, credential=None) is None


def test_get_adapter_clockify_is_reachable():
    """get_adapter("clockify") returns the registered dispatcher via import-time
    registration once this module exists — the 05-05 half of the 04-03 seam.

    Deterministic against sys.modules caching: drop the cached module + registry key
    so get_adapter's import-on-miss re-runs the module body (re-firing register())."""
    sys.modules.pop("agent_mesh.tools.adapters.clockify", None)
    adapters._REGISTRY.pop("clockify", None)

    fn = adapters.get_adapter("clockify")

    assert callable(fn)
    assert fn.__name__ == "clockify_adapter"


def test_read_maps_bare_array_to_output_schema_with_both_path_segments(monkeypatch):
    """The read (a) maps Clockify's BARE ARRAY into the strict {"entries":[...]} output
    schema, (b) builds a URL containing BOTH the workspace_id and user_id segments, and
    (c) sends the X-Api-Key header (NOT Bearer). The HTTP call is captured via a fake."""
    captured: dict = {}

    def fake_get(url, *, headers, params, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        captured["timeout"] = timeout
        # Clockify returns a BARE ARRAY of entry objects.
        return _FakeResponse(
            [
                {
                    "id": "entry-1",
                    "description": "Design review",
                    "timeInterval": {
                        "start": "2026-06-01T09:00:00Z",
                        "end": "2026-06-01T10:00:00Z",
                        "duration": "PT1H",
                    },
                    "projectId": "proj-1",
                }
            ]
        )

    monkeypatch.setattr(ck.httpx, "get", fake_get)

    result = ck.clockify_adapter(
        _spec(),
        {"start": "2026-06-01T00:00:00Z", "page-size": 50},
        credential="api-key-123",
    )

    # (a) Conforms to the strict output schema, wrapped under "entries" (NOT a bare list).
    schema = json.loads(
        (_SCHEMA_DIR / "clockify_read_time_entries.output.schema.json").read_text()
    )
    from jsonschema import Draft202012Validator

    Draft202012Validator(schema).validate(result)
    assert isinstance(result, dict)
    assert "entries" in result and isinstance(result["entries"], list)
    assert result["entries"][0]["id"] == "entry-1"

    # (b) BOTH path segments present in the two-segment workspace/user path.
    assert "ws-abc" in captured["url"]
    assert "usr-xyz" in captured["url"]
    assert captured["url"].endswith("/workspaces/ws-abc/user/usr-xyz/time-entries")

    # (c) X-Api-Key auth header carries the key; NO Bearer Authorization header.
    assert captured["headers"]["X-Api-Key"] == "api-key-123"
    assert "Authorization" not in captured["headers"]

    # Query filters pass through (None-valued keys dropped).
    assert captured["params"] == {"start": "2026-06-01T00:00:00Z", "page-size": 50}


def test_unknown_spec_name_raises_keyerror():
    """A spec.name absent from _CLOCKIFY_OPS surfaces a KeyError (no silent wrong-op
    dispatch) — guards a future second op against a typo'd manifest name."""
    with pytest.raises(KeyError):
        ck.clockify_adapter(_spec("clockify_does_not_exist"), {}, credential="k")
