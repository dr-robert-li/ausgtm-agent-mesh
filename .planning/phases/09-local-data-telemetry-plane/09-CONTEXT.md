# Phase 9: Local Data & Telemetry Plane - Context

**Gathered:** 2026-06-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Document and wire a fully **local** persistence + observability plane so the durable
lane runs on-box: local **Postgres(pgvector)** replacing Cloud SQL, and **self-hosted
Langfuse** replacing cloud Langfuse, for local dev. Deliver LDATA-01/02/03 via
**Makefile targets + RUNBOOK docs + a test + `.env.example` wiring only — zero `src/`
change** (same milestone guardrail as Phase 8; deployment/env names unchanged so the
app reads the local DSN/host with no code edit).

**In scope:** a local pgvector run path make-wired to `DATABASE_URL`/`TEST_DATABASE_URL`
that applies the existing migrations; a documented self-hosted Langfuse env-wiring path;
an end-to-end durable-lane test (`make test-pg` against the local DSN) that asserts
migrations apply + DB reachable, loud-skipping when the DSN is unset.

**Out of scope (Phase 10 owns):** the one-command multi-service `docker-compose` stack
(api+worker+gui+pg+langfuse+litellm+model). Phase 9 stands up at most single best-effort
containers and documents the rest; it does not assemble the full stack.
</domain>

<decisions>
## Implementation Decisions

### A — Local Postgres provisioning (LDATA-01)
- **D-01 (`make run-pg` one-liner):** A best-effort `make run-pg` target runs a **single**
  `docker run pgvector/pgvector:pg16` (named volume for persistence, port 5432). Real and
  runnable now, one container only — the full multi-service stack is Phase 10. Mirrors
  Phase 8's best-effort operator run-target pattern (kept out of `make test`/CI).

### B — Self-hosted Langfuse depth (LDATA-02)
- **D-02 (wire env + document upstream self-host; loud-skip):** RUNBOOK documents the
  **upstream Langfuse `docker compose` self-host path** plus env wiring
  (`LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`); telemetry **loud-skips**
  when keys are unset (mirror existing behavior). **No P9 `make run-langfuse` standup
  target** — actual multi-container Langfuse assembly is deferred to Phase 10's compose.
  Honest, no duplication. (The more-real `make run-langfuse` variant was considered and
  deferred to avoid pinning an external compose file twice.)

### C — Migration applier completeness (LDATA-03)
- **D-03 (apply all four + assert schema):** `tests/conftest.py:_apply_migrations`
  currently applies only `0001/0002`, but `0003/0004` exist — a latent gap. Fix the applier
  to apply **all** migrations in `migrations/` in lexical order (`0001`→`0004`), and have
  the LDATA-03 test assert the **resulting schema** (objects introduced by 0003/0004, e.g.
  tool-call fields + active-version row) plus DB reachability. **Loud-skip** when
  `TEST_DATABASE_URL` is unset. Test-code only — **zero `src/` change**. Honor the existing
  conftest limitation note: migrations are plain comment-free DDL split on `;` (no
  statement that legitimately contains a semicolon) — keep that invariant when generalizing.

### D — Local DSN / env defaults (LDATA-01/02)
- **D-04 (pin concrete copy-paste local defaults):** Put runnable defaults in
  `.env.example` + RUNBOOK so `make test-pg` works out-of-box —
  `DATABASE_URL` and `TEST_DATABASE_URL` = `postgresql://postgres:postgres@localhost:5432/agent_mesh`
  (matching the `make run-pg` container creds/port), image `pgvector/pgvector:pg16`, and a
  local `LANGFUSE_HOST` (self-host default `http://localhost:3000`). Local-only credentials,
  low risk. RUNBOOK discloses these are dev-only defaults.

### Carried forward from Phase 8 (do not re-litigate)
- **Zero `src/` change** — config/Makefile/docs/tests only (assert `git diff <base>..HEAD -- src/` empty).
- **make + RUNBOOK + loud-skip-test** delivery pattern; run/standup targets are best-effort,
  operator-only, NEVER wired into `make test`/CI.
