---
phase: 10-full-stack-local-compose
plan: 02
subsystem: compose-assembly
tags: [docker-compose, profiles, langfuse-v3, pgvector, finding-1, finding-2, pitfall-5, dood, migrate]
requires:
  - Dockerfile (10-01 shared D-01 app image + docker CLI client)
  - config/model_gateway.vllm.compose.yaml (10-01 — service-DNS api_base vllm:8000/v1)
  - config/model_gateway.cpu.compose.yaml (10-01 — service-DNS api_base ollama:11434)
  - migrations/0001-0004 (Phase-9 DDL, dollar-quote-free)
provides:
  - docker-compose.yml (single-file profile-gated full-stack: core + vllm/cpu + langfuse + migrate)
affects:
  - 10-03 (make compose-up/down wrap this file; RUNBOOK discloses dev-only socket/secrets; COMPOSE-03 test asserts this file's shape)
  - Phase 11 (no-egress assertion — compose-variant profiles stay loopback-service-only)
tech-stack:
  added: []   # zero new pip/npm; only container images (pgvector pg16, langfuse:3, postgres:17, clickhouse, redis:7, chainguard minio, vllm-openai v0.6.6, ollama 0.5.4)
  patterns:
    - "single-file profile-gated compose (core always-on; vllm/cpu/langfuse profile-gated — L2)"
    - "Finding #1: compose-variant model profile mount onto /app/config/model_gateway.config.yaml (service-DNS api_base)"
    - "Finding #2: worker DooD via docker.sock + identical-path host bind (source==target) + TMPDIR redirect"
    - "Pitfall 5: one-shot migrate service (psql -f 0001..0004) gating api/worker/gui via service_completed_successfully"
    - "Pitfall 1: Langfuse pg renamed langfuse-postgres with its own volume; mesh DSN points only at pgvector postgres"
key-files:
  created:
    - docker-compose.yml
  modified: []
decisions:
  - "vLLM tag pinned v0.6.6; Ollama tag pinned 0.5.4 (replace upstream :latest)"
  - "api + langfuse-web/clickhouse/redis/minio + postgres/langfuse-postgres carry healthchecks (9 total >= 4 COMPOSE-03 floor)"
  - "langfuse-worker env expanded to real keys (not a comment) so a future operator bring-up works"
  - "compose-variant mount target /app/config/model_gateway.config.yaml (10-01 WORKDIR /app contract)"
metrics:
  duration: ~25m
  completed: 2026-06-10
  tasks: 3
  files: 1
---

# Phase 10 Plan 02: Single-File Full-Stack docker-compose.yml Summary

One-liner: A single profile-gated `docker-compose.yml` assembles the whole mesh —
always-on core (`api`/`worker`/`gui`/`postgres`/`migrate`), `profiles:[vllm]`/`[cpu]`
model backends, and a `profiles:[langfuse]` Langfuse v3 6-container set — threading the
three load-bearing functional gaps a static `docker compose config` cannot catch
(Finding #1 model api_base mount, Finding #2 DooD sandbox path, Pitfall 5 in-stack
migrations), with zero `src/` change and no standalone litellm container (D-06).

## What Was Built

### Task 1 — Core services + model backends (Finding #1 + Finding #2)
- `api`/`worker`/`gui`: all `build: .` (the 10-01 shared image, D-01), differing only by
  `command:` (Makefile run-* strings, no `--reload`; api/gui bind `0.0.0.0`, api on 8080).
- Env overrides per the RESEARCH wiring table: `DATABASE_URL=postgresql://postgres:postgres@postgres:5432/agent_mesh`
  (Phase-9 DSN parity, host `localhost`→`postgres`), `LANGFUSE_HOST=http://langfuse-web:3000`,
  blank `LANGFUSE_PUBLIC_KEY`/`SECRET_KEY` (UI-minted, D-03a).
- `postgres`: `pgvector/pgvector:pg16`, `POSTGRES_USER/PASSWORD/DB=postgres/postgres/agent_mesh`,
  named volume `mesh_pgdata`, `pg_isready` healthcheck.
- **Finding #1 (api AND worker):** mount `./config/model_gateway.${MODEL_PROFILE:-vllm}.compose.yaml`
  onto `/app/config/model_gateway.config.yaml:ro` (the 10-01 WORKDIR `/app` contract). The
  bind is the sole supplier of `config.yaml` (`.dockerignore` excludes it from the image).
  Two mounts → `grep -c model_gateway.config.yaml:ro` = 2.
- **Finding #2 (worker only):** `/var/run/docker.sock:/var/run/docker.sock` (DooD, dev-only)
  + `${MESH_SBX_DIR:-/tmp/agent-mesh-sbx}:${MESH_SBX_DIR:-/tmp/agent-mesh-sbx}` (identical
  absolute path, source==target) + `TMPDIR=${MESH_SBX_DIR:-/tmp/agent-mesh-sbx}` + `group_add: ["${DOCKER_GID:-999}"]`.
  The real P2 executor runs unmodified.
- Model backends: `vllm` (`profiles:[vllm]`, `vllm/vllm-openai:v0.6.6`, `--model Qwen/Qwen2.5-7B-Instruct
  --enable-auto-tool-choice --tool-call-parser hermes`, `:8000`, `ipc: host`, nvidia GPU reservation,
  python-urllib `/health` probe, `start_period: 120s`); `ollama` (`profiles:[cpu]`, `ollama/ollama:0.5.4`,
  `:11434`, `ollama_data` volume, `ollama list` healthcheck). NO `litellm` service (D-06).

### Task 2 — One-shot `migrate` service (Pitfall 5)
- `migrate` core service (`pgvector/pgvector:pg16`, ships `psql`), binds `./migrations:/migrations:ro`,
  `depends_on: postgres service_healthy`, applies the four files in lexical order via
  `psql -v ON_ERROR_STOP=1 -h postgres -U postgres -d agent_mesh -f` (0001_init → 0002_self_improvement
  → 0003_tool_call_fields → 0004_active_version) then exits 0. Files are dollar-quote-free
  (verified) so straight `psql -f` is safe — the conftest comment-strip/split applier is NOT
  reimplemented.
- `api`, `worker`, AND `gui` each gain `depends_on: migrate { condition: service_completed_successfully }`
  (merged with their existing postgres dependency). A fresh `make compose-up` now comes up with
  a schema → SC-1 is functional, not just parseable.

### Task 3 — Langfuse v3 self-host (D-03, Pitfall 1)
- 6 inline containers, EVERY one `profiles: [langfuse]`: `langfuse-web` (`docker.io/langfuse/langfuse:3`,
  `:3000`, `/api/public/health` healthcheck, full `service_healthy` depends-on graph), `langfuse-worker`
  (`docker.io/langfuse/langfuse-worker:3`, env expanded to real keys — not a comment), `langfuse-postgres`
  (`docker.io/postgres:17` — RENAMED per Pitfall 1, own volume `langfuse_pgdata`, `pg_isready`), `clickhouse`
  (`clickhouse/clickhouse-server`, `clickhouse_data`, `/ping`), `redis` (`redis:7`, `--requirepass`, `redis-cli ping`),
  `minio` (`cgr.dev/chainguard/minio` verbatim, `minio_data`, `mc ready local`, upstream `sh -c 'mkdir -p
  /data/langfuse && minio server ...'` bucket pre-creation).
- **A4 re-verify done (execution-time):** the `langfuse-web`/`langfuse-worker` env keys and the minio
  service were diffed against the live upstream `langfuse/langfuse` `main` docker-compose.yml (fetched
  2026-06-10). Every env key used (`DATABASE_URL`, `NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY`,
  `CLICKHOUSE_MIGRATION_URL`/`URL`/`USER`/`PASSWORD`/`CLUSTER_ENABLED`, `REDIS_HOST`/`PORT`/`AUTH`,
  the full `LANGFUSE_S3_EVENT_UPLOAD_*` + `LANGFUSE_S3_MEDIA_UPLOAD_*` set) is a verified subset of
  upstream — no typos. The minio entrypoint/command and `mc ready local` healthcheck were corrected to
  match upstream (pre-creates the `langfuse` bucket; missing it 404s ingestion).
- Pitfall 1: Langfuse `DATABASE_URL` points at `langfuse-postgres:5432` (NOT the mesh `postgres`);
  mesh `postgres` stays pgvector/pg16, langfuse pg is postgres:17 — distinct names AND volumes.
- Dev-default server secrets (NEXTAUTH_SECRET/SALT/ENCRYPTION_KEY + clickhouse/redis/minio creds)
  each marked `# CHANGEME` for RUNBOOK (10-03) disclosure.
- Profile-gating verified: all six absent from the bare `docker compose config --services`; present
  only under `--profile langfuse`.

## Verification

Docker present (27.x / compose v2.32.4), so `docker compose config` ran for real, not just greps.

| Check | Result |
|-------|--------|
| `docker compose config -q` (bare) parses | PASS |
| `docker compose --profile vllm --profile cpu --profile langfuse config -q` parses | PASS |
| core `{api,worker,gui,postgres,migrate}` present | PASS |
| `litellm` absent (D-06) | PASS |
| `pgvector/pgvector:pg16` in vllm+cpu render | PASS |
| Finding #1 mount regex appears twice (api+worker) | PASS |
| `grep -c model_gateway.config.yaml:ro` == 2 | PASS |
| Finding #2 socket mount `/var/run/docker.sock:/var/run/docker.sock` | PASS |
| `TMPDIR` + `MESH_SBX_DIR` present | PASS |
| vLLM tag pinned (not `:latest`) — `v0.6.6` | PASS |
| Ollama tag pinned (not `:latest`) — `0.5.4` | PASS |
| `POSTGRES_DB agent_mesh` (DSN parity) | PASS |
| migrate is a core/non-profiled service | PASS |
| `./migrations:/migrations:ro` bind | PASS |
| `ON_ERROR_STOP` >= 1 | PASS |
| four `.sql` filenames referenced (count == 4) | PASS |
| `service_completed_successfully` >= 3 (api+worker+gui) | PASS |
| `grep -A6 'migrate:' \| grep service_healthy` (migrate waits for pg) | PASS |
| six langfuse services under `--profile langfuse` | PASS |
| langfuse services ABSENT from bare set (profile-gating, L2) | PASS |
| Pitfall 1: mesh pg = pgvector/pg16, langfuse-postgres = postgres:17 (distinct) | PASS |
| `cgr.dev/chainguard/minio` verbatim | PASS |
| `# CHANGEME` count >= 4 | PASS |
| distinct named volumes `langfuse_pgdata`/`clickhouse_data`/`minio_data` | PASS |
| `healthcheck:` count == 9 (>= 4 COMPOSE-03 floor) | PASS |
| profiled `{vllm,langfuse-web}` appear only when `--profile` named | PASS |
| `git diff f0545eb..HEAD -- src/` empty | PASS (zero src change) |
| only `docker-compose.yml` changed vs base | PASS |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Expanded `langfuse-worker` env to real keys**
- **Found during:** Task 3
- **Issue:** The RESEARCH block abbreviated `langfuse-worker`'s backing-store env as a
  `# same env as langfuse-web` comment. Shipping the comment as the service body would leave
  the worker unconfigured, so a future operator `--profile langfuse` bring-up (10-03) would
  fail to ingest.
- **Fix:** Expanded the worker env to the real `DATABASE_URL`/`SALT`/`ENCRYPTION_KEY`/clickhouse/
  redis/S3 keys mirroring `langfuse-web` (server secrets still `# CHANGEME`). Profile-gated and
  not bring-up-tested this phase, but correct for the milestone's "real, locally-validated" intent.
- **Files modified:** docker-compose.yml
- **Commit:** 5e5a9df

**2. [Rule 2 - Missing critical functionality] Added an api `/health` healthcheck**
- **Found during:** Task 1
- **Issue:** The plan's healthcheck discretion (RESEARCH default) names api among the 4
  healthchecked services; the `>= 4` COMPOSE-03 floor is already met by postgres + the model
  backends + langfuse services, but the api `/health` check was added for real readiness
  signalling (cheap; FastAPI exposes `/health` per E2E tests).
- **Files modified:** docker-compose.yml
- **Commit:** fa04bba

Both are additive correctness improvements within the config-only / zero-`src/` boundary.

**3. [A4 re-verify] Corrected minio entrypoint to match upstream (bucket pre-creation)**
- **Found during:** Task 3 post-commit A4 re-verify (the task instruction to re-verify env-key
  spellings against upstream `main` at execution time).
- **Issue:** The initial minio entrypoint (`sh -c "minio server /data --console-address ':9001'"`)
  was reconstructed from memory and did not pre-create the `langfuse` S3 bucket; upstream's form
  does (`mkdir -p /data/langfuse && minio server ...`). Without the bucket, Langfuse event/media
  ingestion 404s on first use.
- **Fix:** Aligned the minio `entrypoint: sh` + `command: -c 'mkdir -p /data/langfuse && minio server
  --address ":9000" --console-address ":9001" /data'` and the `["CMD","mc","ready","local"]` healthcheck
  to the upstream `main` compose. Env keys were confirmed correct (no change needed).
- **Files modified:** docker-compose.yml
- **Commit:** (folded into the Langfuse commit chain — see below)

## Bring-up-unverified (out-of-scope this phase; 10-03 / operator must confirm)

COMPOSE-01 is satisfied by static `docker compose config` (this phase's scope); a real
`make compose-up` is operator-only (10-03). The following were NOT bring-up-tested here and
must be confirmed before first real bring-up:
- **Model image tags** `vllm/vllm-openai:v0.6.6` and `ollama/ollama:0.5.4` are pinned concrete
  tags (replacing the research `:latest`) reconstructed from known-good releases; confirm they
  exist/pull on the target box (GPU for vLLM). A wrong tag fails at pull time, not at `config`.
- **Langfuse env semantics:** the env *keys* are upstream-verified (A4 above), but a full
  ingestion bring-up (clickhouse migrations, minio bucket, redis queue) is unexercised this phase.
- **Chainguard minio shell:** the upstream `entrypoint: sh` assumes `sh`/`mc` are present in the
  Chainguard image (upstream relies on it); confirm on first bring-up.

## Authentication Gates

None.

## Known Stubs

None — `docker-compose.yml` is a complete, parseable single-file stack consumed as-is by
10-03 (make targets + RUNBOOK + COMPOSE-03 test). The blank `LANGFUSE_PUBLIC_KEY`/`SECRET_KEY`
and the `# CHANGEME` Langfuse server secrets are intentional dev-only defaults (D-03a / Pitfall 1
disclosure surface), not stubs — they are documented as operator-supplied in RUNBOOK by 10-03.

## Threat Flags

None beyond the plan's declared `<threat_model>` register (T-10-02-01..04: dev-only docker-socket
DooD mount, inline dev secrets, mesh/Langfuse pg distinctness). No new security surface was
introduced beyond what the plan anticipated. All are dev-only-scoped and RUNBOOK-disclosed (10-03);
none are in the deploy path.

## Self-Check: PASSED
- FOUND: docker-compose.yml
- FOUND commit: fa04bba (Task 1 — core + model backends)
- FOUND commit: c7946d4 (Task 2 — migrate service)
- FOUND commit: 5e5a9df (Task 3 — Langfuse v3)
- `git diff f0545eb..HEAD -- src/` empty (zero src change)
