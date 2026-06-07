# Beehiiv credential (`BEEHIIV_API_KEY`)

The Beehiiv direct adapter (`src/agent_mesh/tools/adapters/beehiiv.py`, TOOL-03) ships one
tool — `beehiiv_create_post`, an **approval-gated publishing write** that creates a
newsletter post **as a draft only** (it never auto-publishes). It calls Beehiiv API v2
over the core `httpx` dependency (no SDK).

## What you need

| Item | Env var / binding | Where |
|------|-------------------|-------|
| API key | `BEEHIIV_API_KEY` | Beehiiv dashboard (mint steps below) |
| Publication id | `resource_bindings.publication_id` in the tool-pack manifest | Beehiiv publication URL / API |
| (live test, opt-in) publication id | `BEEHIIV_LIVE_PUBLICATION_ID` | same as above |

## Mint the API key

1. Sign in to Beehiiv.
2. Go to **Settings → Integrations → API** (in newer dashboards: **Developers → Create an
   API Key**).
3. Create an API key and copy it once.
4. Export it for the live lane (the default lane needs no key — it stubs):

   ```bash
   export BEEHIIV_API_KEY="<your-api-key>"
   ```

The platform passes this key only as the adapter's `credential` argument, resolved at
execution time inside the gateway. It is **never** logged, returned, or read from the
environment by the adapter itself (the adapter reads no `os.getenv`).

## Auth header

The adapter sends:

```
Authorization: Bearer <BEEHIIV_API_KEY>
```

against `POST https://api.beehiiv.com/v2/publications/{publication_id}/posts`.

## Publication id binding

Bind your publication id in the tool-pack manifest under the tool's `resource_bindings`:

```yaml
resource_bindings:
  publication_id: "pub_xxxxxxxx"
```

This is a **deployment-specific** value (per the platform/client boundary) — keep it out
of the reusable platform code.

## Draft-only guarantee

`beehiiv_create_post` **always** sends `status: "draft"`. Even if a caller passes
`status: "confirmed"` (or any other value), the adapter overrides it — this tool never
auto-publishes a live post. A default-lane test asserts the override. Publishing a draft
is a separate human action in the Beehiiv UI.

## Approval gate

`beehiiv_create_post` is `category: publishing` → `approval_required: true` in the
manifest. It is reached only after the shared human-in-the-loop approval gate has approved
the payload-hash-bound write. The adapter performs no gating of its own.

## Enterprise-tier 403 caveat

`create-post` is **beta / Enterprise-tier-gated**. A non-Enterprise API key may return
**HTTP 403** on the create call. This is expected on lower tiers:

- The **default lane** stubs the call regardless of tier (no key, no network).
- The **live lane** (`pytest -m live tests/test_beehiiv_live.py`) treats a `403` as a
  **skip**, not a failure, and documents the tier gate.

If you need the live create to succeed, use an Enterprise-tier key and set both
`BEEHIIV_API_KEY` and `BEEHIIV_LIVE_PUBLICATION_ID`.
