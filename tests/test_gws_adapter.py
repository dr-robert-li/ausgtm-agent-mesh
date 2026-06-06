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

    for name in (
        "google_drive_search",
        "gmail_send",
        "google_sheets_append",
        "google_calendar_list_events",
        "google_calendar_create_event",
        "google_docs_get",
        "google_docs_create",
        "google_slides_get",
        "google_slides_create",
    ):
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


# ---------------------------------------------------------------------------
# 04-07 — Calendar / Docs / Slides: routing regression + response-shape mappings.
# The fakes model the REAL nested Google response shapes (items / start objects /
# body.content text-run tree / pageElements text tree) — flattening them to
# already-correct strings would make the assertion tautological while the live
# mapping stays wrong.
# ---------------------------------------------------------------------------


def test_new_spec_name_routes_to_its_own_op_not_drive(monkeypatch):
    """Regression guard against collision: google_calendar_list_events reaches the
    calendar op through the ONE dispatcher, NOT the Drive op."""
    mod = _gws_module()
    seen: list[str] = []

    def fake_calendar(spec, params, *, credential):
        seen.append("calendar")
        return {"events": []}

    def fake_drive(spec, params, *, credential):
        seen.append("drive")
        return {"results": []}

    monkeypatch.setitem(mod._GWS_OPS, "google_calendar_list_events", fake_calendar)
    monkeypatch.setitem(mod._GWS_OPS, "google_drive_search", fake_drive)

    mod.google_workspace_adapter(
        _spec("google_calendar_list_events"), {}, credential="c"
    )
    assert seen == ["calendar"]


def test_all_twelve_ops_registered_in_dispatch_map():
    """All six products (twelve ops) are reachable through the single _GWS_OPS map."""
    mod = _gws_module()
    for name in (
        "google_drive_search",
        "gmail_send",
        "google_sheets_append",
        "google_calendar_list_events",
        "google_calendar_create_event",
        "google_docs_get",
        "google_docs_create",
        "google_slides_get",
        "google_slides_create",
    ):
        assert name in mod._GWS_OPS


def test_calendar_list_events_maps_nested_response_to_output_schema(monkeypatch):
    """Calendar read maps the REAL Events.list shape (items[], start/end as objects)
    to the strict google_calendar_list_events.output schema, validated against the
    real schema file. start/end objects are flattened to dateTime-or-date strings."""
    from agent_mesh.tools.validation import _load, validate_output

    mod = _gws_module()
    monkeypatch.setattr(mod, "_build_credentials", lambda credential, scopes: object())

    captured: dict[str, object] = {}

    class _FakeList:
        def execute(self):
            return {
                "items": [
                    {
                        "id": "ev1",
                        "summary": "Standup",
                        "start": {"dateTime": "2026-06-07T09:00:00+10:00"},
                        "end": {"dateTime": "2026-06-07T09:15:00+10:00"},
                    },
                    {  # all-day event uses `date`, not `dateTime`; no summary
                        "id": "ev2",
                        "start": {"date": "2026-06-08"},
                        "end": {"date": "2026-06-09"},
                    },
                ]
            }

    class _FakeEvents:
        def list(self, **kwargs):
            captured.update(kwargs)
            return _FakeList()

    class _FakeService:
        def events(self):
            return _FakeEvents()

    monkeypatch.setattr(mod, "_service", lambda product, version, creds: _FakeService())

    result = mod._calendar_list_events(
        _spec("google_calendar_list_events"),
        {"calendar_id": "primary"},
        credential="c",
    )
    assert result == {
        "events": [
            {
                "event_id": "ev1",
                "summary": "Standup",
                "start": "2026-06-07T09:00:00+10:00",
                "end": "2026-06-07T09:15:00+10:00",
            },
            {
                "event_id": "ev2",
                "start": "2026-06-08",
                "end": "2026-06-09",
            },
        ]
    }
    assert captured["calendarId"] == "primary"
    schema = _load(
        str(REPO_ROOT / "schemas" / "google_calendar_list_events.output.schema.json")
    )
    assert validate_output(schema, result) == []


