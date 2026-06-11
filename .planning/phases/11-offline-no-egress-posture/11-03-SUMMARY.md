---
phase: 11-offline-no-egress-posture
plan: 03
subsystem: offline-posture / zero-src-guardrail
tags: [OFFLINE-01, offline-posture, zero-src-invariant, config, tests, docs]
requires: [11-01, 11-02]
provides:
  - ".env.offline.example concrete OFFLINE posture artifact (D-03)"
  - "RUNBOOK Offline / no-egress posture section"
  - "valued-cloud-key sweep over .env.offline.example (OFFLINE-01)"
  - "durable env-gated zero-src invariant test (supersedes P10 one-shot bash gate)"
affects: []
tech-stack:
  added: []
  patterns:
    - "valued-key sweep (key-present-but-blank = OK) over .env posture file"
    - "env-gated loud-skip git-diff zero-src assertion (mirrors pg_dsn convention)"
key-files:
  created:
    - .env.offline.example
    - tests/test_offline_posture_env.py
    - tests/test_zero_src_invariant.py
  modified:
    - RUNBOOK.md
decisions:
  - "VERTEX_LOCATION blanked in .env.offline.example (carries australia-southeast1 in .env.example — a value the valued-key sweep would flag)"
  - "posture sweep uses 6-name _CLOUD_KEY_NAMES per plan (incl. MODEL_GATEWAY_MASTER_KEY), not the compose-env test's 5"
  - "zero-src test is env-gated loud-skip — no hardcoded SHA (time-bomb), no main...HEAD (vacuous on main)"
  - "SaaS/tool-pack creds left NORMAL — offline zeroes only cloud-LLM/gateway creds; no over-assertion"
metrics:
  duration: ~9 min
  completed: 2026-06-11
  tasks: 3
  files: 4
---

# Phase 11 Plan 03: Offline / No-Egress Posture + Durable Zero-src Guardrail Summary

OFFLINE-01 made an asserted+documented property via a copy-pasteable
`.env.offline.example` (cloud-LLM/gateway creds blank incl. `VERTEX_LOCATION`,
SaaS creds normal, local `api_base` via the `use-vllm`/`use-ollama` file-swap) and
a RUNBOOK "Offline / no-egress posture" section; plus a valued-key sweep that keeps
the artifact honest and a DURABLE env-gated zero-`src/` invariant test that replaces
P10's one-shot bash gate without a hardcoded-SHA time-bomb or a vacuous `main...HEAD`.

## What Was Built

- **`.env.offline.example` (D-03):** derived from `.env.example`. Cloud-LLM/gateway
  creds blanked — `CF_AIG_WRAPPER_URL=`, `ANTHROPIC_API_KEY=`, `VERTEX_PROJECT_ID=`,
  `VERTEX_LOCATION=` (the one real content transform — `.env.example` carries
  `australia-southeast1`), `MODEL_GATEWAY_MASTER_KEY=`, `MODEL_GATEWAY_SHARED_SECRET=`,
  `GOOGLE_APPLICATION_CREDENTIALS=`. `MODEL_GATEWAY_BASE_URL` kept local
  (`http://localhost:4000`). SaaS/tool-pack creds (`COMPOSIO_API_KEY`,
  `BITSCALE_API_KEY`) and the local data plane left NORMAL. Header documents that the
  local model `api_base` is NOT a new env var (zero-`src/` forbids a runtime read) —
  it comes from the `make use-vllm`/`use-ollama` file-swap.
- **RUNBOOK `## Offline / no-egress posture` section** (inserted before
  `## Credentials & live lane`): what the posture is/is-not (scope caveat verbatim —
  "offline = no cloud-hosted LLM, not blanket no-network"), how to express it
  (`cp .env.offline.example .env` + `make use-vllm`/`use-ollama`), how to verify
  (`make test` sweeps + deny-guard; `ZERO_SRC_BASE=<sha> make test` for the durable
  zero-src assertion).
- **`tests/test_offline_posture_env.py`:** valued-key sweep over `.env.offline.example`
  using the 6-name `_CLOUD_KEY_NAMES` (per plan, incl. `MODEL_GATEWAY_MASTER_KEY`).
  Key-present-but-blank = OK; key-present-and-valued = violation. Comment-safe parser
  (skips `#` lines, splits on first `=`). Also asserts `MODEL_GATEWAY_BASE_URL` local
  and does NOT over-assert SaaS creds. Runs (does not skip) under `make test`.
- **`tests/test_zero_src_invariant.py`:** env-gated loud-skip git-diff assertion.
  Reads `ZERO_SRC_BASE`; unset → `pytest.skip` (mirrors `conftest.py` `pg_dsn`); set →
  `git diff $ZERO_SRC_BASE..HEAD -- src/` must be empty. No baked SHA. Supersedes the
  P10 one-shot bash zero-src gate with durable CI-collectable enforcement.

## Tasks & Commits

| Task | Name | Commit |
| ---- | ---- | ------ |
| 1 | .env.offline.example (D-03) + RUNBOOK offline section + valued-key sweep | `08a1ed0` |
| 2 | Durable env-gated zero-src invariant test | `601092b` |
| 3 | [BLOCKING] ENFORCING zero-src run (verification only — no files) | — |

## [BLOCKING] Enforcing-Run Result (Task 3)

All three gates PASS — phase base = `5092323` (pre-P11 HEAD at planning):

1. `ZERO_SRC_BASE=5092323 .venv/bin/python -m pytest tests/test_zero_src_invariant.py -x`
   → **1 passed, 0 skipped** (non-vacuous: did NOT skip).
2. `git diff 5092323..HEAD -- src/` → **byte-empty** (src/ unchanged since the phase base).
3. `make test` (`.venv/bin/python -m pytest -q -m "not live"`) → **346 passed, 11 skipped,
   23 deselected** green. All four Phase-11 CI-wired tests collect
   (test_local_profiles, test_offline_compose_env, test_offline_deny_guard,
   test_offline_posture_env) + test_zero_src_invariant loud-skipped by default.

The durable zero-`src/` milestone guardrail is enforced non-vacuously at the phase gate.

## Deviations from Plan

None — plan executed exactly as written. (Per the spawn prompt, the Task-3
`checkpoint:human-verify` runs as a verification gate that HALTs only on failure;
the enforcing run passed, so execution completed without a human-wait.)

## Threat Surface

No new threat surface. All four STRIDE-register `mitigate` dispositions addressed:
T-11-09 (VERTEX_LOCATION blanked + valued-key sweep), T-11-10 (valued-key semantics,
not substring), T-11-11 (durable git-diff test + non-vacuous enforcing run),
T-11-12 (env-gated loud-skip — no time-bomb, no vacuity). T-11-SC: no installs.

## Self-Check: PASSED

- `.env.offline.example` — FOUND
- `tests/test_offline_posture_env.py` — FOUND
- `tests/test_zero_src_invariant.py` — FOUND
- `RUNBOOK.md` "Offline / no-egress posture" — FOUND
- Commit `08a1ed0` (Task 1) — FOUND
- Commit `601092b` (Task 2) — FOUND
