"""Google Workspace adapter — default-lane (creds-free) tests (04-06).

Proves, WITHOUT the google SDK installed and WITHOUT any network/creds:

* the module imports cleanly (all google imports are lazy/in-function);
* it registers EXACTLY ONE dispatcher under the shared ``google_workspace`` key,
  reachable via the 04-03 ``get_adapter`` import-on-miss seam;
* the single dispatcher ROUTES BY ``spec.name`` to distinct ops — the regression
  guard against the last-wins collision that would make Drive/Gmail unreachable;
* credential-None degrades to the stub-fallback sentinel (``None``) BEFORE any creds
  build / SDK import (D-11);
* the Drive read maps a fake Files.list response to the strict
  ``google_drive_search.output`` schema (validated against the real schema file).

The auth/service seams (``_build_credentials`` / ``_service``) are monkeypatched so
the real ``google-api-python-client`` / ``google-auth`` are never imported.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from agent_mesh.contracts.enums import ToolCategory
from agent_mesh.tools.gateway import ToolSpec, load_tool_pack

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "manifests" / "tool_pack_manifest.yaml"


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Snapshot/restore the module-global registry per test (mirrors 04-03)."""
    from agent_mesh.tools import adapters

    saved = dict(adapters._REGISTRY)
    adapters._REGISTRY.clear()
    try:
        yield
    finally:
        adapters._REGISTRY.clear()
        adapters._REGISTRY.update(saved)


def _gws_module():
    """Import (and re-run module-level register()) of the GWS adapter.

    The autouse fixture clears _REGISTRY, so reload to re-fire registration into the
    now-empty registry — exactly what get_adapter's import-on-miss does at runtime.
    """
    import agent_mesh.tools.adapters.google_workspace as mod

    return importlib.reload(mod)


def _spec(name: str) -> ToolSpec:
    return next(s for s in load_tool_pack(MANIFEST) if s.name == name)


def test_module_imports_without_google_sdk():
    """All google imports are lazy -> the module imports creds/SDK-free."""
    mod = _gws_module()
    assert callable(mod.google_workspace_adapter)


def test_registers_exactly_one_dispatcher_under_provider_key():
    """ONE register('google_workspace', ...) — reachable via the 04-03 seam.

    Proves the module's register() actually populates the registry under the
    adapter_key_for-derived key (provider, for direct_api), not just that the
    string appears in the source.
    """
    _gws_module()
    from agent_mesh.tools.adapters import adapter_key_for, get_adapter

    spec = _spec("google_drive_search")
    assert adapter_key_for(spec) == "google_workspace"
    adapter = get_adapter("google_workspace")
    assert adapter is not None and callable(adapter)


def test_single_dispatcher_routes_by_spec_name_to_distinct_ops(monkeypatch):
    """Regression guard: google_drive_search vs google_sheets_append reach DIFFERENT
    ops through the ONE dispatcher (not last-wins-collision)."""
    mod = _gws_module()
    seen: list[str] = []

    def fake_drive(spec, params, *, credential):
        seen.append("drive")
        return {"results": []}

    def fake_sheets(spec, params, *, credential):
        seen.append("sheets")
        return {"updated_range": "Sheet1!A1"}

    monkeypatch.setitem(mod._GWS_OPS, "google_drive_search", fake_drive)
    monkeypatch.setitem(mod._GWS_OPS, "google_sheets_append", fake_sheets)

    mod.google_workspace_adapter(_spec("google_drive_search"), {}, credential="c")
    mod.google_workspace_adapter(_spec("google_sheets_append"), {}, credential="c")
    assert seen == ["drive", "sheets"]


def test_credential_none_degrades_to_stub_before_any_creds_build(monkeypatch):
    """credential=None returns None (stub-fallback sentinel) BEFORE _build_credentials
    is ever called — proves the guard precedes the creds build / SDK import (D-11)."""
    mod = _gws_module()

    def _boom(*a, **k):  # would fire if the None-guard were missing
        raise AssertionError("_build_credentials must NOT run on the cred-None path")

    monkeypatch.setattr(mod, "_build_credentials", _boom)

    for name in ("google_drive_search", "gmail_send", "google_sheets_append"):
        result = mod.google_workspace_adapter(_spec(name), {}, credential=None)
        assert result is None


def test_unknown_spec_name_returns_none(monkeypatch):
    """An unrouted name degrades to the stub (None), not an exception."""
    mod = _gws_module()
    bogus = ToolSpec(
        name="google_unknown_op",
        provider="google_workspace",
        category=ToolCategory.READ,
        description="",
        approval_required=False,
        credential_secret_name="GOOGLE_WORKSPACE_OAUTH",
        resource_bindings={},
    )
    assert mod.google_workspace_adapter(bogus, {}, credential="c") is None


def test_drive_search_maps_fake_service_to_output_schema(monkeypatch):
    """Drive read maps a fake Files.list response to the STRICT
    google_drive_search.output schema (validated against the real schema file).

    Absent optional keys are OMITTED, not set to None (additionalProperties: false +
    string-typed optionals would reject mime_type: null)."""
    from agent_mesh.tools.validation import _load, validate_output

    mod = _gws_module()
    monkeypatch.setattr(mod, "_build_credentials", lambda credential, scopes: object())

    class _FakeList:
        def execute(self):
            return {
                "files": [
                    {
                        "id": "1abc",
                        "name": "Q3 plan.docx",
                        "mimeType": "application/vnd.google-apps.document",
                        "modifiedTime": "2026-06-01T10:00:00.000Z",
                    },
                    {"id": "2def", "name": "untitled"},  # optional keys absent
                ]
            }

    class _FakeFiles:
        def list(self, **kwargs):
            assert kwargs["fields"] == "files(id,name,mimeType,modifiedTime)"
            return _FakeList()

    class _FakeService:
        def files(self):
            return _FakeFiles()

    monkeypatch.setattr(mod, "_service", lambda product, version, creds: _FakeService())

    result = mod._drive_search(
        _spec("google_drive_search"), {"query": "plan"}, credential="c"
    )
    assert result == {
        "results": [
            {
                "file_id": "1abc",
                "name": "Q3 plan.docx",
                "mime_type": "application/vnd.google-apps.document",
                "modified_at": "2026-06-01T10:00:00.000Z",
            },
            {"file_id": "2def", "name": "untitled"},
        ]
    }
    # Tie the assertion to the REAL schema file, not just the dict above.
    schema = _load(str(REPO_ROOT / "schemas" / "google_drive_search.output.schema.json"))
    assert validate_output(schema, result) == []


def test_drive_search_escapes_single_quote_in_query(monkeypatch):
    """An apostrophe in the query MUST be escaped — the Drive `q` grammar single-quotes
    the literal, so 'client's deck' unescaped is malformed syntax (live-call error)."""
    mod = _gws_module()
    monkeypatch.setattr(mod, "_build_credentials", lambda credential, scopes: object())
    captured: dict[str, str] = {}

    class _FakeList:
        def execute(self):
            return {"files": []}

    class _FakeFiles:
        def list(self, **kwargs):
            captured["q"] = kwargs["q"]
            return _FakeList()

    class _FakeService:
        def files(self):
            return _FakeFiles()

    monkeypatch.setattr(mod, "_service", lambda product, version, creds: _FakeService())
    mod._drive_search(
        _spec("google_drive_search"), {"query": "client's deck"}, credential="c"
    )
    assert captured["q"] == "fullText contains 'client\\'s deck'"
