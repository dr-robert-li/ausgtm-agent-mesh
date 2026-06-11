---
phase: 11-offline-no-egress-posture
verified: 2026-06-11T01:44:20Z
status: passed
score: 11/11
overrides_applied: 0
re_verification: false
---

# Phase 11: Offline / No-Egress Posture — Verification Report

**Phase Goal:** Make "runs offline with no cloud-hosted LLM egress" an ASSERTED property,
not a hope — a config/.env OFFLINE posture plus tests that FAIL if any local model profile,
the assembled compose stack, or the default creds-free lane can reach a cloud LLM provider
or model gateway. Config/.env/docs/tests only — ZERO `src/` change (durably enforced).
**Verified:** 2026-06-11T01:44:20Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Preliminary: Commit Range Integrity

Before trusting the armed zero-src run, the verifier confirmed the phase-base SHA
`5092323` is genuinely behind HEAD (not the same commit).

`git log 5092323..HEAD` returns 15 commits (planning docs + all 6 phase-11 test/config commits):
`a379e55`, `54f925c`, `543e9a7`, `182613f`, `1ffb70c`, `08a1ed0`, `601092b`, etc.

The base SHA `5092323` corresponds to "docs(state): record phase 11 context session" — the
pre-Phase-11 planning HEAD, genuinely below the test commits. The armed run is non-vacuous.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | OFFLINE posture expressible via config/.env (OFFLINE-01) | VERIFIED | `.env.offline.example` ships all 6 cloud-LLM creds blank; `MODEL_GATEWAY_BASE_URL=http://localhost:4000`; RUNBOOK "## Offline / no-egress posture" section at line 340 with scope caveat verbatim |
| 2 | All 4 local model profiles pass whole-file cloud-LLM-marker sweep (OFFLINE-02) | VERIFIED | `test_profile_file_has_no_cloud_llm_marker` passes for vllm, ollama, vllm-compose, cpu-compose; zero hits on `_FILE_DENY` = ("CF_AIG_WRAPPER_URL","vertex_ai","googleapis.com","anthropic","anthropic.com","sk-") |
| 3 | Every route api_base in all 4 local profiles is loopback or in-stack service-DNS | VERIFIED | `test_every_route_api_base_is_loopback_or_service_dns` passes for all 4 profiles; `_LOCAL_ALLOW = _LOOPBACK + _SERVICE_DNS` allowlists compose service-DNS correctly |
| 4 | `config/model_gateway.cloud.yaml` TRIPS the sweep (negative control / non-vacuity) | VERIFIED | `test_cloud_reference_profile_does_trip_the_sweep` passes; manually confirmed cloud.yaml trips markers: `['CF_AIG_WRAPPER_URL', 'vertex_ai', 'anthropic']` |
| 5 | docker-compose.yml api/worker env blocks carry no valued cloud-LLM key and no cloud host in any env value (OFFLINE-02/D-04) | VERIFIED | `test_no_valued_cloud_llm_key_in_env` and `test_no_cloud_host_in_env_values` pass for both api and worker; non-empty block sanity guard also passes |
| 6 | Deny-guard patches `socket.getaddrinfo` (not create_connection-only), raises on cloud-LLM hosts, passes local hosts (OFFLINE-03) | VERIFIED | Guard at line 101 patches `socket.getaddrinfo`; `_is_cloud_llm_host` unit tests confirm: aiplatform.googleapis.com=True, sheets.googleapis.com=False, anthropic.com=True, localhost=False, vllm=False |
| 7 | Sync positive control (`anthropic/` via `litellm.completion`) asserts on guard's unique message "OFFLINE deny" | VERIFIED | `test_guard_denies_anthropic_sync_positive_control` PASSED; asserts `"OFFLINE deny" in str(ei.value)` only — no wrong-reason `or "anthropic.com"` |
| 8 | Async positive control (`anthropic/` via `litellm.acompletion`) also trips the guard | VERIFIED | `test_guard_denies_anthropic_async_positive_control` PASSED; async path the real LangGraph worker uses |
| 9 | Representative default-lane path (local loopback profile) does NOT trip the deny-guard (non-vacuous proof) | VERIFIED | `test_default_lane_local_profile_does_not_trip_guard` PASSED; connection-refused to localhost:8000 is treated as PASS; "OFFLINE deny" not in error |
| 10 | `.env.offline.example` valued-key sweep: all 6 cloud-LLM keys present-but-blank (OFFLINE-01) | VERIFIED | `test_cloud_llm_keys_present_but_blank` PASSED; all 6 `_CLOUD_KEY_NAMES` present with empty values incl. `VERTEX_LOCATION=` (which `.env.example` carries `australia-southeast1`) |
| 11 | Durable zero-src invariant: armed run passes without skipping; default run loud-skips | VERIFIED | `ZERO_SRC_BASE=5092323 .venv/bin/python -m pytest tests/test_zero_src_invariant.py` → `1 passed, 0 skipped`; unset → `1 skipped`; `git diff 5092323..HEAD -- src/` is byte-empty |

