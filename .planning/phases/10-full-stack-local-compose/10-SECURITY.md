---
phase: 10
slug: full-stack-local-compose
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-10
---

# Phase 10 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Scope: a deliberate **zero-`src/`-change, LOCAL/OFFLINE dev-POC** milestone (config / docker /
> docs / tests only). Hardening is explicitly deferred — see `docs/production-readiness-caveats.md`.
> The genuine security surface in this phase is the worker **docker-socket (DooD) mount**: an
> accepted, RUNBOOK-disclosed dev-only risk that never exists in the deploy path (production uses
> Cloud Run Jobs, not a socket mount).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| build context → image | repo files copied into the shared image; `.dockerignore` limits what crosses | source code, configs (no secrets — excluded) |
| worker container → host docker daemon | `/var/run/docker.sock` bind grants the worker effective host-root (DooD) — the one real escalation surface | container-exec commands (host-root-equivalent) |
| operator → compose dev secrets | Langfuse/clickhouse/minio/postgres default creds inline in compose | dev-only credentials (`# CHANGEME`) |
| mesh pg ↔ Langfuse pg | two distinct Postgres instances; must not collide | task/audit state vs Langfuse trace state |
| CI test → docker CLI | COMPOSE-03 test shells out to `docker compose config` (daemon-free, client-side) | compose config (no live data) |
| operator docs → secrets | RUNBOOK discloses dev-only creds/socket; no secret values beyond `# CHANGEME` pointers | disclosure text only |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-10-01-01 | Information Disclosure | Dockerfile build context | mitigate | `.dockerignore` excludes `.venv/` (:14), `.env` (:23), `.git` (:27), `.sbxwork/` (:31), active config-swap `config/model_gateway.config.yaml` (:36) — secrets/local state never enter image layer | closed |
| T-10-01-02 | Tampering | docker CLI binary in image | accept | `Dockerfile:48` installs `docker-cli` (client only, no daemon); dangerous socket wired/disclosed in 10-02/10-03, not baked here | closed |
| T-10-01-SC | Tampering | pip/apt installs in Dockerfile | accept | `Dockerfile:46-50` only `docker-cli` + `ca-certificates` from base distro repo; no new PyPI packages (`tech-stack.added: []`) | closed |
| T-10-02-01 | Elevation of Privilege | worker `/var/run/docker.sock` mount (D-02) | accept (dev-only) + mitigate | `docker-compose.yml:89` socket on `worker` only; `RUNBOOK.md:282-288` discloses DEV-ONLY host-root-equivalent, prod uses Cloud Run Jobs. Disclosure IS the mitigation | closed |
| T-10-02-02 | Information Disclosure | Langfuse `NEXTAUTH_SECRET`/`SALT`/`ENCRYPTION_KEY` + clickhouse/redis/minio creds | accept (dev-only) + mitigate | `docker-compose.yml:253-255` each `# CHANGEME` (31 total markers); `RUNBOOK.md:306-309` local-only-must-replace | closed |
| T-10-02-03 | Information Disclosure | mesh `postgres` default creds (`postgres/postgres`) | accept (dev-only) | `docker-compose.yml:43,76,115` Phase-9 pinned dev-DSN parity; local-only; replaced per RUNBOOK | closed |
| T-10-02-04 | Tampering | mesh pg vs Langfuse pg collision (Pitfall 1) | mitigate | `docker-compose.yml:322` Langfuse pg renamed `langfuse-postgres` + own volume `langfuse_pgdata` (:330); mesh app services → `postgres:5432/agent_mesh` exclusively. No shared state | closed |
| T-10-03-01 | Elevation of Privilege | docker-socket mount (disclosed here) | mitigate | `RUNBOOK.md:282-288` explicit DEV-ONLY host-root-equivalent disclosure — the disclosure is the declared mitigation for the 10-02 surface | closed |
| T-10-03-02 | Information Disclosure | `.env.example` cleanliness | mitigate | `.env.example:54` `ANTHROPIC_API_KEY=` empty; no `sk-` values; `VERTEX_LOCATION=australia-southeast1` is a non-secret region string. No valued cloud key | closed |
| T-10-03-03 | Tampering | unintended `src/` edit | mitigate | `git diff 5b787196..HEAD -- src/` empty across 20 phase-10 commits; changes confined to Dockerfile/.dockerignore/config compose profiles/docker-compose.yml/Makefile/RUNBOOK/.env.example/test. **See Audit Note 1** | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-10-01 | T-10-01-02 | docker CLI client binary enables DooD; image carries client only, socket is compose-declared dev-only | dr.robert.li (POC owner) | 2026-06-10 |
| AR-10-02 | T-10-01-SC | `docker-cli` + `ca-certificates` from base distro repo without supply-chain pinning; dev-POC, no new PyPI packages | dr.robert.li (POC owner) | 2026-06-10 |
| AR-10-03 | T-10-02-01 | `/var/run/docker.sock` grants worker host-root equivalent; local-dev-only, prod uses Cloud Run Jobs, RUNBOOK-disclosed | dr.robert.li (POC owner) | 2026-06-10 |
| AR-10-04 | T-10-02-02 | Langfuse/clickhouse/redis/minio creds are inline plaintext dev defaults, each `# CHANGEME`, RUNBOOK instructs replacement | dr.robert.li (POC owner) | 2026-06-10 |
| AR-10-05 | T-10-02-03 | Mesh postgres `postgres:postgres` dev creds; matches Phase-9 pinned DSN; replaced per RUNBOOK for real deployment | dr.robert.li (POC owner) | 2026-06-10 |

*Accepted risks do not resurface in future audit runs. All are local-dev-only and absent from the deploy path; production hardening is tracked in `docs/production-readiness-caveats.md`.*

---

## Audit Notes

**Note 1 (T-10-03-03 — non-blocking, carry to Phase 11):** The zero-`src/`-change invariant was
enforced this phase as a **one-shot operator/bash gate** (10-03-PLAN Task 4), NOT as a durable CI
assertion inside `tests/test_compose_config.py` (the test file contains no `git diff` call). The
property **holds for Phase 10** (verified: empty `src/` diff vs phase base `5b787196`), but there
is no ongoing automated enforcement. Phase 11 also carries the zero-`src/` guardrail — consider
adding a durable test-level assertion there if continuous enforcement is wanted. Accepted as-is for
Phase 10; does not reopen the threat (the property is satisfied).

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-10 | 10 | 10 | 0 | gsd-security-auditor (sonnet) via /gsd:secure-phase 10 |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-10
