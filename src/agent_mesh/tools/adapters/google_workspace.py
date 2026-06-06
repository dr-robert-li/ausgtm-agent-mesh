"""Google Workspace direct adapter — shared auth scaffold + single dispatcher (D-08).

This module ships the FIRST half of the full Google Workspace direct suite: the
shared OAuth/refresh auth scaffold plus three ops — Drive search (read), Gmail send
(external_send, approval-gated upstream), and Sheets append (write, approval-gated
upstream). 04-07 EXTENDS this same file with Calendar/Docs/Slides by adding entries
to ``_GWS_OPS`` — it does NOT add another ``register`` call (which would last-wins
collide and silently make most ops unreachable).

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


# Internal dispatch map: spec.name -> op. 04-07 extends this in place with
# Calendar/Docs/Slides entries (no new register call).
_GWS_OPS = {
    "google_drive_search": _drive_search,
    "gmail_send": _gmail_send,
    "google_sheets_append": _sheets_append,
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
