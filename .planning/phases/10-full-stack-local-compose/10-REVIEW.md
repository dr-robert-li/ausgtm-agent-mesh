---
phase: 10-full-stack-local-compose
reviewed: 2026-06-10T08:35:40Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - Dockerfile
  - .dockerignore
  - docker-compose.yml
  - config/model_gateway.vllm.compose.yaml
  - config/model_gateway.cpu.compose.yaml
  - Makefile
  - RUNBOOK.md
  - .env.example
  - tests/test_compose_config.py
findings:
  critical: 2
  warning: 3
  info: 4
  total: 9
status: resolved
resolved: 2026-06-10T08:40:00Z
resolution_commit: cd5de7a
---

> **Resolution (2026-06-10, commit `cd5de7a`):** Both Criticals fixed in `docker-compose.yml`
> (CR-01 api healthcheck `/health`→`/healthz` to match `GET /healthz` in app.py; CR-02 redis
> healthcheck given `-a myredissecret` to clear NOAUTH). WR-03 Dockerfile comment corrected to
> `docker-cli`. **WR-01 + WR-02 (clickhouse + chainguard-minio untagged) BOTH retained as accepted
> dev-only risk, matching langfuse upstream `main` verbatim** — langfuse itself floats both images
> (`clickhouse/clickhouse-server` and `cgr.dev/chainguard/minio`, no tags), and chainguard publishes
> no free semver tag; pinning to a number langfuse does not test against would *diverge* from
> upstream and risk a wrong-tag bring-up failure (operator-verify, out of static-config scope).
> A first commit (`cd5de7a`) pinned `clickhouse:24.3`, then `<follow-up>` reverted it to upstream-
> floating after confirming via WebFetch that langfuse `main` does not pin clickhouse. Info items
> left as-is (dev-POC tradeoffs). Zero `src/` change; compose parses (bare + all-profile);
> `test_compose_config` 6/6.

# Phase 10: Code Review Report

**Reviewed:** 2026-06-10T08:35:40Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Phase 10 delivers the full-stack local compose scaffold: a shared `Dockerfile`,
profile-gated `docker-compose.yml` (vllm/cpu/langfuse), two compose-variant model
profile configs, Makefile operator targets, RUNBOOK section, `.env.example`
annotation, and a static-parse test. Zero source files changed; the zero-src
invariant holds.

All documented dev-only tradeoffs (docker-socket DooD mount, UI-minted Langfuse
keys, all-zeros `ENCRYPTION_KEY`, `# CHANGEME` secrets, vLLM GPU requirement, and
the embedded LiteLLM router) are properly disclosed in RUNBOOK.md and are not
flagged as defects.

Two critical issues were found that cause permanent stack startup failures when the
`langfuse` profile is active. Three warnings cover reproducibility and a stale
comment. Four info items cover image hardening gaps and a duplicate schema
declaration.

---

## Critical Issues

### CR-01: API healthcheck probes wrong route — 404 on every check, service perpetually unhealthy

**File:** `docker-compose.yml:63`
**Issue:** The `api` service healthcheck probes `http://localhost:8080/health` but the
FastAPI application only registers `GET /healthz` (app.py:34). Every probe returns
HTTP 404. The `urllib.request.urlopen` call raises `urllib.error.HTTPError: HTTP
Error 404: Not Found`, which exits non-zero. The `api` service will never reach
`healthy`. Because `worker` and `gui` both declare `depends_on: api: condition:
service_healthy`, neither will start until `api` is healthy. The entire stack
(minus postgres/migrate) is permanently blocked.

**Evidence:**
- `docker-compose.yml:63`: `urlopen('http://localhost:8080/health')`
- `src/agent_mesh/api/app.py:34`: `@app.get("/healthz")`
- RUNBOOK.md:62 also documents the route as `/healthz`

