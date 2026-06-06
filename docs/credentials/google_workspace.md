# Google Workspace credentials (`GOOGLE_WORKSPACE_OAUTH`) — D-12

The Google Workspace direct adapter (`tools/adapters/google_workspace.py`) drives
all six products — Drive, Gmail, Sheets, Calendar, Docs, Slides — from a **single
OAuth client plus one stored refresh token**. One refresh token mints short-lived
access tokens on demand and auto-refreshes via
`google.oauth2.credentials.Credentials`, so the live lane runs unattended. The single
OAuth client must be granted the **union** of all six products' scopes (table below).

The Tool Gateway resolves the secret **only at execution time** (D-02): it is never
returned to the agent, set as a span attribute, or logged. Store it as a secret env
var / Secret Manager entry — never in code.

## Credential shape

`GOOGLE_WORKSPACE_OAUTH` resolves to a single JSON blob (NOT a bare token):

```json
{
  "client_id": "xxxx.apps.googleusercontent.com",
  "client_secret": "GOCSPX-xxxx",
  "refresh_token": "1//xxxx"
}
```

The adapter parses this blob and builds:

```python
Credentials(
    token=None,
    refresh_token=blob["refresh_token"],
    token_uri="https://oauth2.googleapis.com/token",
    client_id=blob["client_id"],
    client_secret=blob["client_secret"],
    scopes=[...],  # per-product, least-privilege (table below)
)
```

## Step 1 — Create the OAuth client (Desktop) in Google Cloud Console

1. In the Google Cloud Console, select (or create) the project, then enable the APIs
   you need: **Google Drive API**, **Gmail API**, **Google Sheets API**, **Google
   Calendar API**, **Google Docs API**, **Google Slides API** (all six products are
   live as of 04-07).
2. Configure the **OAuth consent screen** (Internal for a Workspace org, or External +
   test users for the POC). Add the per-product scopes from the table below.
3. Under **APIs & Services -> Credentials -> Create credentials -> OAuth client ID**,
   choose application type **Desktop app**. Download the client-secret JSON; note its
   `client_id` and `client_secret`.

## Step 2 — Mint the refresh token (one-time consent)

Run the one-time consent locally with `google-auth-oauthlib` (the `tools` extra). This
is the **only** place the consent flow runs — never in the live test path:

```python
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/presentations.readonly",
    "https://www.googleapis.com/auth/presentations",
]
flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(access_type="offline", prompt="consent")
print(creds.refresh_token)  # store into the GOOGLE_WORKSPACE_OAUTH blob
```

`access_type="offline"` + `prompt="consent"` guarantees a refresh token is returned.
The refresh token is long-lived; **rotation = re-run this consent flow**.

## Step 3 — Assemble and export the secret

```bash
export GOOGLE_WORKSPACE_OAUTH='{"client_id":"...","client_secret":"...","refresh_token":"..."}'
```

With it set, `pytest -m live tests/test_gws_live.py` runs a real Drive search; without
it, the live lane SKIPS and the default suite stays green and creds-free (the adapter
degrades to the deterministic stub, D-11).

## Per-product scopes (least-privilege — full six-product suite)

The single OAuth client is granted the **union** of these scopes; each adapter op
requests only its own product's read or write scope at execution time.

| Product  | Operation | Category | Scope |
| :--- | :--- | :--- | :--- |
| Drive    | `google_drive_search` (read)         | read         | `https://www.googleapis.com/auth/drive.readonly` |
| Gmail    | `gmail_send`                          | external_send| `https://www.googleapis.com/auth/gmail.send` |
| Sheets   | `google_sheets_append`               | write        | `https://www.googleapis.com/auth/spreadsheets` |
| Calendar | `google_calendar_list_events` (read) | read         | `https://www.googleapis.com/auth/calendar.readonly` |
| Calendar | `google_calendar_create_event`       | write        | `https://www.googleapis.com/auth/calendar.events` |
| Docs     | `google_docs_get` (read)             | read         | `https://www.googleapis.com/auth/documents.readonly` |
| Docs     | `google_docs_create`                 | write        | `https://www.googleapis.com/auth/documents` |
| Slides   | `google_slides_get` (read)           | read         | `https://www.googleapis.com/auth/presentations.readonly` |
| Slides   | `google_slides_create`               | write        | `https://www.googleapis.com/auth/presentations` |

Least-privilege by design (RESEARCH A7): each read uses its product's `*.readonly`
scope, **not** the full read/write scope. Reads are ungated; writes/sends are
approval-gated by the manifest + ledger. Request only the scopes the deployed ops need.
