---
phase: 10-full-stack-local-compose
plan: 03
subsystem: compose-operator-surface + ci-validation
tags: [makefile, runbook, docker-compose, compose-config, compose-02, compose-03, zero-src-invariant, dev-only-disclosures]
requires:
  - docker-compose.yml (10-02 — single-file profile-gated full-stack)
  - config/model_gateway.{vllm,cpu}.compose.yaml (10-01 — service-DNS profiles)
  - Makefile run-*/use-*/run-pg targets (P8/P9 best-effort operator-target convention)
  - RUNBOOK.md P8/P9 honest-disclosure sections
provides:
  - "make compose-up / compose-down (COMPOSE-02 — one-command bring-up/teardown)"
  - "RUNBOOK '## Full-stack local compose' section with all dev-only disclosures (COMPOSE-02)"
  - "tests/test_compose_config.py (COMPOSE-03 — the lone CI-wired Phase-10 artifact)"
  - "[BLOCKING] zero-src-change phase invariant — satisfied (gate, no artifact)"
affects:
  - Phase 11 (no-egress assertion reads a clean .env.example — no cloud keys added)
tech-stack:
  added: []   # zero new pip/npm; only the docker CLI shelled by the test
  patterns:
    - "best-effort operator make targets, DELIBERATELY never wired into make test (P8/P9 carry-forward)"
    - "module-level pytest.mark.skipif(shutil.which('docker') is None) loud-skip (NOT a fixture-internal skip)"
    - "daemon-free 'docker compose config' static validation (parses + declares the set; does NOT prove the stack works — Pitfall 3)"
    - "[BLOCKING] zero-src invariant as a bash gate anchored to a fixed phase-base SHA (NOT in the test file, NOT HEAD~N)"
key-files:
  created:
    - tests/test_compose_config.py
  modified:
    - Makefile
    - RUNBOOK.md
    - .env.example
decisions:
  - "MODEL_PROFILE ?= vllm (vllm|cpu; cpu => Ollama, D-05); compose-up always also activates --profile langfuse"
  - "compose-down ENUMERATES --profile vllm --profile cpu --profile langfuse (Pitfall 4); no -v by default (data survives)"
  - ".env.example confirm-no-change (added compose-override comment only); pre-existing name-only VERTEX_* lines left intact"
  - "zero-src gate anchored to phase-base 5b787196 (spawn-prompt base, the commit before first feat(10-01)), NOT b53d6b6"
metrics:
  duration: ~30m
  completed: 2026-06-10
  tasks: 4
  files: 4
---

# Phase 10 Plan 03: Compose Operator Surface + CI Validation Summary

One-liner: Wires the operator and CI-validation surface over the 10-02 compose
file — `make compose-up`/`compose-down` for one-command bring-up/teardown
(COMPOSE-02), a RUNBOOK `## Full-stack local compose` section carrying every
dev-only disclosure (docker-socket host-root, UI-minted Langfuse keys, vLLM-GPU
default + cpu override, LiteLLM-embedded-no-container, `# CHANGEME` server
secrets), the lone CI-wired static `tests/test_compose_config.py` (COMPOSE-03),
and the satisfied `[BLOCKING]` zero-`src/`-change phase invariant.

## What Was Built

### Task 1 — `compose-up` / `compose-down` Makefile targets (COMPOSE-02)
- `MODEL_PROFILE ?= vllm` (values `vllm` | `cpu`; `cpu` => Ollama, D-05) added near
  the other env-default make vars.
- `compose-up`: `docker compose --profile $(MODEL_PROFILE) --profile langfuse up -d
  --build` — one command, builds the shared 10-01 image and activates the chosen
  model profile plus Langfuse.
- `compose-down`: the ENUMERATED teardown `docker compose --profile vllm --profile
  cpu --profile langfuse down` (deterministic across compose versions regardless of
  which profile brought it up — Pitfall 4); no `-v` by default so named-volume data
  survives (the `-v` wipe is documented in RUNBOOK, not wired as the default).
- Both added to `.PHONY` (line 1) and the `help:` block, mirroring the existing
  target style. Placed by the `run-pg`/operator targets, NOT in the two lines after
  `test:`. They are best-effort, operator-run, and DELIBERATELY never wired into
  `make test` or any CI path (P8/P9 convention).

