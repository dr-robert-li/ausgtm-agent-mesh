# Phase 9: Local Data & Telemetry Plane - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-10
**Phase:** 9-Local Data & Telemetry Plane
**Areas discussed:** PG provisioning mechanism, Self-hosted Langfuse depth, Migration applier completeness, Local DSN/env defaults

---

## PG provisioning mechanism (LDATA-01)

| Option | Description | Selected |
|--------|-------------|----------|
| `make run-pg` one-liner | Single `docker run pgvector/pgvector:pg16`, named volume, port 5432; best-effort operator target | ✓ |
| Document-only BYO Postgres | No make target; RUNBOOK says point DSNs at any local pgvector:pg16 | |
| Single-service compose now | Minimal docker-compose.pg.yml; overlaps Phase 10 compose ownership | |

**User's choice:** `make run-pg` one-liner (Recommended).
**Notes:** Real & runnable now, one container only; leaves the multi-service stack to Phase 10. Mirrors Phase 8's best-effort run-target pattern.

---

## Self-hosted Langfuse depth (LDATA-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Wire env + document upstream self-host; loud-skip | RUNBOOK documents upstream `docker compose` + env wiring; telemetry loud-skips when keys unset; no P9 standup target | ✓ |
| `make run-langfuse` pulls upstream compose | Make target fetches+runs upstream Langfuse compose; duplicates Phase 10, pins external file | |

**User's choice:** Wire env + document upstream self-host; loud-skip (Recommended).
**Notes:** Honest, no duplication; heavy multi-container assembly deferred to Phase 10's stack.

---

## Migration applier completeness (LDATA-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Fix to all four (0001-0004) + assert | Applier globs/applies all migrations in order; LDATA-03 test asserts resulting schema + reachability | ✓ |
| Mirror existing 2-migration behavior | Keep applying 0001/0002 only; minimal but under-validates | |

**User's choice:** Fix to all four (0001-0004) + assert (Recommended).
**Notes:** Closes a latent gap (conftest applied only 0001/0002 while 0003/0004 exist); test genuinely validates "migrations applied". Test-code only, zero src/. Keep the plain-DDL `;`-split invariant noted in conftest.

---

## Local DSN / env defaults (LDATA-01/02)

| Option | Description | Selected |
|--------|-------------|----------|
| Pin concrete local defaults | Copy-paste DSNs + image + LANGFUSE_HOST in .env.example + RUNBOOK; `make test-pg` works out-of-box | ✓ |
| Keep blank + prose guidance | Leave values blank, document shape only | |

**User's choice:** Pin concrete local defaults (Recommended).
**Notes:** `postgresql://postgres:postgres@localhost:5432/agent_mesh`, pgvector:pg16, local LANGFUSE_HOST `http://localhost:3000`. Local-only creds, low risk; RUNBOOK discloses dev-only.

---

## Claude's Discretion

- Exact `docker run` flags for `run-pg` (volume name, healthcheck, `--rm` vs persistent).
- `make` target naming around DB apply (keep existing `test-pg` contract intact).
- Precise schema assertions in the LDATA-03 test (which 0003/0004 objects).

## Deferred Ideas

- Full multi-container self-hosted Langfuse standup → Phase 10 compose.
- docker-compose for Postgres → Phase 10 one-command stack.
- `make run-langfuse` upstream-compose target → deferred (duplicates Phase 10).
- pgvector index tuning / AlloyDB or Vertex Vector Search migration → production hardening.