**Score:** 11/11 truths verified

---

## Test Execution Results

### Five Phase-11 files (named run)

Command: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_local_profiles.py tests/test_offline_compose_env.py tests/test_offline_deny_guard.py tests/test_offline_posture_env.py tests/test_zero_src_invariant.py -m "not live" -v`

Result: **36 passed, 1 skipped in 1.84s**

The 1 skip is `test_zero_src_invariant.py::test_no_src_change_since_phase_base` — correct
loud-skip with message "ZERO_SRC_BASE unset; durable zero-src assertion needs the phase-base SHA".

### Durable zero-src test (armed / enforcing run)

Command: `ZERO_SRC_BASE=5092323 PYTHONPATH=src .venv/bin/python -m pytest tests/test_zero_src_invariant.py -m "not live" -v`

Result: **1 passed in 0.02s** — NON-VACUOUS: did not skip.

Cross-check: `git diff 5092323..HEAD -- src/` → byte-empty.

### Full default lane (regression check)

Command: `PYTHONPATH=src .venv/bin/python -m pytest -q -m "not live"`

Result: **346 passed, 11 skipped, 23 deselected, 10 warnings in 24.04s** — zero failures. No regressions introduced by Phase 11.

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/test_local_profiles.py` | Extended: 4-profile sweep + service-DNS allowlist + whole-file deny + negative control (D-01) | VERIFIED | `_PROFILES` has 4 keys; `_FILE_DENY` defined; `test_profile_file_has_no_cloud_llm_marker` parametrized; `test_cloud_reference_profile_does_trip_the_sweep` present |
| `tests/test_offline_compose_env.py` | New: docker-compose api/worker valued-cloud-key + cloud-host env sweep (D-04) | VERIFIED | Contains `_CLOUD_KEY_NAMES`; `_env_items` normalizes dict and list env forms; non-empty block sanity guard |
| `tests/test_offline_deny_guard.py` | New: `socket.getaddrinfo` autouse deny-guard + sync/async positive controls + representative path (D-02) | VERIFIED | Contains `getaddrinfo`; `@pytest.fixture(autouse=True)` function-scoped; `_is_cloud_llm_host` with precise Vertex match; creds-gated no-op |
| `tests/test_offline_posture_env.py` | New: valued-key sweep over `.env.offline.example` (OFFLINE-01) | VERIFIED | Contains `_CLOUD_KEY_NAMES`; 6-name list; valued-key semantics (not substring sweep) |
| `tests/test_zero_src_invariant.py` | New: durable env-gated loud-skip git-diff zero-src assertion | VERIFIED | Contains `ZERO_SRC_BASE`; `git diff $ZERO_SRC_BASE..HEAD -- src/` assertion; no hardcoded SHA |
| `.env.offline.example` | Concrete offline posture artifact (D-03): cloud-LLM creds blank, local api_base, SaaS creds normal | VERIFIED | `ANTHROPIC_API_KEY=`, `VERTEX_PROJECT_ID=`, `VERTEX_LOCATION=`, `CF_AIG_WRAPPER_URL=`, `MODEL_GATEWAY_MASTER_KEY=`, `MODEL_GATEWAY_SHARED_SECRET=` all present-and-blank; `MODEL_GATEWAY_BASE_URL=http://localhost:4000` |
| `RUNBOOK.md` | "## Offline / no-egress posture" section with scope caveat | VERIFIED | Section at line 340; scope caveat "offline = no cloud-hosted LLM, not blanket no-network" at line 356; how-to-express, how-to-verify, and durable zero-src instructions documented |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `tests/test_local_profiles.py` | `config/model_gateway.{vllm,ollama,vllm.compose,cpu.compose}.yaml` | `read_text()` whole-file sweep using `_FILE_DENY` | WIRED | All 4 profiles read and swept; zero hits confirmed in execution |
| `tests/test_local_profiles.py` | `config/model_gateway.cloud.yaml` | negative-control assertion (must trip) | WIRED | `test_cloud_reference_profile_does_trip_the_sweep` verifies `cloud.yaml` trips 3 markers |
| `tests/test_offline_compose_env.py` | `docker-compose.yml` | `yaml.safe_load()` + api/worker env normalization | WIRED | Static load (no docker daemon); both api and worker env blocks swept; sanity check confirms non-empty blocks |
| `tests/test_offline_deny_guard.py` | `socket.getaddrinfo` | `monkeypatch.setattr(socket, "getaddrinfo", guard)` | WIRED | Guard fires on sync and async paths; confirmed by positive control execution results |
| `tests/test_offline_deny_guard.py` | `agent_mesh.worker.model_gateway.build_router` | representative default-lane path under fixture | WIRED | `build_router("config/model_gateway.vllm.yaml")` called; completion driven through "low-complexity" route; connection-refused to localhost treated as PASS |
| `tests/test_offline_posture_env.py` | `.env.offline.example` | valued-key sweep (key-present-but-blank OK) | WIRED | Parser skips comment lines; splits on first `=`; all 6 `_CLOUD_KEY_NAMES` verified present-and-blank |
| `tests/test_zero_src_invariant.py` | `git diff $ZERO_SRC_BASE..HEAD -- src/` | `subprocess.run` + env-gated loud-skip | WIRED | Armed run returns `1 passed, 0 skipped`; `git diff 5092323..HEAD -- src/` byte-empty |