def test_docs_get_walks_content_tree_to_output_schema(monkeypatch):
    """Docs read walks the REAL body.content[].paragraph.elements[].textRun.content
    tree into the required `text` field, validated against the real schema file."""
    from agent_mesh.tools.validation import _load, validate_output

    mod = _gws_module()
    monkeypatch.setattr(mod, "_build_credentials", lambda credential, scopes: object())

    class _FakeGet:
        def execute(self):
            return {
                "documentId": "doc1",
                "title": "Q3 Plan",
                "body": {
                    "content": [
                        {"sectionBreak": {}},  # non-paragraph element is skipped
                        {
                            "paragraph": {
                                "elements": [
                                    {"textRun": {"content": "Hello "}},
                                    {"textRun": {"content": "world\n"}},
                                ]
                            }
                        },
                    ]
                },
            }

    class _FakeDocs:
        def get(self, documentId):
            assert documentId == "doc1"
            return _FakeGet()

    class _FakeService:
        def documents(self):
            return _FakeDocs()

    monkeypatch.setattr(mod, "_service", lambda product, version, creds: _FakeService())

    result = mod._docs_get(
        _spec("google_docs_get"), {"document_id": "doc1"}, credential="c"
    )
    assert result == {
        "document_id": "doc1",
        "text": "Hello world\n",
        "title": "Q3 Plan",
    }
    schema = _load(str(REPO_ROOT / "schemas" / "google_docs_get.output.schema.json"))
    assert validate_output(schema, result) == []


def test_slides_get_walks_page_elements_to_output_schema(monkeypatch):
    """Slides read walks the REAL slides[].pageElements[].shape.text.textElements[]
    .textRun.content tree, mapping objectId -> slide_id; validated against the real
    schema file."""
    from agent_mesh.tools.validation import _load, validate_output

    mod = _gws_module()
    monkeypatch.setattr(mod, "_build_credentials", lambda credential, scopes: object())

    class _FakeGet:
        def execute(self):
            return {
                "presentationId": "pres1",
                "title": "Pitch",
                "slides": [
                    {
                        "objectId": "s1",
                        "pageElements": [
                            {
                                "shape": {
                                    "text": {
                                        "textElements": [
                                            {"textRun": {"content": "Title slide"}}
                                        ]
                                    }
                                }
                            }
                        ],
                    },
                    {"objectId": "s2"},  # slide with no text -> slide_id only
                ],
            }

    class _FakePresentations:
        def get(self, presentationId):
            assert presentationId == "pres1"
            return _FakeGet()

    class _FakeService:
        def presentations(self):
            return _FakePresentations()

    monkeypatch.setattr(mod, "_service", lambda product, version, creds: _FakeService())

    result = mod._slides_get(
        _spec("google_slides_get"), {"presentation_id": "pres1"}, credential="c"
    )
    assert result == {
        "presentation_id": "pres1",
        "title": "Pitch",
        "slides": [
            {"slide_id": "s1", "text": "Title slide"},
            {"slide_id": "s2"},
        ],
    }
    schema = _load(str(REPO_ROOT / "schemas" / "google_slides_get.output.schema.json"))
    assert validate_output(schema, result) == []


def test_calendar_create_event_maps_created_id(monkeypatch):
    """Calendar write maps the created event's id -> event_id and htmlLink ->
    html_link, validated against the real schema file."""
    from agent_mesh.tools.validation import _load, validate_output

    mod = _gws_module()
    monkeypatch.setattr(mod, "_build_credentials", lambda credential, scopes: object())

    captured: dict[str, object] = {}

    class _FakeInsert:
        def execute(self):
            return {"id": "newev", "htmlLink": "https://cal/x"}

    class _FakeEvents:
        def insert(self, **kwargs):
            captured.update(kwargs)
            return _FakeInsert()

    class _FakeService:
        def events(self):
            return _FakeEvents()

    monkeypatch.setattr(mod, "_service", lambda product, version, creds: _FakeService())

    result = mod._calendar_create_event(
        _spec("google_calendar_create_event"),
        {
            "calendar_id": "primary",
            "summary": "Sync",
            "start": "2026-06-07T09:00:00+10:00",
            "end": "2026-06-07T09:30:00+10:00",
        },
        credential="c",
    )
    assert result == {"event_id": "newev", "html_link": "https://cal/x"}
    assert captured["calendarId"] == "primary"
    schema = _load(
        str(REPO_ROOT / "schemas" / "google_calendar_create_event.output.schema.json")
    )
    assert validate_output(schema, result) == []