**Fix:**
```yaml
# docker-compose.yml — api service healthcheck (line 63)
healthcheck:
  test: ["CMD-SHELL", "python -c \"import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/healthz').status==200 else 1)\""]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

---

### CR-02: Redis healthcheck has no auth credentials — NOAUTH failure blocks entire Langfuse stack

**File:** `docker-compose.yml:355-357`
**Issue:** The `redis` service starts with `--requirepass myredissecret` (line 355),
which requires all clients — including `redis-cli` — to authenticate. The
healthcheck at line 357 runs `redis-cli ping` without any `-a PASSWORD` flag. Redis
7 with `requirepass` set responds to an unauthenticated connection with:

```
NOAUTH Authentication required
```

`redis-cli` exits with a non-zero code. The healthcheck fails on every attempt
through all `retries: 10`. The `redis` service never reaches `healthy`. Because
`langfuse-web` and `langfuse-worker` both declare `depends_on: redis: condition:
service_healthy`, neither will start. The Langfuse observability stack is
permanently broken when brought up with `--profile langfuse`.

**Fix:**
```yaml
# docker-compose.yml — redis service healthcheck (line 356-360)
healthcheck:
  test: ["CMD", "redis-cli", "-a", "myredissecret", "ping"]
  interval: 10s
  timeout: 3s
  retries: 10
```

Alternatively (avoids echoing the password in process args on Redis 6+):

```yaml
healthcheck:
  test: ["CMD-SHELL", "redis-cli -a $$REDIS_PASSWORD ping"]
  interval: 10s
  timeout: 3s
  retries: 10