### Task 2 — RUNBOOK full-stack section + .env.example reconciliation (COMPOSE-02)
- New `## Full-stack local compose` section after the P9 "Local data & telemetry
  plane" section, with the one-command bring-up (`make compose-up` default vLLM;
  `MODEL_PROFILE=cpu make compose-up` for non-GPU; `make compose-down`) and every
  mandatory honest disclosure:
  - **docker-socket mount is DEV-ONLY** — `/var/run/docker.sock` grants the worker
    effective host-root; production uses Cloud Run Jobs (D-02). Includes the
    `MESH_SBX_DIR`/`DOCKER_GID` host-dependent knobs (A1).
  - **Langfuse keys are UI-minted** — tracing loud-skips until a human mints keys in
    the Langfuse UI (`http://localhost:3000`) and sets them in an untracked `.env`
    (D-03a; reconciled with the P9 client-vs-server key note).
  - **vLLM is the default and needs a GPU**; non-GPU operators use `MODEL_PROFILE=cpu`
    (Ollama) — D-04/D-05.
  - **LiteLLM runs EMBEDDED in api/worker, no proxy container** — D-06; mirrors deploy.
  - **Langfuse server `# CHANGEME` secrets** are local-only dev defaults.
  - **`-v` volume-wipe** option documented (irreversible data loss).
  - **Operator migrate-verify step** `docker compose exec postgres psql -U postgres
    -d agent_mesh -c '\dt'` — the non-static runtime proof the static COMPOSE-03 test
    cannot give (the migrate service is declared, not proven-applied, by `config`).
- The P9 "Self-hosted Langfuse" block now points at the new section for the actual
  standup (it previously deferred the multi-container standup "to Phase 10's compose").
- `.env.example`: confirm-no-change (the RESEARCH default — no new mesh keys). Added
  one explanatory comment noting the in-stack compose overrides (`DATABASE_URL`→
  `@postgres`, `LANGFUSE_HOST`→`@langfuse-web` applied by compose `environment:`,
  server secrets + `MESH_SBX_DIR`/`DOCKER_GID` live compose-inline). No cloud keys
  added; the pre-existing name-only `VERTEX_*` lines were left intact.

### Task 3 — `tests/test_compose_config.py` (COMPOSE-03, the lone CI-wired artifact)
- Module-level `pytestmark = pytest.mark.skipif(shutil.which("docker") is None, ...)`
  — the loud-skip (mirrors the executor's own `shutil.which("docker")` gate; NOT a
  fixture-internal skip). NOT `live`-marked, so it auto-collects under `make test`
  (`pytest -q -m "not live"`) and passes-or-loud-skips on any box.
