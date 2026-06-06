"""Google Workspace direct adapter — shared auth scaffold + single dispatcher (D-08).

This module ships the FULL Google Workspace direct suite: the shared OAuth/refresh
auth scaffold plus nine ops across six products — Drive search (read), Gmail send
(external_send), Sheets append (write) [04-06]; and Calendar list/create, Docs
get/create, Slides get/create [04-07]. Reads are ungated; writes/sends are
approval-gated upstream by the manifest + ledger. All nine ops live behind ONE
dispatcher routed by ``spec.name`` through ``_GWS_OPS`` — there is exactly ONE
registration call (a second per-op call would last-wins collide and silently make
most ops unreachable).

REGISTRY CONTRACT (04-03)
-------------------------
All Google Workspace tools share ``provider: google_workspace`` and ``execute()``
dispatches direct tools by ``spec.provider``. So this module performs EXACTLY ONE
registration under the ``google_workspace`` key — a single dispatcher that routes by
``spec.name`` through ``_GWS_OPS``. One register call per op would collide on the
shared provider key and leave Drive/Gmail unreachable (silent SC-1 under-delivery).

CREDENTIAL SHAPE (D-02 / RESEARCH A5)
-------------------------------------
``GOOGLE_WORKSPACE_OAUTH`` resolves to a JSON blob
``{client_id, client_secret, refresh_token}`` (the unattended-refresh material). One
OAuth client + stored refresh token drives a single ``google-api-python-client`` across
all products via ``google.oauth2.credentials.Credentials`` (auto-refreshes on first
call). When the credential is ``None`` the adapter returns ``None`` so ``execute()``
falls back to the deterministic stub (D-11) — the default suite stays green and
creds-free.

LAZY IMPORTS
------------
Every google import (``json``-parsing aside) lives INSIDE a function so the module
imports cleanly without ``google-api-python-client`` / ``google-auth`` installed. The
default-lane tests monkeypatch ``_build_credentials`` and ``_service`` so neither
import fires; the live lane (opt-in, ``GOOGLE_WORKSPACE_OAUTH`` present) exercises the
real SDK.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from agent_mesh.tools.adapters import register

if TYPE_CHECKING:  # pragma: no cover - typing only
    from agent_mesh.tools.gateway import ToolSpec

# Per-product OAuth scopes for THIS plan (least-privilege, RESEARCH scopes table).
# 04-07 adds calendar.events / documents / presentations entries alongside.
_DRIVE_READONLY = "https://www.googleapis.com/auth/drive.readonly"
_GMAIL_SEND = "https://www.googleapis.com/auth/gmail.send"
_SHEETS = "https://www.googleapis.com/auth/spreadsheets"
# 04-07 — Calendar/Docs/Slides per-product scopes (read = readonly, write = full).
_CALENDAR_READONLY = "https://www.googleapis.com/auth/calendar.readonly"
_CALENDAR_EVENTS = "https://www.googleapis.com/auth/calendar.events"
_DOCS_READONLY = "https://www.googleapis.com/auth/documents.readonly"
_DOCS = "https://www.googleapis.com/auth/documents"
_SLIDES_READONLY = "https://www.googleapis.com/auth/presentations.readonly"
_SLIDES = "https://www.googleapis.com/auth/presentations"


def _build_credentials(credential: str, scopes: list[str]):
    """Build an auto-refreshing ``Credentials`` from the GOOGLE_WORKSPACE_OAUTH blob.

    Lazy-imports ``google.oauth2.credentials`` so the module stays importable without
    the SDK. Parses the ``{client_id, client_secret, refresh_token}`` blob and returns
    a ``Credentials`` with ``token=None`` that auto-refreshes on first API call (the
    refresh token is the long-lived material; the access token is minted on demand).

    Shared by every op and reused unchanged by 04-07 — the only per-op variation is the
    ``scopes`` list, so all six products share this one auth path.
    """
    from google.oauth2.credentials import Credentials

    blob = json.loads(credential)
    return Credentials(
        token=None,
        refresh_token=blob["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=blob["client_id"],
        client_secret=blob["client_secret"],
        scopes=scopes,
    )


def _service(product: str, version: str, creds):
    """Build a ``google-api-python-client`` service for ``product`` (lazy import).

    A thin seam over ``googleapiclient.discovery.build`` so the SDK import stays inside
    a function (module importable creds-free) and default-lane tests can monkeypatch
    this to return a fake service without installing the client.
    """
    from googleapiclient.discovery import build

    return build(product, version, credentials=creds, cache_discovery=False)


def _drive_search(spec: ToolSpec, params: dict, *, credential: str | None) -> dict | None:
    """Drive search (read; ``drive.readonly``). Maps the Files.list response to the
    strict ``google_drive_search.output`` schema (``{results: [{file_id, name, ...}]}``).

    ``additionalProperties: false`` on each result item means optional keys
    (``mime_type``/``snippet``/``modified_at``) are OMITTED when the API omits them —
    setting them to ``None`` would fail the ``string`` type.
    """
    if credential is None:  # defensive D-11 (execute() also guards before dispatch)
        return None
    creds = _build_credentials(credential, [_DRIVE_READONLY])
    service = _service("drive", "v3", creds)
    # Escape backslashes then single-quotes: the Drive `q` grammar single-quotes the
    # literal, so an unescaped apostrophe ("O'Brien", "client's deck") would produce
    # malformed query syntax and the API call would error.
    query = params["query"].replace("\\", "\\\\").replace("'", "\\'")
    max_results = params.get("max_results", 10)
    list_kwargs: dict[str, Any] = {
        "q": f"fullText contains '{query}'",
        "pageSize": max_results,
        "fields": "files(id,name,mimeType,modifiedTime)",
    }
    drive_id = params.get("drive_id")
    if drive_id:
        list_kwargs.update(
            corpora="drive",
            driveId=drive_id,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        )
    resp = service.files().list(**list_kwargs).execute()
    results: list[dict[str, str]] = []
    for f in resp.get("files", []):
        item: dict[str, str] = {"file_id": f["id"], "name": f["name"]}
        if f.get("mimeType"):
            item["mime_type"] = f["mimeType"]
        if f.get("modifiedTime"):
            item["modified_at"] = f["modifiedTime"]
        results.append(item)
    return {"results": results}


def _gmail_send(spec: ToolSpec, params: dict, *, credential: str | None) -> dict | None:
    """Gmail send (external_send; ``gmail.send``). Reached only AFTER the ledger
    approves (manifest ``approval_required: true``; the gateway never dispatches a
    write-class call without approval). Maps the sent-message response to
    ``gmail_send.output`` (``{message_id, thread_id?}``).
    """
    if credential is None:  # defensive D-11
        return None
    import base64
    from email.message import EmailMessage

    creds = _build_credentials(credential, [_GMAIL_SEND])
    service = _service("gmail", "v1", creds)
    msg = EmailMessage()
    msg["To"] = ", ".join(params["to"])
    if params.get("cc"):
        msg["Cc"] = ", ".join(params["cc"])
    msg["Subject"] = params.get("subject", "")
    msg.set_content(params.get("body", ""))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    out: dict[str, str] = {"message_id": sent["id"]}
    if sent.get("threadId"):
        out["thread_id"] = sent["threadId"]
    return out


def _sheets_append(spec: ToolSpec, params: dict, *, credential: str | None) -> dict | None:
    """Sheets append (write; ``spreadsheets``). Reached only AFTER the ledger approves.
    Maps the append response's ``updates`` block to ``google_sheets_append.output``
    (``{updated_range, updated_rows?}``).
    """
    if credential is None:  # defensive D-11
        return None
    creds = _build_credentials(credential, [_SHEETS])
    service = _service("sheets", "v4", creds)
    rng = params.get("range", "A1")
    resp = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=params["spreadsheet_id"],
            range=rng,
            valueInputOption="USER_ENTERED",
            body={"values": params["values"]},
        )
        .execute()
    )
    updates = resp.get("updates", {})
    out: dict[str, Any] = {"updated_range": updates.get("updatedRange", rng)}
    if "updatedRows" in updates:
        out["updated_rows"] = updates["updatedRows"]
    return out


# ---------------------------------------------------------------------------
# 04-07 — Calendar / Docs / Slides ops (complete the six-product suite, D-08).
# All reuse _build_credentials + _service (no new auth path); each read maps the
# nested Google response to its flat output schema, each write maps the created id.
# ---------------------------------------------------------------------------


def _calendar_list_events(
    spec: ToolSpec, params: dict, *, credential: str | None
) -> dict | None:
    """Calendar list-events (read; ``calendar.readonly``; ``build("calendar","v3")``).

    The Events.list response key is ``items`` (NOT ``events``); each item's
    ``start``/``end`` are objects (``{dateTime}`` for timed, ``{date}`` for all-day),
    but ``google_calendar_list_events.output`` declares them as ``string`` — so we
    extract ``dateTime or date``. Maps ``id`` -> ``event_id``. Optional keys are
    OMITTED when absent (the items allow additionalProperties but the declared fields
    are string-typed, so a null would mismatch).
    """
    if credential is None:  # defensive D-11 (execute() also guards before dispatch)
        return None
    creds = _build_credentials(credential, [_CALENDAR_READONLY])
    service = _service("calendar", "v3", creds)
    list_kwargs: dict[str, Any] = {
        "calendarId": params["calendar_id"],
        "maxResults": params.get("max_results", 25),
        "singleEvents": True,
        "orderBy": "startTime",
    }
    if params.get("time_min"):
        list_kwargs["timeMin"] = params["time_min"]
    if params.get("time_max"):
        list_kwargs["timeMax"] = params["time_max"]
    resp = service.events().list(**list_kwargs).execute()
    events: list[dict[str, str]] = []
    for ev in resp.get("items", []):
        item: dict[str, str] = {"event_id": ev["id"]}
        if ev.get("summary"):
            item["summary"] = ev["summary"]
        start = ev.get("start") or {}
        start_val = start.get("dateTime") or start.get("date")
        if start_val:
            item["start"] = start_val
        end = ev.get("end") or {}
        end_val = end.get("dateTime") or end.get("date")
        if end_val:
            item["end"] = end_val
        events.append(item)
    return {"events": events}


def _calendar_create_event(
    spec: ToolSpec, params: dict, *, credential: str | None
) -> dict | None:
    """Calendar create-event (write; ``calendar.events``; events().insert). Reached
    only AFTER the ledger approves (manifest ``approval_required: true``). Maps the
    created event's ``id`` -> ``event_id`` and ``htmlLink`` -> ``html_link``.
    """
    if credential is None:  # defensive D-11
        return None
    creds = _build_credentials(credential, [_CALENDAR_EVENTS])
    service = _service("calendar", "v3", creds)
    body: dict[str, Any] = {
        "summary": params["summary"],
        "start": {"dateTime": params["start"]},
        "end": {"dateTime": params["end"]},
    }
    if params.get("description"):
        body["description"] = params["description"]
    if params.get("attendees"):
        body["attendees"] = [{"email": e} for e in params["attendees"]]
    created = (
        service.events()
        .insert(calendarId=params["calendar_id"], body=body)
        .execute()
    )
    out: dict[str, str] = {"event_id": created["id"]}
    if created.get("htmlLink"):
        out["html_link"] = created["htmlLink"]
    return out


def _docs_get(spec: ToolSpec, params: dict, *, credential: str | None) -> dict | None:
    """Docs get (read; ``documents.readonly``; ``build("docs","v1")``; documents().get).

    The API returns ``body.content[]`` structural elements; ``text`` is a REQUIRED
    output field, so we walk ``content[].paragraph.elements[].textRun.content`` and
    join (returning "" would pass the schema but be a dead read). Maps ``documentId``
    -> ``document_id`` and ``title``.
    """
    if credential is None:  # defensive D-11
        return None
    creds = _build_credentials(credential, [_DOCS_READONLY])
    service = _service("docs", "v1", creds)
    doc = service.documents().get(documentId=params["document_id"]).execute()
    parts: list[str] = []
    for element in doc.get("body", {}).get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for run in paragraph.get("elements", []):
            text_run = run.get("textRun")
            if text_run and text_run.get("content"):
                parts.append(text_run["content"])
    out: dict[str, str] = {
        "document_id": doc.get("documentId", params["document_id"]),
        "text": "".join(parts),
    }
    if doc.get("title"):
        out["title"] = doc["title"]
    return out


def _docs_create(
    spec: ToolSpec, params: dict, *, credential: str | None
) -> dict | None:
    """Docs create (write; ``documents``; documents().create). Reached only AFTER the
    ledger approves. ``documents().create`` accepts only ``title`` (folder placement /
    body content would need extra Drive-move / batchUpdate calls — out of scope for
    this representative write; writes aren't in the live read lane). Maps ``documentId``
    -> ``document_id`` and ``title``.
    """
    if credential is None:  # defensive D-11
        return None
    creds = _build_credentials(credential, [_DOCS])
    service = _service("docs", "v1", creds)
    created = service.documents().create(body={"title": params["title"]}).execute()
    out: dict[str, str] = {"document_id": created["documentId"]}
    if created.get("title"):
        out["title"] = created["title"]
    return out


def _slides_get(
    spec: ToolSpec, params: dict, *, credential: str | None
) -> dict | None:
    """Slides get (read; ``presentations.readonly``; ``build("slides","v1")``;
    presentations().get). Walks each slide's
    ``pageElements[].shape.text.textElements[].textRun.content`` and maps slide
    ``objectId`` -> ``slide_id``; maps ``presentationId`` -> ``presentation_id`` and
    ``title``. A slide with no extractable text still appears (slide_id only).
    """
    if credential is None:  # defensive D-11
        return None
    creds = _build_credentials(credential, [_SLIDES_READONLY])
    service = _service("slides", "v1", creds)
    pres = (
        service.presentations().get(presentationId=params["presentation_id"]).execute()
    )
    slides: list[dict[str, str]] = []
    for slide in pres.get("slides", []):
        entry: dict[str, str] = {}
        if slide.get("objectId"):
            entry["slide_id"] = slide["objectId"]
        parts: list[str] = []
        for page_element in slide.get("pageElements", []):
            text = page_element.get("shape", {}).get("text", {})
            for te in text.get("textElements", []):
                text_run = te.get("textRun")
                if text_run and text_run.get("content"):
                    parts.append(text_run["content"])
        if parts:
            entry["text"] = "".join(parts)
        slides.append(entry)
    out: dict[str, Any] = {
        "presentation_id": pres.get("presentationId", params["presentation_id"])
    }
    if pres.get("title"):
        out["title"] = pres["title"]
    if slides:
        out["slides"] = slides
    return out


def _slides_create(
    spec: ToolSpec, params: dict, *, credential: str | None
) -> dict | None:
    """Slides create (write; ``presentations``; presentations().create). Reached only
    AFTER the ledger approves. ``presentations().create`` accepts only ``title``
    (folder placement would need an extra Drive-move call — out of scope for this
    representative write). Maps ``presentationId`` -> ``presentation_id`` and ``title``.
    """
    if credential is None:  # defensive D-11
        return None
    creds = _build_credentials(credential, [_SLIDES])
    service = _service("slides", "v1", creds)
    created = (
        service.presentations().create(body={"title": params["title"]}).execute()
    )
    out: dict[str, str] = {"presentation_id": created["presentationId"]}
    if created.get("title"):
        out["title"] = created["title"]
    return out


# Internal dispatch map: spec.name -> op. 04-07 extends this in place with
# Calendar/Docs/Slides entries (no new register call).
_GWS_OPS = {
    "google_drive_search": _drive_search,
    "gmail_send": _gmail_send,
    "google_sheets_append": _sheets_append,
    "google_calendar_list_events": _calendar_list_events,
    "google_calendar_create_event": _calendar_create_event,
    "google_docs_get": _docs_get,
    "google_docs_create": _docs_create,
    "google_slides_get": _slides_get,
    "google_slides_create": _slides_create,
}


def google_workspace_adapter(
    spec: ToolSpec, params: dict, *, credential: str | None
) -> dict | None:
    """Single dispatcher for the shared ``google_workspace`` provider key.

    Routes by ``spec.name`` to the matching op in ``_GWS_OPS``. An unknown name returns
    ``None`` so the gateway degrades to the deterministic stub rather than raising
    (defensive; the gateway only dispatches names that resolved to this provider).
    """
    op = _GWS_OPS.get(spec.name)
    if op is None:
        return None
    return op(spec, params, credential=credential)


# EXACTLY ONE registration under the shared provider key (04-03 invariant: one
# dispatcher per provider key, routing by spec.name). NOT one per op.
register("google_workspace", google_workspace_adapter)