```

where `REDIS_PASSWORD` is passed as an environment variable to the container. Either
form resolves the NOAUTH failure.

---

## Warnings

### WR-01: `clickhouse/clickhouse-server` image has no version tag — floats to latest

**File:** `docker-compose.yml:338`
**Issue:** `image: docker.io/clickhouse/clickhouse-server` has no tag. Docker
resolves this to `:latest`, pulling whatever the upstream registry currently
serves. ClickHouse has breaking config-format changes between minor versions (e.g.,
the `<zookeeper>` → Keeper transition between 22.x and 24.x). An untagged image
produces a non-reproducible stack and can break silently when the upstream tag
moves. All other Langfuse-profile images in the same file are pinned
(`langfuse:3`, `langfuse-worker:3`, `redis:7`, `postgres:17`).

**Fix:**
```yaml
# docker-compose.yml:338
image: docker.io/clickhouse/clickhouse-server:24.8
```

Pin to the ClickHouse version validated against Langfuse v3 (check
`docker.io/langfuse/langfuse:3`'s own `docker-compose.yml` for the tested
ClickHouse version).

---

### WR-02: `cgr.dev/chainguard/minio` image has no version tag — floats to latest

**File:** `docker-compose.yml:363`
**Issue:** `image: cgr.dev/chainguard/minio` has no tag. Chainguard images use
date-stamped or semver tags; without a tag this floats to `:latest`. The Chainguard
minio image has a non-standard entrypoint and `mc` tooling path that differ from
`minio/minio`. An upstream tag move can silently break the bucket pre-creation
`entrypoint` command on line 368. The comment "keep Chainguard registry verbatim"
captures the registry rationale but does not address the version drift risk.

**Fix:**
```yaml
# docker-compose.yml:363
image: cgr.dev/chainguard/minio:YYYYMMDD
```

Pin to a specific date-stamped digest or tag. Verify the pinned version's `mc`
binary path matches the healthcheck `["CMD", "mc", "ready", "local"]` at line 375.

---

### WR-03: Dockerfile line 20 stale comment names `docker.io` OS package; actual install is `docker-cli`

**File:** `Dockerfile:20`
**Issue:** The comment reads:

> `binary (the \`docker.io\` OS package).`

But the `RUN apt-get install` at line 47 installs `docker-cli`, not `docker.io`.
On Debian trixie, `docker.io` ships only the daemon (`dockerd`); `docker-cli`
ships the client binary the worker actually needs. The comment is contradicted by
both the RUN command below it and by the corrective note at lines 37-40 which
correctly names `docker-cli`. A developer reading line 20 gets false information
about what is installed.

**Fix:**
```dockerfile
# Dockerfile:20 — change:
# binary (the `docker.io` OS package).
# to:
# binary (the `docker-cli` OS package).
```

---

## Info

### IN-01: `tests/` directory not excluded from `.dockerignore` — test files baked into app image

**File:** `.dockerignore`
**Issue:** The `.dockerignore` excludes `.venv/`, `.git/`, `.sbxwork/`,
`config/model_gateway.config.yaml`, `docker/`, `.planning/`, `.claude/`,
`graphify-out/`, and `.DS_Store`, but not `tests/`. All test files (pytest
fixtures, E2E test modules, compose config tests, smoke tests) are copied into
the production image layer by `COPY . /app`. This adds test-only dependencies
to the image surface (the `pytest` fixture infrastructure) and expands the attack
surface at runtime, though no direct security impact exists in this POC context.

**Fix:** Add to `.dockerignore`:
```
tests/
```

---

### IN-02: `ai_bom_snapshots` table declared twice across migrations — silent duplicate DDL

**Files:** `migrations/0001_init.sql:188-199`, `migrations/0004_active_version.sql:34-48`
**Issue:** `CREATE TABLE IF NOT EXISTS ai_bom_snapshots` appears in both 0001 and
0004. The `IF NOT EXISTS` guard means the second declaration is silently ignored on
any schema that ran 0001 first (all normal flows). However, the two declarations
differ in their `DEFAULT` syntax (`'[]'::jsonb` in 0001 vs `'[]'` bare string in
0004). If ever run against a fresh DB starting from 0004 (e.g., targeted migration
replay), the schema created differs subtly. The duplicate also creates a
maintenance trap: adding a column to `ai_bom_snapshots` requires updating both
files or the developer must know which one actually won.

**Fix:** Remove the `ai_bom_snapshots` DDL block from `migrations/0004_active_version.sql`
(lines 34-48). The table is owned by 0001 and the `idx_ai_bom_snapshots_tenant`
index in 0004 can be kept if it was added in that phase; otherwise remove both.

---

### IN-03: No `EXPOSE` declarations in Dockerfile

**File:** `Dockerfile`
**Issue:** The shared image serves three roles: api (port 8080), gui (Streamlit,
8501), and worker (no listening port). No `EXPOSE` declarations are present. While
`EXPOSE` is documentation-only and does not affect runtime networking, its absence
means `docker inspect` and compose tooling cannot auto-discover port intent, and
operators running the image outside compose (e.g., `docker run -P`) get no
automatic port mapping.

**Fix:** Add near the bottom of the Dockerfile before any CMD/ENTRYPOINT:
```dockerfile
# Informational — actual port binding is via compose or -p flag
EXPOSE 8080
EXPOSE 8501
```

---

### IN-04: Dockerfile runs as root — no non-root USER declared

**File:** `Dockerfile`
**Issue:** No `USER` instruction is present. The container process runs as `root`
(UID 0). This is a known hardening gap; it is not a POC blocker because the
docker-socket DooD mount already requires the worker to have socket access
(which the compose `group_add: DOCKER_GID` handles at runtime). However,
the api and gui services gain no benefit from root and should run unprivileged.
This is the standard production-hardening note documented in
`docs/production-readiness-caveats.md`.

**Fix** (for api/gui roles; worker needs socket group membership):
```dockerfile
RUN groupadd --gid 1001 appuser && useradd --uid 1001 --gid 1001 --no-create-home appuser
USER appuser
```

For the worker, the non-root user must also be added to the docker GID at runtime
via compose `group_add` (already wired). A multi-stage or multi-target Dockerfile
would let the worker image retain socket group access without rooting api/gui.

---

_Reviewed: 2026-06-10T08:35:40Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
