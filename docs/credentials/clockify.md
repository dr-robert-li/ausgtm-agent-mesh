# Clockify credential & scope setup (D-12)

The Clockify direct adapter (`clockify_read_time_entries` — read-only this phase, TOOL-03)
authenticates with a single **API key** sent in the **`X-Api-Key` header** (NOT a Bearer
token). The key is resolved only at execution time inside `ToolGateway.execute()` (D-02)
and is never logged or returned. With the key unset the adapter degrades to the
deterministic stub (D-11) and the default test suite stays green and creds-free.

> **No SDK / no extra dependency:** the adapter calls Clockify API v1 over the core
> `httpx` dependency. There is no opt-in package to install and no `ImportError` degrade
> branch — the only stub path is an absent credential.

## 1. Mint the API key

1. Sign in to Clockify.
2. Go to **Profile Settings** (bottom-left avatar -> Profile Settings).
3. Scroll to the **API** section -> **Generate** (or copy an existing key).
4. Copy the generated key — this is your `CLOCKIFY_API_KEY`.

> **Subdomain caveat:** if your organization uses a **subdomain workspace**
> (`https://<org>.clockify.me`), the regular profile API key will NOT authenticate
> against the standard `api.clockify.me` host — you must mint a **subdomain-specific
> key** from that subdomain's settings. Using the wrong key returns 401. The adapter
> always calls the standard host `https://api.clockify.me/api/v1`; if your deployment is
> subdomain-scoped, confirm the key was minted under the subdomain.

## 2. Auth header

The adapter sends the key in the **`X-Api-Key`** header:

```
X-Api-Key: <the-api-key>
```

It does **NOT** use `Authorization: Bearer ...`. Sending the key as a Bearer token will
fail with 401.

## 3. Resource bindings (`workspace_id` + `user_id`)

The read endpoint needs BOTH a workspace and a user segment:

```
GET https://api.clockify.me/api/v1/workspaces/{workspaceId}/user/{userId}/time-entries
```

So the manifest's `resource_bindings` for `clockify_read_time_entries` must supply both:

```yaml
resource_bindings:
  workspace_id: "<your-clockify-workspace-id>"
  user_id: "<the-target-user-id>"
```

These are **operator-bound** (set in the manifest, not free agent input) — the adapter
never lets an agent choose which workspace/user to read (T-05-05-02).

To resolve the ids:

- **`user_id`** — call `GET https://api.clockify.me/api/v1/user` with your
  `X-Api-Key`; the response `id` is the caller's user id.
- **`workspace_id`** — call `GET https://api.clockify.me/api/v1/workspaces`; pick the
  `id` of the workspace you want, or read it from the workspace URL in the Clockify UI.

## 4. Environment variable

The gateway resolves the key from the secret named `CLOCKIFY_API_KEY`:

```bash
export CLOCKIFY_API_KEY='<the-api-key>'
```

## 5. Live-lane operator note

`pytest -m live tests/test_clockify_live.py` **skips** when `CLOCKIFY_API_KEY` is unset.
But the live lane ALSO needs **real** `resource_bindings` in the manifest — the live read
does NOT skip on placeholder bindings. If `workspace_id` / `user_id` are left at their
manifest placeholders (e.g. `REPLACE_WITH_CLOCKIFY_WORKSPACE_ID`), the live call ERRORS
(404 / raise) instead of skipping. Replace both bindings with real ids before running the
live lane.