- **Honest disclosure** in RUNBOOK (dev-only creds, best-effort targets, what's deferred to P10).
- Reuse the **existing** `test-pg`/`test-live` Makefile targets and `conftest` fixture rather than new seams.

### Claude's Discretion
- Exact `docker run` flags for `run-pg` (volume name, healthcheck, `--rm` vs persistent).
- `make` target naming around DB apply (`run-pg` vs an additional `migrate`/`db-up` alias) —
  planner/researcher choose, keeping the existing `test-pg` contract intact.
- Precise schema assertions in the LDATA-03 test (which tables/columns from 0003/0004).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` §"Phase 9: Local Data & Telemetry Plane" — goal + 3 success criteria.
- `.planning/REQUIREMENTS.md` — LDATA-01/02/03 (lines ~126-128, traceability ~214-216).
- `.planning/phases/08-local-inference-lane/08-CONTEXT.md` — carry-forward pattern (file-swap/make/RUNBOOK/loud-skip, zero-src, honest disclosure).

### Migrations & durable lane (the assets being wired)
- `migrations/0001_init.sql`, `0002_self_improvement.sql`, `0003_tool_call_fields.sql`, `0004_active_version.sql` — the DDL the applier must apply in order.
- `migrations/README.md` — migration conventions.
- `tests/conftest.py` — `_apply_migrations(dsn)` fixture to FIX (currently 0001/0002 only); existing `TEST_DATABASE_URL` loud-skip + pgvector:pg16 note.
- `Makefile` — existing `test-pg:` (L47) and `test-live:` (L40) targets to reuse; `use-*`/`run-*` (L90-94) pattern to mirror.
- `.env.example` — `DATABASE_URL=` (L13, blank), `LANGFUSE_HOST`/`LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` (L27/44/45) to pin local defaults into.
- `RUNBOOK.md` — insertion point for the local data/telemetry section (follows the Phase 8 "Local inference lane" section).

### Reference-only (read to understand env wiring; DO NOT edit — zero src/ change)
- `src/agent_mesh/settings.py` — reads `DATABASE_URL` + `LANGFUSE_*` (confirms env names; no edit).
- `src/agent_mesh/services/repository.py`, `worker/orchestrator.py` — durable lane consumers (context only).

No new external specs/ADRs — decisions fully captured above.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tests/conftest.py:_apply_migrations` — the migration applier; extend to all four + keep loud-skip.
- `Makefile` `test-pg`/`test-live` targets + `run-*`/`use-*` best-effort pattern — model `run-pg` on these.
- `migrations/` 0001-0004 plain DDL — applied externally by the test fixture (repo never self-applies).
- `.env.example` already carries `DATABASE_URL` + `LANGFUSE_*` keys — pin defaults, no new keys needed.

### Established Patterns
- Phase 8 "best-effort operator run-target, out of CI, RUNBOOK-documented, loud-skip-on-unset-env" — apply verbatim to `run-pg` + the LDATA-03 test.
- `settings.py` already env-driven for DATABASE_URL + LANGFUSE_HOST — local wiring needs NO src change.

### Integration Points
- `make run-pg` container creds/port MUST match the pinned `DATABASE_URL` default (D-01 ↔ D-04).
- LDATA-03 test rides the existing `test-pg` lane + conftest fixture; no new test harness.
</code_context>

<specifics>
## Specific Ideas

- Pin the pgvector image explicitly as `pgvector/pgvector:pg16` (matches the conftest note that
  0001 needs a pgvector-enabled image, not vanilla postgres).
- Langfuse local default host `http://localhost:3000` (upstream self-host default port).
- DSN default `postgresql://postgres:postgres@localhost:5432/agent_mesh`.
</specifics>

<deferred>
## Deferred Ideas

- **Full multi-container self-hosted Langfuse standup** (web+worker+postgres+clickhouse+redis+minio) → **Phase 10** compose.
- **docker-compose for Postgres** (single-service compose) → folded into **Phase 10**'s one-command stack.
- **`make run-langfuse`** upstream-compose-pulling target → deferred (would duplicate Phase 10; revisit if P10 slips).
- **pgvector index tuning / AlloyDB or Vertex Vector Search migration** → production hardening (per architecture risks).

None of the above is in Phase 9 scope; discussion stayed within the local-wiring boundary.
</deferred>

---

*Phase: 9-Local Data & Telemetry Plane*
*Context gathered: 2026-06-10*
