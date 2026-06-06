# Google Workspace credentials (`GOOGLE_WORKSPACE_OAUTH`) — D-12

The Google Workspace direct adapter (`tools/adapters/google_workspace.py`) drives
Drive, Gmail, Sheets (this plan) — and, once 04-07 lands, Calendar, Docs, Slides —
from a **single OAuth client plus one stored refresh token**. One refresh token mints
short-lived access tokens on demand and auto-refreshes via
`google.oauth2.credentials.Credentials`, so the live lane runs unattended.

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
   you need: **Google Drive API**, **Gmail API**, **Google Sheets API** (add
   Calendar / Docs / Slides APIs when 04-07 ships).
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

## Per-product scopes (least-privilege — this plan: Drive/Gmail/Sheets)

| Product | Operation (this plan) | Scope |
| :--- | :--- | :--- |
| Drive   | `google_drive_search` (read)          | `https://www.googleapis.com/auth/drive.readonly` |
| Gmail   | `gmail_send` (external_send)           | `https://www.googleapis.com/auth/gmail.send` |
| Sheets  | `google_sheets_append` (write)         | `https://www.googleapis.com/auth/spreadsheets` |

Least-privilege by design (RESEARCH A7): Drive uses `drive.readonly`, **not** the full
`https://www.googleapis.com/auth/drive` scope. Request only the scopes the deployed
ops need.

## Calendar / Docs / Slides scopes — see 04-07

04-07 extends this adapter (and this doc) with the Calendar, Docs, and Slides
operations and their scopes:

| Product  | Scope (added by 04-07) |
| :--- | :--- |
| Calendar | `https://www.googleapis.com/auth/calendar.events` |
| Docs     | `https://www.googleapis.com/auth/documents` |
| Slides   | `https://www.googleapis.com/auth/presentations` |

When you add those ops, append their scopes to the consent flow and re-mint the refresh
token so the single `GOOGLE_WORKSPACE_OAUTH` blob covers all six products.
