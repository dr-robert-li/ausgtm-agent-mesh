# Bitscale credential (`BITSCALE_API_KEY`)

The Bitscale direct adapter (`provider: bitscale`, `direct_api`) calls the live Bitscale
REST API over core `httpx` — no SDK, no extra dependency. Base URL:
`https://api.bitscale.ai/api/v1`.

## Mint the API key

1. Sign in to the Bitscale dashboard for the target workspace
   (the POC target is the client's real `australiagtm.com` workspace).
2. Open **Settings → API key** and create / copy an API key.
3. Store it as the environment variable / secret `BITSCALE_API_KEY`
   (already wired into `.env` / `.env.example`). In GCP it lives in Secret Manager and
   is resolved at execution time by the Tool Gateway — agents never see it.

## Auth header — `X-API-Key` (NOT Bearer)

Bitscale authenticates with the **`X-API-Key`** request header:

```
X-API-Key: <BITSCALE_API_KEY>
```

It is **not** a bearer token. `Authorization: Bearer …`, `api-key`, and `apikey` all
return `401`; only `X-API-Key` / `x-api-key` return `200` (verified by live curl). The
adapter sends `X-API-Key` and never an `Authorization` header.

## Resource binding — `grid_id`

`resource_bindings.grid_id` binds a specific Bitscale grid. It is required only for the
**write** op `bitscale_run_grid` (which targets `POST /grids/{grid_id}/run`). The two
credit-free reads (`bitscale_list_grids`, `bitscale_get_workspace`) do **not** need
`grid_id`.

The manifest ships `grid_id: REPLACE_WITH_BITSCALE_GRID_ID` as a placeholder. Operator
note: the live test lane (the credit-free reads) skips only on a **missing
`BITSCALE_API_KEY`**, not on a placeholder binding. The reads ignore `grid_id`, so the
placeholder is harmless for them — but for any op that consumes `grid_id` (i.e.
`run_grid`) a left-in `REPLACE_WITH_BITSCALE_GRID_ID` would **error the call** rather
than skip it. Set a real `grid_id` before exercising any grid-bound op.

## CREDIT-SAFETY — `bitscale_run_grid` consumes paid credits

`bitscale_run_grid` appends a row and triggers enrichment on a **real** leads grid and
**consumes the client's paid Bitscale credits** (the `australiagtm.com` workspace is on a
real paid plan).

- It is **approval-gated upstream**: the manifest declares it `category: write` →
  `approval_required: true`, so it only executes after the human-in-the-loop
  payload-hash-bound approval gate. The adapter performs no gating bypass.
- It is **never exercised in the live test lane**. `tests/test_bitscale_live.py` is
  **reads only** (`bitscale_list_grids`, `bitscale_get_workspace`) and contains no
  `run_grid` call. The write path / mapping is proven through the default-lane
  fake-httpx unit test (no network, no credit spend) + the upstream approval gate — never
  a live call.

## Ops

| Op | HTTP | Category | Credits |
| --- | --- | --- | --- |
| `bitscale_list_grids` | `GET /grids` | read | credit-free |
| `bitscale_get_workspace` | `GET /workspace` | read | credit-free |
| `bitscale_run_grid` | `POST /grids/{grid_id}/run` | write (approval-gated) | **consumes paid credits** |

## Degradation

When `BITSCALE_API_KEY` is absent the engine degrades to the deterministic stub before
reaching the adapter (D-11), so `make test` stays green and creds-free. `httpx` is a core
dependency, so there is no opt-in-SDK branch — the only degrade path is a missing key.
