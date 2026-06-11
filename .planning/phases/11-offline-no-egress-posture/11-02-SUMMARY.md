---
phase: 11-offline-no-egress-posture
plan: 02
subsystem: offline-posture / test-assurance
tags: [offline, OFFLINE-03, deny-guard, getaddrinfo, litellm, zero-src]
requires: [model_gateway.build_router, config/model_gateway.vllm.yaml, tests/conftest.py:live_creds]
provides: [tests/test_offline_deny_guard.py, cloud-LLM-host-deny-guard, non-vacuous-OFFLINE-03-proof]
affects: [default make test lane]
tech-stack:
  added: []
  patterns: [function-scoped-autouse-deny-guard, creds-gated-no-op, sync+async-positive-control, non-vacuous-representative-path]
key-files:
  created: [tests/test_offline_deny_guard.py]
  modified: []
decisions: [assert-on-unique-OFFLINE-deny-message-not-anthropic.com-OR]
metrics:
  duration: ~25m
  completed: 2026-06-11
---

# Phase 11 Plan 02: Cloud-LLM Egress Deny-Guard (OFFLINE-03) Summary

A `socket.getaddrinfo` autouse deny-guard (D-02) that raises ONLY on cloud-LLM hosts,
proving the default creds-free lane performs no outbound to a real LLM provider/gateway,
asserted non-vacuously by sync+async `anthropic/` positive controls plus a representative
routed completion through the active local (loopback) profile. Zero `src/` change.

## What Was Built

`tests/test_offline_deny_guard.py` — entirely in `tests/`, in the default `make test -m "not live"` lane:

- **`_is_cloud_llm_host(host)`** — denies the exact host list (`api.anthropic.com`,
  `anthropic.com`, `aiplatform.googleapis.com`, `gateway.ai.cloudflare.com`) plus the
  regional Vertex shape (`*-aiplatform.googleapis.com`) and CF subdomain shape
  (`*.gateway.ai.cloudflare.com`). Precise Vertex match — bare `googleapis.com` and
  `sheets.googleapis.com` pass through (legitimate SaaS Google APIs).
- **`_cloud_llm_deny_guard`** — `@pytest.fixture(autouse=True)`, function-scoped (the
  autouse default; NOT `scope="module"`, which would `ScopeMismatch` against function-scoped
  `monkeypatch`). Patches `socket.getaddrinfo` to raise `RuntimeError("OFFLINE deny: ...")`
  only on cloud-LLM hosts; every other host delegates to the real resolver. The DNS seam
  is chosen over `create_connection` because it fires on BOTH the sync (httpcore) and async
  (anyio) httpx backends — the async path is the one the real worker uses (Pitfall 1).
  Sets `LITELLM_LOCAL_MODEL_COST_MAP=True` to suppress the cost-map fetch to
  raw.githubusercontent.com (Pitfall 3). No-ops (yields without patching) when any of
  `ANTHROPIC_API_KEY` / `VERTEX_PROJECT_ID` / `CF_AIG_WRAPPER_URL` is set, mirroring
  conftest `live_creds` so `make test-live` is unaffected (Pitfall 4).
- **Host-classification unit tests** — assert the precise-Vertex and CF/Anthropic matching.
- **Sync positive control** — `litellm.completion(anthropic/...)` trips the guard.
- **Async positive control** — `litellm.acompletion(anthropic/...)` via `asyncio.run` trips
  the guard (the path the real LangGraph/Deep Agents worker uses). `vertex_ai/` deliberately
  NOT used (dies at `DefaultCredentialsError` before connect in the creds-free lane — Pitfall 2).
- **Representative default-lane path** — `build_router("config/model_gateway.vllm.yaml")`
  (loopback api_base) drives one completion under the guard. Connection-refused/timeout to
  `http://localhost:8000` is PASS; only `"OFFLINE deny"` in the error fails it. Because
  `build_router` is lazy, this is what makes the proof non-vacuous (Pitfall 5).

## Tasks

| Task | Name | Commit |
| ---- | ---- | ------ |
| 1 | getaddrinfo deny-guard + sync/async positive controls | 543e9a7 |
| 2 | representative default-lane local-profile path | 182613f |
| (hardening) | tighten positive controls to unique guard message | 1ffb70c |

## Verification

- `.venv/bin/python -m pytest tests/test_offline_deny_guard.py -m "not live" -x` → 5 passed.
- Full lane `.venv/bin/python -m pytest -m "not live"` → 342 passed, 10 skipped, 23 deselected (live).
- `git status --porcelain src/` → empty (zero `src/` change).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Assurance bug] Positive-control assertion was wrong-reason-passable**
- **Found during:** post-execution review (advisor)
- **Issue:** The planned assertion `"OFFLINE deny" in str(e) or "anthropic.com" in str(e)`
  could pass even with the guard removed — a fake-key `anthropic/` call raises an error
  containing "anthropic.com" anyway (a 401 / plain connect error). That is exactly the
  wrong-reason pass the plan's own threat register flags as **T-11-07**, making the
  positive control vacuous.
- **Fix:** Empirically confirmed (sync + async) that the guard's unique `RuntimeError`
  message survives litellm's `InternalServerError` wrapping, then tightened both controls
  to assert `"OFFLINE deny" in str(e)` only. "OFFLINE deny" can ONLY originate from the
  guard, so the control now provably passes because the guard fired.
- **Files modified:** tests/test_offline_deny_guard.py
- **Commit:** 1ffb70c

## Threat Register Outcome

- **T-11-05** (async exfiltration) — mitigated: `getaddrinfo` guard catches sync+async; async positive control present.
- **T-11-06** (vacuous guard) — mitigated: representative routed completion under the guard (Pitfall 5).
- **T-11-07** (wrong-reason pass) — mitigated: positive controls use `anthropic/` (reach the seam) AND assert on the guard's unique message (hardening commit 1ffb70c).
- **T-11-08** (allowlist too broad) — controlled: precise `aiplatform.googleapis.com` match (not bare googleapis.com) + creds-gated no-op.
- **T-11-SC** (supply chain) — N/A: no package installs in this plan.

## Known Stubs

None. The deliverable is a self-contained test asserting an existing property; no stubbed data paths.

## Self-Check: PASSED

- `tests/test_offline_deny_guard.py` — FOUND.
- Commits 543e9a7, 182613f, 1ffb70c — FOUND in `git log`.
- `git status --porcelain src/` — empty.