---

## Behavioral Spot-Checks (Execution Results)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Sync positive control trips deny-guard | `litellm.completion(anthropic/..., api_key="sk-ant-fake")` under guard | `"OFFLINE deny"` in error | PASS |
| Async positive control trips deny-guard | `litellm.acompletion(anthropic/..., api_key="sk-ant-fake")` via `asyncio.run` | `"OFFLINE deny"` in error | PASS |
| Local profile completion does NOT trip guard | `build_router(vllm.yaml).completion("low-complexity")` under guard | connection-refused to localhost (no "OFFLINE deny") | PASS |
| cloud.yaml negative control is non-vacuous | read cloud.yaml; check `_FILE_DENY` hits | `['CF_AIG_WRAPPER_URL', 'vertex_ai', 'anthropic']` | PASS |
| sheets.googleapis.com passes through guard | `_is_cloud_llm_host("sheets.googleapis.com")` | False | PASS |
| aiplatform.googleapis.com is denied | `_is_cloud_llm_host("aiplatform.googleapis.com")` | True | PASS |
| VERTEX_LOCATION blanked in posture file | `.env.offline.example` | `VERTEX_LOCATION=` (empty value) | PASS |
| Zero-src invariant non-vacuous (armed) | `ZERO_SRC_BASE=5092323 pytest test_zero_src_invariant.py` | 1 passed, 0 skipped | PASS |
| Zero-src loud-skip (default) | `pytest test_zero_src_invariant.py` (no env var) | 1 skipped: "ZERO_SRC_BASE unset…" | PASS |
| Full default lane regression | `pytest -q -m "not live"` | 346 passed, 11 skipped, 0 failures | PASS |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| OFFLINE-01 | 11-03-PLAN.md | OFFLINE posture expressible via config/.env; documented in RUNBOOK | SATISFIED | `.env.offline.example` + `RUNBOOK.md §Offline/no-egress posture` + `tests/test_offline_posture_env.py` all present and passing |
| OFFLINE-02 | 11-01-PLAN.md | Test asserts local/offline model profiles contain NO cloud api_base and no cloud-key env refs | SATISFIED | `test_profile_file_has_no_cloud_llm_marker` (4 profiles, whole-file) + `test_every_route_api_base_is_loopback_or_service_dns` + `test_offline_compose_env.py` (assembled stack D-04) all pass |
| OFFLINE-03 | 11-02-PLAN.md | Test asserts default creds-free lane performs no outbound to real provider/gateway | SATISFIED | `tests/test_offline_deny_guard.py` socket.getaddrinfo guard + sync/async positive controls + representative path; all 5 tests pass |

---

## Anti-Patterns Found

Scanned phase-11 modified files: `tests/test_local_profiles.py`, `tests/test_offline_compose_env.py`, `tests/test_offline_deny_guard.py`, `tests/test_offline_posture_env.py`, `tests/test_zero_src_invariant.py`, `.env.offline.example`, `RUNBOOK.md`.

| File | Pattern | Severity | Finding |
|------|---------|----------|---------|
| All files | TBD / FIXME / XXX | — | None found |
| All files | TODO / HACK / PLACEHOLDER | — | None found |
| All files | Empty implementations | — | None found |

No anti-patterns. All phase-11 files are complete, substantive implementations.

---

## Zero `src/` Change Invariant

This is the BLOCKING milestone guardrail for this phase and must be explicitly verified.

- `git diff 5092323..HEAD -- src/` → **byte-empty** (confirmed via direct shell invocation)
- Armed test: `ZERO_SRC_BASE=5092323 .venv/bin/python -m pytest tests/test_zero_src_invariant.py` → **1 passed, 0 skipped** (non-vacuous)
- The commit range `5092323..HEAD` contains 15 commits, all in `.planning/`, `tests/`, `.env.offline.example`, and `RUNBOOK.md` — zero under `src/`

INVARIANT HOLDS.

---

## Human Verification Required

None. All phase-11 truths are programmatically verifiable via static config/env file analysis and pytest execution. The deny-guard is tested with live litellm calls (fake key, connection-refused to localhost). No visual, real-time, or external-service behavior requires human confirmation.

---

## Gaps Summary

No gaps. All 11 must-have truths verified, all 7 required artifacts substantive and wired, all key links confirmed, all 3 requirement IDs satisfied, no anti-patterns, no regressions, zero `src/` change confirmed non-vacuously.

---

_Verified: 2026-06-11T01:44:20Z_
_Verifier: Claude (gsd-verifier)_