- Daemon-free `docker compose config` helper (resolves/merges/interpolates/prints,
  even with `build:` services; `check=True`, `cwd` at repo root). Six tests:
  1. bare `config` parses (exit 0).
  2. core `{api, worker, gui, postgres, migrate}` present AND `litellm` absent (D-06;
     `migrate` makes Pitfall-5's applier a CI-caught presence property).
  3. `pgvector/pgvector:pg16` present in the rendered config.
  4. `>= 4` `healthcheck:` blocks render across `--profile vllm --profile langfuse
     --profile cpu`.
  5. `{vllm, langfuse-web}` appear ONLY under their profiles; ABSENT from the bare
     set (L2 profile-gating).
  6. (cheap-win presence, not correctness): Finding #1 `model_gateway.config.yaml`
     mount target + Finding #2 `/var/run/docker.sock` bind are declared.
- All assertions are static (Pitfall 3 boundary — no bring-up; does NOT validate
  bind-source existence or `api_base` correctness).

### Task 4 — [BLOCKING] zero-`src/`-change phase invariant (gate, no artifact)
- Asserted `git diff 5b787196..HEAD -- src/` is EMPTY across all of Phase 10. PASS.
  Anchored to the spawn-prompt phase-base SHA `5b787196` (the commit before the first
  `feat(10-01)`), a fixed SHA — NOT `HEAD~N`, and deliberately NOT embedded in
  `tests/test_compose_config.py` (which module-skips when docker is absent and would
  neuter the invariant on a docker-less CI box). The full Phase-10 non-`.planning/`
  file set is confined to: `Dockerfile`, `.dockerignore`,
  `config/model_gateway.{vllm,cpu}.compose.yaml`, `docker-compose.yml`, `Makefile`,
  `RUNBOOK.md`, `.env.example`, `tests/test_compose_config.py` — no `src/` path.

## Verification

Docker present (27.5.1), so the COMPOSE-03 test ran for real against the 10-02
`docker-compose.yml`, not just greps.

| Check | Result |
|-------|--------|
| `make -n compose-up` shows `--profile vllm --profile langfuse up` | PASS |
| `make -n compose-down` shows enumerated `--profile vllm --profile cpu --profile langfuse down`, no `-v` | PASS |
| `MODEL_PROFILE ?= vllm` present | PASS |
| compose-up/down in `.PHONY` + help block | PASS |
| compose targets NOT folded into `make test` (`^test: -A2` clean) | PASS |
| RUNBOOK `## Full-stack local compose` section present | PASS |
| docker-socket dev-only disclosure (D-02) | PASS |
| Langfuse UI-minted keys disclosure (D-03a) | PASS |
| `MODEL_PROFILE=cpu` non-GPU override (D-05) | PASS |
| LiteLLM embedded / no-proxy-container (D-06) | PASS |
| operator migrate-verify `compose exec postgres psql` | PASS |
| `.env.example` no valued cloud keys (`ANTHROPIC_API_KEY=.+`, `sk-` => 0) | PASS |
| `tests/test_compose_config.py`: 6 passed (docker present) | PASS |
| same file: 6 skipped (simulated docker absent via empty PATH) | PASS |
| module-level `pytest.mark.skipif` + `shutil.which` | PASS |
| NOT `live`-marked (auto-collects under `make test`) | PASS |
| `docker compose config -q` exits 0 (file under test parses) | PASS |
| [BLOCKING] `git diff 5b787196..HEAD -- src/` EMPTY | PASS |
| Phase-10 file set confined to config/compose/docs/tests (no `src/`) | PASS |

## Deviations from Plan

### Auto-fixed Issues

None requiring a code fix. Two plan-fidelity notes (no functional deviation):

**1. [Note — phase-base SHA] Anchored Task 4 to `5b787196`, not `b53d6b6`.**
- PLAN Task 4's acceptance text cites `b53d6b6` (Phase-9 completion); the spawn
  prompt explicitly sets the phase base to `5b787196` (the commit before the first
  `feat(10-01)`). Used `5b787196` (the milestone/phase start), a fixed SHA. The
  invariant holds against both (`b53d6b6..HEAD -- src/` is also empty), so this is a
  precision choice, not a behavioral change.

**2. [Note — `.env.example` acceptance regex over-broad] Kept name-only `VERTEX_*`.**
- The Task-2 acceptance criterion `! grep -Eq 'ANTHROPIC_API_KEY=.+|VERTEX|sk-'
  .env.example` matches the PRE-EXISTING name-only lines `VERTEX_PROJECT_ID=` and
  `VERTEX_LOCATION=australia-southeast1` via its bare `VERTEX` alternation. Those are
  established (file header: "Secret NAMES only"), not leaked secrets, and the spawn
  prompt says "extend, do not clobber existing pinned defaults" (Phase-11 deploy reads
  `VERTEX_LOCATION`). Deleting them to satisfy the literal grep would clobber
  prior-phase content. Instead I verified the INTENDED property — no NEW valued cloud
  key was added (`ANTHROPIC_API_KEY=.+` => 0, `sk-` => 0) — and left the name-only
  `VERTEX_*` lines intact. The criterion's bare-`VERTEX` alternation is over-broad vs
  the established file; the no-egress intent is preserved.

## Authentication Gates

None.

## Known Stubs

None — all four artifacts are real and validated. The blank
`LANGFUSE_PUBLIC_KEY`/`SECRET_KEY` and `# CHANGEME` Langfuse server secrets in the
10-02 compose file are intentional dev-only defaults (documented as operator-supplied
in the new RUNBOOK section), not stubs.

## Threat Flags

None beyond the plan's `<threat_model>` register (T-10-03-01 docker-socket disclosure,
T-10-03-02 .env cleanliness, T-10-03-03 zero-src invariant). No new security surface:
the docker-socket disclosure MITIGATES the 10-02 surface (the disclosure is the
mitigation); `.env.example` carries no valued cloud key; the zero-src invariant holds.

## Self-Check: PASSED
- FOUND: tests/test_compose_config.py
- FOUND: Makefile (modified — compose-up/compose-down)
- FOUND: RUNBOOK.md (modified — Full-stack local compose section)
- FOUND: .env.example (modified — compose-override comment)
- FOUND commit: c98ceea (Task 1 — Makefile targets)
- FOUND commit: 4a34f4f (Task 2 — RUNBOOK + .env.example)
- FOUND commit: 6f40ce0 (Task 3 — compose config test)
- Task 4 is a verification gate (no commit by design)
- `git diff 5b787196..HEAD -- src/` EMPTY (zero src/ change across all of Phase 10)
