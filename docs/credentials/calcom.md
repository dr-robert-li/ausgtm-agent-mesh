# Cal.com credential & header setup (D-12)

The Cal.com direct adapter (`calcom_list_bookings` read + `calcom_create_booking`
approval-gated write — D-07, TOOL-03) authenticates with a single **API key** over
Cal.com **API v2** (`https://api.cal.com/v2`). No SDK and no new dependency: the adapter
calls the API over the core `httpx` dependency. The key is resolved only at execution
time inside `ToolGateway.execute()` (D-02) and is never logged or returned. With the key
unset the adapter degrades to the deterministic stub (D-11) and the default test suite
stays green and creds-free.

## 1. Mint an API key

In Cal.com: **Settings -> Developer -> API Keys -> Add** (or **+ Add**). Copy the key —
it is prefixed `cal_`. Cal.com shows the key only once.

Set it in the environment for the live lane:

```bash
export CALCOM_API_KEY="cal_xxxxxxxxxxxxxxxxxxxxxxxx"
```

## 2. The MANDATORY dated `cal-api-version` header (the 400 gotcha)

Every Cal.com **v2** bookings call MUST send the dated header:

```
cal-api-version: 2026-05-01
```

in addition to `Authorization: Bearer <CALCOM_API_KEY>`. A **missing or wrong**
`cal-api-version` value makes the API return **400** on every call — it is not optional.
The adapter pins the version as the module constant `_CAL_API_VERSION = "2026-05-01"` and
sends it on **both** ops (list and create); a default-lane header test asserts both ops
emit it.

## 3. The `event_type_id` resource binding (write only)

`calcom_create_booking` (the approval-gated write) needs the **event type** to book
against. That comes from the manifest `resource_bindings.event_type_id`, NOT from the
environment and NOT from agent input. Find the numeric event-type id in Cal.com under
**Event Types -> (your event) -> URL / settings**, then replace the manifest placeholder
`REPLACE_WITH_EVENT_TYPE_ID` for `calcom_create_booking` with the real id.

> **Operator note — the live lane needs REAL bindings, not just the key.** The live read
> (`tests/test_calcom_live.py`) **skips** when `CALCOM_API_KEY` is unset, but it does NOT
> skip on a placeholder binding. If you set the key but leave a placeholder such as
> `REPLACE_WITH_EVENT_TYPE_ID` in the manifest, a write live call would **error** (a bad
> event-type id) instead of skipping. The shipped live test exercises only the read
> (which needs no `event_type_id`); the write mapping is proven in the default lane and
> its live execution stays behind the approval ledger.

## 4. Approval gate (write)

`calcom_create_booking` is category `write`, so `approval_required: true` is a manifest
invariant (05-01) and the booking is created only after a human approves the
payload-hash-bound write through the shared ledger. The adapter itself performs no
gating — it is reached only after the worker approval gate clears.

## Endpoints used

| Tool | Method + path | Output schema |
| :--- | :--- | :--- |
| `calcom_list_bookings` (read) | `GET https://api.cal.com/v2/bookings` | `schemas/calcom_list_bookings.output.schema.json` |
| `calcom_create_booking` (write) | `POST https://api.cal.com/v2/bookings` | `schemas/calcom_create_booking.output.schema.json` |

Both calls send `Authorization: Bearer <key>` + `cal-api-version: 2026-05-01`.
