---
phase: 11-offline-no-egress-posture
audit_date: 2026-06-11
asvs_level: 1
threats_total: 13
threats_closed: 13
threats_open: 0
status: SECURED
---

# Phase 11 Security Audit — Offline / No-Egress Posture

**Phase Goal:** Make "runs offline with no cloud-hosted LLM egress" an ASSERTED property
via config/.env/docs/tests only — ZERO `src/` change.

**ASVS Level:** 1
**Audit Date:** 2026-06-11
**Result:** SECURED — 13/13 threats closed, 0 open

---

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-11-01 | Information Disclosure | mitigate | CLOSED | `test_profile_file_has_no_cloud_llm_marker` parametrized over all 4 profiles (`_PROFILES` = vllm, ollama, vllm-compose, cpu-compose); `_FILE_DENY` = ("CF_AIG_WRAPPER_URL","vertex_ai","googleapis.com","anthropic","anthropic.com","sk-"); all 4 pass: `tests/test_local_profiles.py:102-108`. Live run: 4/4 passed. |
| T-11-02 | Information Disclosure | mitigate | CLOSED | `test_no_valued_cloud_llm_key_in_env` + `test_no_cloud_host_in_env_values` over api and worker services; `_CLOUD_KEY_NAMES` = ("ANTHROPIC_API_KEY","VERTEX_PROJECT_ID","VERTEX_LOCATION","CF_AIG_WRAPPER_URL","MODEL_GATEWAY_SHARED_SECRET"); valued-key semantics; non-empty-block sanity guard. `tests/test_offline_compose_env.py:82-111`. Live run: 6/6 passed. |
| T-11-03 | Assurance gap (vacuous sweep) | mitigate | CLOSED | `test_cloud_reference_profile_does_trip_the_sweep` reads `config/model_gateway.cloud.yaml` and asserts `any(m in text for m in _FILE_DENY)` is True; cloud.yaml trips 3 markers: `['CF_AIG_WRAPPER_URL', 'vertex_ai', 'anthropic']`. `tests/test_local_profiles.py:111-120`. Live run: passed. |
| T-11-04 | False positive (allowlist too narrow) | accept-with-control | CLOSED | `_SERVICE_DNS = ("http://vllm:8000","http://ollama:11434")`; `_LOCAL_ALLOW = _LOOPBACK + _SERVICE_DNS`; `test_every_route_api_base_is_loopback_or_service_dns` uses `startswith(_LOCAL_ALLOW)`. Cloud-host lists are cloud-LLM-scoped, never blanket. `tests/test_local_profiles.py:82-98`. |
| T-11-05 | Information Disclosure / Exfiltration | mitigate | CLOSED | `_cloud_llm_deny_guard` patches `socket.getaddrinfo` (not `create_connection` — catches both sync httpcore and async anyio backends). Async positive control: `test_guard_denies_anthropic_async_positive_control` uses `litellm.acompletion` via `asyncio.run`. `tests/test_offline_deny_guard.py:71-172`. Live run: passed. |
| T-11-06 | Assurance gap (vacuous guard) | mitigate | CLOSED | `test_default_lane_local_profile_does_not_trip_guard` calls `build_router("config/model_gateway.vllm.yaml")` and drives a completion; connection-refused-to-localhost = PASS; "OFFLINE deny" in error = FAIL. Guard exercised beyond construction (Pitfall 5). `tests/test_offline_deny_guard.py:186-202`. Live run: passed. |
| T-11-07 | Assurance gap (wrong-reason pass) | mitigate | CLOSED | Both positive controls assert `"OFFLINE deny" in str(ei.value)` only — no `or "anthropic.com"` fallback. "OFFLINE deny" can only originate from `_cloud_llm_deny_guard`. Hardened in commit 1ffb70c. `tests/test_offline_deny_guard.py:136-172`. Live run: sync and async both assert unique message. |
| T-11-08 | False positive (allowlist too broad) | accept-with-control | CLOSED | `_is_cloud_llm_host` matches precise `aiplatform.googleapis.com` and `*-aiplatform.googleapis.com`, never bare `googleapis.com`. `test_is_cloud_llm_host_matches_vertex_precisely` asserts `sheets.googleapis.com` → False, `googleapis.com` → False. Guard no-ops when `ANTHROPIC_API_KEY`/`VERTEX_PROJECT_ID`/`CF_AIG_WRAPPER_URL` is set. `tests/test_offline_deny_guard.py:110-126`. |
| T-11-09 | Information Disclosure | mitigate | CLOSED | `VERTEX_LOCATION=` blanked in `.env.offline.example:81` (source has `australia-southeast1`). `test_cloud_llm_keys_present_but_blank` asserts all 6 `_CLOUD_KEY_NAMES` present-and-blank. `tests/test_offline_posture_env.py:75-91`. Live run: passed. |
| T-11-10 | Assurance gap (false positive) | mitigate | CLOSED | `_env_pairs()` uses valued-key semantics: parses `KEY=VALUE`, asserts `not pairs[key]` (empty string). Skips comment lines (starting with `#`) so the file's own blank key names do not substring-trip. `tests/test_offline_posture_env.py:51-91`. Live run: passed. |
| T-11-11 | Tampering / Assurance gap | mitigate | CLOSED | `test_no_src_change_since_phase_base`: (1) loud-skips when `ZERO_SRC_BASE` unset — default run confirmed 1 skipped; (2) armed run `ZERO_SRC_BASE=5092323`: `1 passed, 0 skipped` (non-vacuous). Range non-vacuity confirmed: `git rev-list --count 5092323..HEAD` = 17 commits; `git log --oneline 5092323..HEAD -- src/` = empty (0 src-touching commits). `tests/test_zero_src_invariant.py:40-59`. |
| T-11-12 | Assurance gap (time-bomb / vacuity) | accept-with-control | CLOSED | `ZERO_SRC_BASE` not baked into test file — env-gated loud-skip is the only non-time-bomb, non-vacuous formulation. `test_no_src_change_since_phase_base` reads `os.getenv("ZERO_SRC_BASE")` and calls `pytest.skip(...)` when unset; no hardcoded SHA; no `main...HEAD`. `tests/test_zero_src_invariant.py:47-51`. |
| T-11-SC | Tampering | mitigate | CLOSED | No npm/pip/cargo installs in this phase. All deps (litellm, pytest, yaml, httpx) were already present. Confirmed by all three SUMMARY files: "tech-stack added: []". No new dependencies introduced. |

