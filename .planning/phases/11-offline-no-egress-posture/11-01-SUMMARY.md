---
phase: 11-offline-no-egress-posture
plan: 01
subsystem: offline-egress-assertion
tags: [OFFLINE-02, D-01, D-04, no-cloud-llm-egress, config-validation, tests-only]
requires:
  - "config/model_gateway.{vllm,ollama,vllm.compose,cpu.compose}.yaml (4 frozen local profiles — sweep targets)"
  - "config/model_gateway.cloud.yaml (frozen negative control)"
  - "docker-compose.yml api/worker env blocks (D-04 sweep target)"
provides:
  - "Whole-file cloud-LLM-marker sweep across all 4 local profiles (OFFLINE-02, gap LOCAL-04 left open)"
  - "Loopback-OR-service-DNS api_base allowlist for the 2 compose profiles"
  - "cloud.yaml negative control: _FILE_DENY MUST trip (non-vacuous proof)"
  - "docker-compose api/worker valued-cloud-key + cloud-host env sweep (D-04)"
affects:
  - "tests/test_local_profiles.py (extended)"
  - "tests/test_offline_compose_env.py (new)"
tech-stack:
  added: []
  patterns:
    - "Whole-file read_text() deny-marker sweep (extends LOCAL-04 api_base-only guard)"
    - "Negative control mirroring test_d06_chokepoint.py:180 (guard non-vacuity)"
    - "Valued-key semantics (present-but-blank OK, valued = violation) for compose env"
    - "dict / KEY=VALUE list env normalization; static yaml.safe_load (no docker daemon)"
key-files:
  created:
    - "tests/test_offline_compose_env.py"
  modified:
    - "tests/test_local_profiles.py"
decisions:
  - "Kept _FILE_DENY cloud-LLM-scoped: omitted 'openai' (no OpenAI route; would false-positive on vLLM 'OpenAI-compatible' prose) — CONTEXT Discretion + RESEARCH A3"
  - "Did NOT add the justified-but-optional sk-ant- / aiplatform.googleapis.com / gateway.ai.cloudflare.com markers; they are strict subsets of floor markers (sk-, googleapis.com) already swept, so adding them changes no sweep outcome — kept the D-01 floor exactly"
metrics:
  duration: "~15 min"
  completed: "2026-06-11"
  tasks: 2
  files: 2
---

# Phase 11 Plan 01: Offline No-Egress Posture (profile + compose env sweep) Summary

OFFLINE-02 is now an asserted property: a whole-file cloud-LLM-marker sweep across all
4 local model profiles (loopback + service-DNS) plus a docker-compose api/worker env
valued-cloud-key sweep prove the local/offline model surface is egress-free by
construction, with the frozen `cloud.yaml` as a negative control that fails loudly if
the marker list is ever emptied.

## What Was Built

**Task 1 — extended `tests/test_local_profiles.py` (D-01):**
- Added the 2 P10 compose profiles (`vllm-compose`, `cpu-compose`) to `_PROFILES` → 4 profiles.
- Added `_SERVICE_DNS = ("http://vllm:8000", "http://ollama:11434")` and `_LOCAL_ALLOW = _LOOPBACK + _SERVICE_DNS`; renamed the api_base test to
  `test_every_route_api_base_is_loopback_or_service_dns` so the 2 loopback profiles still
  pass on loopback and the 2 compose profiles pass on in-stack service-DNS.
- Added `_FILE_DENY = ("CF_AIG_WRAPPER_URL", "vertex_ai", "googleapis.com", "anthropic", "anthropic.com", "sk-")`
  and a parametrized whole-file `read_text()` sweep over all 4 profiles — the gap the
  api_base-only LOCAL-04 guard left open. `openai` deliberately omitted (RESEARCH A3).
- Added the negative control `test_cloud_reference_profile_does_trip_the_sweep`: the
  pristine `config/model_gateway.cloud.yaml` MUST trip `_FILE_DENY` (it trips 3 markers:
  `CF_AIG_WRAPPER_URL`, `vertex_ai`, `anthropic`), mirroring `test_d06_chokepoint.py:180`.

**Task 2 — new `tests/test_offline_compose_env.py` (D-04):**
- Static `yaml.safe_load` over `docker-compose.yml` (no docker daemon, no `skipif`).
- `_CLOUD_KEY_NAMES` valued-key sweep over the `api` and `worker` env blocks:
  present-but-blank OK, present-and-valued = violation.
- Cloud-host substring sweep (`googleapis.com`, `anthropic`, `gateway.ai.cloudflare.com`)
  over env values; local `@postgres`/`@langfuse-web`/blank `LANGFUSE_*`/`TMPDIR` stay legit.
- `_env_items` normalizes both dict and `KEY=VALUE` list env forms; a non-empty-block
  sanity guard keeps the sweep non-vacuous.

## How to Verify

```
.venv/bin/python -m pytest tests/test_local_profiles.py tests/test_offline_compose_env.py -m "not live"
```
→ 27 passed. Full default lane (`PYTHONPATH=src .venv/bin/python -m pytest -q -m "not live"`)
→ 337 passed, 10 skipped, 0 failures.

Negative-control / non-vacuity (verified): `_FILE_DENY` trips `cloud.yaml` on
`['CF_AIG_WRAPPER_URL', 'vertex_ai', 'anthropic']` and produces ZERO hits on all 4 local
profiles.

## Deviations from Plan

None — plan executed exactly as written.

> Note (decision, not a deviation): the plan's `_FILE_DENY` floor was used exactly. RESEARCH
> listed `sk-ant-`, `aiplatform.googleapis.com`, and `gateway.ai.cloudflare.com` as
> *optional, justified additions*. They are strict substrings of floor markers already in the
> sweep (`sk-`, `googleapis.com`), so including them changes no sweep outcome; the D-01 floor
> (which the plan action specified verbatim) was kept to match the plan and CONTEXT precisely.

## Known Stubs

None.

## Threat Flags

None — no new security-relevant surface introduced (tests-only; config/compose files read,
never modified).

## Constraints Honored

- Zero `src/` change (`git status --porcelain src/` empty).
- Zero `config/` change (the 4 profiles + `cloud.yaml` stay frozen; `git status --porcelain config/` empty).
- `.planning/STATE.md` / `ROADMAP.md` untouched (orchestrator-owned).
- Canonical interpreter `.venv/bin/python`; both tests in the default `make test -m "not live"` lane.

## Self-Check: PASSED

- `tests/test_local_profiles.py` — FOUND (modified, committed a379e55)
- `tests/test_offline_compose_env.py` — FOUND (created, committed 54f925c)
- Commit a379e55 — present in git log
- Commit 54f925c — present in git log