---

## Unregistered Flags

None. All three SUMMARY files explicitly report no new attack surface:
- 11-01-SUMMARY.md: "## Threat Flags: None — no new security-relevant surface introduced (tests-only; config/compose files read, never modified)"
- 11-02-SUMMARY.md: "## Threat Register Outcome" (no new flags reported)
- 11-03-SUMMARY.md: "No new threat surface. All four STRIDE-register `mitigate` dispositions addressed"

---

## Accepted Risks Log

| Threat ID | Category | Control | Rationale |
|-----------|----------|---------|-----------|
| T-11-04 | False positive — service-DNS flagged | `_SERVICE_DNS` + `_LOCAL_ALLOW` allowlist; cloud-LLM-scoped host/key lists only | Accepted: in-stack service DNS (vllm:8000, ollama:11434) is egress-free compose-sibling traffic, not cloud-LLM egress. Never a blanket no-network block. |
| T-11-08 | False positive — non-Vertex Google API denied; live lane blocked | Precise `aiplatform.googleapis.com` match; creds-gated no-op | Accepted: guard does not fire on `sheets.googleapis.com` or bare `googleapis.com`; no-ops in `make test-live` when any real cred is set. |
| T-11-12 | Assurance gap — time-bomb or vacuity in zero-src test | Env-gated loud-skip; SHA operator/CI-supplied | Accepted: env-gated formulation mirrors `pg_dsn` repo convention; avoids hardcoded-SHA time-bomb and vacuous `main...HEAD`; enforcing run confirmed non-vacuous at phase gate. |

---

## Audit Note: model_gateway.config.yaml

`config/model_gateway.config.yaml` is the ACTIVE MUTABLE runtime config (`DEFAULT_CONFIG_PATH` in `src/agent_mesh/worker/model_gateway.py:35`). In its committed/default state it contains cloud markers (identical content to `cloud.yaml`) — this is correct and expected. `make use-vllm`/`make use-ollama` overwrites it with the local profile at deployment time; `docker-compose.yml` mounts the compose profiles over it at `:55,86`. It is intentionally excluded from the T-11-01 sweep (which covers the 4 immutable source profiles). The negative control (`cloud.yaml`) exercises the same marker set. No gap.

---

## Test Execution Evidence

All tests run under `PYTHONPATH=src .venv/bin/python -m pytest -m "not live"` on 2026-06-11:

| Test File | Result |
|-----------|--------|
| tests/test_local_profiles.py | 21 passed |
| tests/test_offline_compose_env.py | 6 passed |
| tests/test_offline_deny_guard.py | 5 passed |
| tests/test_offline_posture_env.py | 4 passed |
| tests/test_zero_src_invariant.py | 1 skipped (loud-skip, correct) |
| **Armed run** (`ZERO_SRC_BASE=5092323`) | **1 passed, 0 skipped** (non-vacuous) |
| `git rev-list --count 5092323..HEAD` | 17 (range non-empty) |
| `git log --oneline 5092323..HEAD -- src/` | empty (zero src-touching commits) |
