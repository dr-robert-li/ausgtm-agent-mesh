# Phase 9: Local Data & Telemetry Plane - Research

**Researched:** 2026-06-10
**Domain:** Local persistence (Postgres + pgvector) + self-hosted observability (Langfuse) wiring; Makefile/RUNBOOK/test/.env delivery
**Confidence:** HIGH (codebase facts), MEDIUM (external Langfuse self-host facts — datable, may drift)

## Summary

Phase 9 documents and wires a fully **local** persistence + observability plane so the durable lane runs on-box, delivered through **Makefile targets + RUNBOOK docs + one test + `.env.example` wiring only — ZERO `src/` change** (same milestone guardrail as Phase 8). The settings layer (`src/agent_mesh/settings.py`) already reads `DATABASE_URL` and `LANGFUSE_HOST`/`LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` from the environment, so local wiring is purely env defaults + operator run-paths + docs — no code edit is needed or permitted.

**One material discrepancy with CONTEXT D-03 surfaced and must be reconciled by the planner (see Open Questions Q1).** D-03's premise — that `tests/conftest.py:_apply_migrations` "currently applies only 0001/0002" — is **factually stale**. The applier already iterates a four-element `_MIGRATIONS` tuple (`0001`→`0004`) in lexical order, and `_truncate` already covers the 0003/0004 tables. This was committed during Phase 6 (commit `9011377`, 2026-06-07), three days before this phase's CONTEXT was gathered. So **applier-completeness is already satisfied.** What is genuinely *not* yet done — and is the real LDATA-03 deliverable — is a **DDL-level schema-assertion test**: no existing test confirms the 0003 columns / 0004 tables exist *in the actual migrated Postgres schema* (existing tests assert them only at the Pydantic-contract and repository layers).

**Primary recommendation:** Add a best-effort `make run-pg` (single `docker run pgvector/pgvector:pg16`) mirroring the Phase 8 `run-*` pattern; pin local DSN/host defaults in `.env.example` + RUNBOOK; add ONE new DSN-gated schema-assertion test (riding the existing `pg_dsn` fixture + `test-pg` lane) that asserts the 0003 columns + 0004 tables exist in the live DB and the DB is reachable, loud-skipping when `TEST_DATABASE_URL` is unset; document the upstream self-hosted Langfuse `docker compose` path + env wiring in RUNBOOK with the full multi-container standup explicitly DEFERRED to Phase 10. Treat D-03's "apply all migrations" as already-true for 0003/0004 and flag the glob-vs-tuple intent to the planner rather than auto-changing the applier.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01 (`make run-pg` one-liner):** A best-effort `make run-pg` target runs a **single** `docker run pgvector/pgvector:pg16` (named volume for persistence, port 5432). Real and runnable now, one container only — the full multi-service stack is Phase 10. Mirrors Phase 8's best-effort operator run-target pattern (kept out of `make test`/CI).
- **D-02 (wire env + document upstream self-host; loud-skip):** RUNBOOK documents the **upstream Langfuse `docker compose` self-host path** plus env wiring (`LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`); telemetry **loud-skips** when keys are unset (mirror existing behavior). **No P9 `make run-langfuse` standup target** — actual multi-container Langfuse assembly is deferred to Phase 10's compose.
- **D-03 (apply all four + assert schema):** Fix `_apply_migrations` to apply **all** migrations in `migrations/` in lexical order (`0001`→`0004`); have the LDATA-03 test assert the **resulting schema** (objects introduced by 0003/0004 — tool-call fields + active-version row) plus DB reachability. **Loud-skip** when `TEST_DATABASE_URL` is unset. Test-code only — **zero `src/` change**. Honor the conftest invariant: migrations are plain comment-free DDL split on `;` (no statement that legitimately contains a semicolon) — keep that invariant when generalizing. *(NOTE: research found the applier already applies all four — see Open Questions Q1; the planner must reconcile the stale premise.)*
- **D-04 (pin concrete copy-paste local defaults):** `.env.example` + RUNBOOK pin `DATABASE_URL` and `TEST_DATABASE_URL` = `postgresql://postgres:postgres@localhost:5432/agent_mesh` (matching the `make run-pg` container creds/port), image `pgvector/pgvector:pg16`, and a local `LANGFUSE_HOST` default `http://localhost:3000`. Local-only credentials, low risk. RUNBOOK discloses these are dev-only defaults.

### Carried forward from Phase 8 (do not re-litigate)
- **Zero `src/` change** — config/Makefile/docs/tests only (assert `git diff <base>..HEAD -- src/` empty).
- **make + RUNBOOK + loud-skip-test** delivery pattern; run/standup targets are best-effort, operator-only, NEVER wired into `make test`/CI.
- **Honest disclosure** in RUNBOOK (dev-only creds, best-effort targets, what's deferred to P10).
- Reuse the **existing** `test-pg`/`test-live` Makefile targets and `conftest` fixture rather than new seams.

### Claude's Discretion
- Exact `docker run` flags for `run-pg` (volume name, healthcheck, `--rm` vs persistent).
- `make` target naming around DB apply (`run-pg` vs an additional `migrate`/`db-up` alias) — keep the existing `test-pg` contract intact.
- Precise schema assertions in the LDATA-03 test (which tables/columns from 0003/0004).

### Deferred Ideas (OUT OF SCOPE)
- **Full multi-container self-hosted Langfuse standup** (web+worker+postgres+clickhouse+redis+minio) → **Phase 10** compose.
- **docker-compose for Postgres** (single-service compose) → folded into **Phase 10**'s one-command stack.
- **`make run-langfuse`** upstream-compose-pulling target → deferred (would duplicate Phase 10).
- **pgvector index tuning / AlloyDB or Vertex Vector Search migration** → production hardening.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LDATA-01 | A local Postgres(pgvector) run path is documented + make-wired to `DATABASE_URL`/`TEST_DATABASE_URL` and applies the existing migrations | `make run-pg` (single `pgvector/pgvector:pg16` container, port 5432, named volume) mirroring the Phase 8 `run-*` best-effort pattern; `.env.example` pins matching DSN defaults; existing `_apply_migrations` already applies 0001→0004 (the "applies the existing migrations" clause is met by the existing fixture + `test-pg` lane). [VERIFIED: codebase] |
| LDATA-02 | A self-hosted Langfuse local run path is documented with its env wiring (`LANGFUSE_HOST`, keys) for local trace ingestion | RUNBOOK documents upstream `git clone langfuse && docker compose up` → UI at `http://localhost:3000`; operator creates project + API keys IN THE UI, then exports `LANGFUSE_HOST`/`LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`; `settings.py` already reads all three; telemetry loud-skips when keys unset. Full standup DEFERRED to Phase 10. [CITED: langfuse.com/self-hosting] [VERIFIED: settings.py] |
| LDATA-03 | The durable lane runs locally end to end (`make test-pg` against the local DSN); a test asserts the local-DSN path applies migrations and is reachable, loud-skip when unset | Existing `pg_dsn` fixture already applies all migrations + loud-skips on unset `TEST_DATABASE_URL`; existing `test-pg` target runs the durable/checkpointer lane. Genuinely-new work = ONE schema-assertion test asserting 0003 columns + 0004 tables exist in the migrated DB + reachability. No existing test does this at the DDL layer. [VERIFIED: codebase + grep] |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Local Postgres provisioning (`run-pg`) | Operator tooling (Makefile) | Docker runtime | Best-effort container standup is an operator action, never CI; mirrors P8 `run-vllm`/`run-ollama`. |
| Migration application | Test fixture (`conftest._apply_migrations`) | Database / Storage | The repo NEVER self-applies migrations; the test fixture is the external applier (psycopg, mirroring `psql -f`). |
| DSN/host configuration | Config (`.env.example`) + Settings (`src/agent_mesh/settings.py`, READ-ONLY) | — | `settings.py` already env-driven; local wiring is env defaults only — no `src/` edit. |
| Self-hosted Langfuse standup | RUNBOOK docs (path only) | Phase 10 compose | P9 documents the upstream path + wires env; full multi-container assembly is Phase 10. |
| Telemetry ingestion to Langfuse | Settings + existing callback handler (READ-ONLY) | Langfuse server | Keys generated in Langfuse UI per-project; client reads `LANGFUSE_*`; loud-skip when unset (existing behavior). |
| Schema-assertion test | Test (`tests/...`, NEW) riding `pg_dsn` fixture | `test-pg` Makefile lane | The new LDATA-03 deliverable; rides existing fixture + lane, no new harness. |

## Standard Stack

This phase installs NO new packages. It uses an existing Docker image and existing test dependencies.

### Core
| Component | Version / Tag | Purpose | Why Standard |
|-----------|---------------|---------|--------------|
| `pgvector/pgvector:pg16` (Docker image) | `pg16` tag | Local Postgres 16 with the `vector` extension pre-built so migration `0001`'s `CREATE EXTENSION vector` succeeds | The canonical pgvector image; already named in `conftest.py:_apply_migrations` docstring and `RUNBOOK.md:82-84` as the required image (a vanilla `postgres` image fails `CREATE EXTENSION vector`). [VERIFIED: codebase — conftest + RUNBOOK both pin it] [CITED: hub.docker.com/r/pgvector/pgvector — `pg16` tag is the supported Postgres-16 line] |
| `psycopg` (already a test dep) | existing pin | The fixture's external migration applier + reachability connection | Already used by `_apply_migrations`/`_truncate`/`RepositorySQL`; no new dependency. [VERIFIED: codebase] |
| Self-hosted Langfuse (v3) via upstream `docker compose` | v3 | Local observability plane replacing cloud Langfuse | Project's required observability platform (CLAUDE.md); upstream self-host is the documented path. [CITED: langfuse.com/self-hosting/docker-compose] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `pgvector/pgvector:pg16` | `ankane/pgvector` (legacy image name) | Deprecated/renamed; `pgvector/pgvector` is the current official namespace. Stick with the pinned image. |
| Single `docker run` for PG | Single-service `docker-compose` for PG | Explicitly DEFERRED to Phase 10 (CONTEXT Deferred Ideas). D-01 locks a single `docker run`. |
| `make run-langfuse` standup target | Documentation-only path | D-02 locks documentation-only (no standup target) to avoid pinning an external compose file twice before Phase 10. |

**Installation:** No `pip install`. Operator pulls the image implicitly via `make run-pg` (`docker run pgvector/pgvector:pg16`). Langfuse is `git clone https://github.com/langfuse/langfuse.git && cd langfuse && docker compose up` (documented in RUNBOOK; NOT run by any P9 make target).

## Package Legitimacy Audit

No new language packages are installed in Phase 9. The only external artifacts are Docker images pulled by operator-run, best-effort targets (never CI).

| Artifact | Registry | Notes | Disposition |
|----------|----------|-------|-------------|
| `pgvector/pgvector:pg16` | Docker Hub | Official pgvector image; already referenced and relied upon by the existing test fixture + RUNBOOK durable lane. | Approved (pre-existing project dependency) |
| `langfuse/langfuse` (via `git clone` + `docker compose`) | GitHub / Docker Hub | Project's required observability platform; documented path only, not pulled by any P9 target. | Approved (documented path; standup deferred to P10) |

*slopcheck not applicable — no PyPI/npm/crates package installs in this phase. Docker images above are pre-existing, named in the current codebase, and verified against the project's own usage.*

## Architecture Patterns

### System Architecture Diagram

```
LOCAL DEV BOX
=============

  Operator                                       make test-pg (CI-excluded lane)
     │                                                   │
     │ make run-pg                                       │ (reads TEST_DATABASE_URL)
     ▼                                                   ▼
  ┌──────────────────────────────┐          ┌────────────────────────────────────┐
  │ docker run                    │          │ tests/conftest.py : pg_dsn fixture  │
  │   pgvector/pgvector:pg16      │◄─────────│  1. loud-skip if DSN unset          │
  │   -p 5432:5432                │  DSN     │  2. _apply_migrations(0001→0004)    │
  │   -v agent_mesh_pgdata:…      │          │  3. _truncate(known tables)         │
  │   POSTGRES_USER=postgres      │          └──────────────┬─────────────────────┘
  │   POSTGRES_PASSWORD=postgres  │                         │
  │   POSTGRES_DB=agent_mesh      │                         ▼
  └──────────────────────────────┘          ┌────────────────────────────────────┐
            ▲                                │ NEW schema-assertion test (LDATA-03)│
            │ DATABASE_URL                   │  - assert 0003 cols on tool_calls   │
            │ (settings.py reads, no edit)   │  - assert 0004 tables exist         │
  ┌──────────────────────────────┐          │  - assert DB reachable              │
  │ src/agent_mesh/settings.py    │          └────────────────────────────────────┘
  │  database_url / langfuse_*    │
  │  (READ-ONLY — zero src change) │          OBSERVABILITY (documented path; standup = Phase 10)
  └──────────────────────────────┘          ┌────────────────────────────────────┐
            │ LANGFUSE_HOST / _PUBLIC / _SECRET        │ git clone langfuse                  │
            └──────────────────────────────────────►  │ docker compose up                   │
                                                       │  web(:3000)+worker+postgres+        │
              operator creates project +               │  clickhouse+redis+minio (v3)        │
              API keys IN THE UI, exports them          │ UI :3000 → create project → keys    │
                                                       └────────────────────────────────────┘
```

File-to-implementation mapping is in the Component Responsibilities table (the Architectural Responsibility Map above).

### Pattern 1: Best-effort operator run-target (mirror Phase 8 `run-vllm`/`run-ollama`)
**What:** A `make run-pg` target that issues a single `docker run pgvector/pgvector:pg16 …`, with a Makefile comment stating it is best-effort, operator-only, and never wired into `test`/CI.
**When to use:** For LDATA-01's "run path." Operator runs it once; it may fail on a box without Docker, which is acceptable and documented.
**Example (model the existing run-vllm block, `Makefile:70-84`):**
```makefile
# --- Local data plane (LDATA-01) ---------------------------------------------
# run-pg starts a single local pgvector Postgres. Best-effort, operator-run, and
# DELIBERATELY never wired into `test` or CI: it requires Docker and may fail on a
# box without it, which is acceptable and documented in RUNBOOK.md. Creds/port/db
# MUST match the pinned DATABASE_URL default in .env.example (D-01 <-> D-04).
PG_IMAGE     ?= pgvector/pgvector:pg16
PG_CONTAINER ?= agent_mesh_pg
PG_VOLUME    ?= agent_mesh_pgdata
run-pg:
	docker run -d --name $(PG_CONTAINER) \
	  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=agent_mesh \
	  -p 5432:5432 -v $(PG_VOLUME):/var/lib/postgresql/data \
	  $(PG_IMAGE)
```
*(Exact flags — `--rm` vs persistent, `-d` vs foreground, healthcheck — are the planner's discretion per CONTEXT. A named volume + persistent container is recommended so data survives restarts and `make test-pg` can re-run; document the teardown, e.g. `docker rm -f agent_mesh_pg`.)*

### Pattern 2: Documentation-only external self-host path (Langfuse)
**What:** RUNBOOK documents the upstream clone + `docker compose up` and the env wiring, but P9 ships NO target that pulls or runs the Langfuse compose. The full standup is Phase 10.
**When to use:** For LDATA-02. Keeps P9 honest (no duplicate external-compose pin) while giving the operator a complete, datable path.
**Key wiring fact:** `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` are NOT server env vars — the operator creates a project in the Langfuse UI (`http://localhost:3000`) and generates API keys there, then exports them as client-side env vars the mesh reads. The server-side secrets are different (`NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY`, `DATABASE_URL`, ClickHouse/Redis/S3 vars). RUNBOOK should make this client-vs-server distinction explicit so operators don't conflate them. [CITED: langfuse.com/self-hosting/configuration]

### Pattern 3: DSN-gated, loud-skip schema-assertion test (mirror `pg_dsn` shape)
**What:** A new test that depends on the existing `pg_dsn` fixture (which already applies migrations + loud-skips on unset DSN) and asserts the post-migration schema contains the 0003 columns and 0004 tables, plus a trivial reachability assertion.
**When to use:** For LDATA-03 — the genuinely-new deliverable.
**Example (introspect the live schema via `information_schema`):**
```python
# tests/test_local_data_plane.py  (NEW — test-code only, zero src change)
import psycopg

def test_migrated_schema_has_0003_and_0004_objects(pg_dsn):  # pg_dsn applies 0001->0004 + loud-skips
    with psycopg.connect(pg_dsn) as conn:
        # 0003: additive tool_calls columns
        cols = {r[0] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'tool_calls'"
        ).fetchall()}
        assert {"integration_style", "schema_validation", "is_read"} <= cols
        # 0004: new tables
        tabs = {r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        ).fetchall()}
        assert {"self_improvement_active_version", "ai_bom_snapshots"} <= tabs
        # reachability
        assert conn.execute("SELECT 1").fetchone()[0] == 1
```
*Wire this test file into the `test-pg` target alongside the existing two files (see Pitfall 3), or confirm it is collected under `-m "not live"`. Planner picks the precise assertion set per CONTEXT discretion.*

### Anti-Patterns to Avoid
- **Editing `src/`** to add an env-driven config-path/seam or to apply migrations from the app — forbidden by the milestone zero-src guardrail. `settings.py` is already env-driven; only `.env.example`, `Makefile`, `RUNBOOK.md`, and `tests/` change.
- **Wiring `run-pg` into `make test`/CI** — it is operator-only and best-effort, exactly like `run-vllm`/`run-ollama`.
- **Adding a `make run-langfuse` standup target** — D-02 forbids it; would duplicate Phase 10's compose pin.
- **Changing the migration DSN/port without changing the matching `.env.example` default** — D-01↔D-04 must stay in lockstep (creds `postgres:postgres`, port 5432, db `agent_mesh`).
- **Switching `_apply_migrations` from the explicit tuple to a directory glob without flagging intent** — see Open Questions Q1; a glob silently changes behavior for a future `0005`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Applying SQL migrations in tests | A new migration runner | The existing `conftest.py:_apply_migrations` (already applies 0001→0004) | It already loops the tuple in order, strips comments, splits on `;`, and is the established external applier. CONTEXT says reuse it. |
| DSN loud-skip gating | A new skip helper | The existing `pg_dsn` fixture | Already skips on unset `TEST_DATABASE_URL` and returns the migrated, truncated DSN. New test just depends on it. |
| A local pgvector Postgres | A custom Dockerfile | `pgvector/pgvector:pg16` | Official image with `vector` pre-built; vanilla `postgres` fails `CREATE EXTENSION vector`. |
| A self-hosted Langfuse stack | A hand-written compose | Upstream `langfuse` repo `docker compose` (documented, not run) | v3 needs web+worker+postgres+clickhouse+redis+minio; pinning our own duplicates Phase 10. Document the upstream path. |
| A durable-lane test runner | A new pytest invocation | The existing `make test-pg` target | Already the DSN-gated, CI-excluded durable lane; add the new test file to it. |

**Key insight:** Almost everything LDATA-01/02/03 needs already exists in the repo (env-driven settings, the migration applier, the loud-skip fixture, the `test-pg` lane, the pgvector image reference). Phase 9 is overwhelmingly **wiring + documentation + one assertion test**, not new infrastructure.

## Runtime State Inventory

This is a config/docs/test phase (zero `src/` change), but the durable lane it wires touches stored data and an external service. Inventory:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Local pgvector Postgres holds the mesh schema (tasks/sessions/tool_calls/etc. from 0001-0004) + LangGraph checkpoint tables. A persistent named volume (`agent_mesh_pgdata`) survives container restarts. | None for P9 beyond documenting teardown (`docker rm -f` + optional `docker volume rm`). No data migration — fresh local DB. |
| Live service config | Self-hosted Langfuse v3 stores its own state in its own Postgres+ClickHouse+MinIO (NOT the mesh DB). The mesh's `LANGFUSE_PUBLIC_KEY`/`SECRET_KEY` are generated in the Langfuse UI and live in the operator's `.env`, not in git. | Document in RUNBOOK that keys are UI-generated and `.env`-sourced; standup deferred to P10. |
| OS-registered state | None — no Task Scheduler / launchd / systemd / pm2 registration involved. | None (verified — phase only adds make targets + docs + a test). |
| Secrets/env vars | `.env.example` gains pinned LOCAL defaults for `DATABASE_URL`/`TEST_DATABASE_URL` and `LANGFUSE_HOST`; `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` remain blank placeholders (UI-generated). Env NAMES are unchanged — `settings.py` reads them as-is, no `src/` edit. | Pin dev-only defaults; disclose they are dev-only in RUNBOOK. |
| Build artifacts | None — no package rename, no egg-info/binary churn. | None (verified). |

**The canonical question — after files are updated, what runtime systems still hold old state?** Nothing in P9 renames or migrates existing state. The only durable state is a fresh local DB the operator stands up; the Langfuse keys are operator-supplied at runtime. No stale cached/registered strings exist to reconcile.

## Common Pitfalls

### Pitfall 1: Vanilla `postgres` image fails `CREATE EXTENSION vector`
**What goes wrong:** Using `postgres:16` instead of `pgvector/pgvector:pg16` makes migration `0001` fail at `CREATE EXTENSION IF NOT EXISTS vector` (the `IF NOT EXISTS` does NOT install the extension — it only no-ops if already present).
**Why it happens:** The `vector` extension must be compiled into the image; the official postgres image doesn't ship it.
**How to avoid:** Pin `pgvector/pgvector:pg16` in `make run-pg` and `.env.example`/RUNBOOK. The codebase already warns about this (`conftest.py:_apply_migrations` docstring; `RUNBOOK.md:82-84`).
**Warning signs:** `ERROR: extension "vector" is not available` on first `make test-pg`.

### Pitfall 2: DSN/container-cred drift between D-01 and D-04
**What goes wrong:** `make run-pg` uses different user/password/db/port than the pinned `DATABASE_URL`/`TEST_DATABASE_URL`, so `make test-pg` can't connect.
**Why it happens:** The container env and the DSN string are set in two different files.
**How to avoid:** Make `run-pg` use exactly `POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres POSTGRES_DB=agent_mesh -p 5432:5432`, matching `postgresql://postgres:postgres@localhost:5432/agent_mesh`. Add a one-line RUNBOOK note tying them together.
**Warning signs:** `password authentication failed` / `database "agent_mesh" does not exist` / connection refused.

### Pitfall 3: New schema test not actually collected by `test-pg`
**What goes wrong:** The existing `test-pg` target names two explicit files (`tests/e2e/test_e2e_mcp_durable_job_live.py tests/test_checkpointer_resume.py`). A new test file in `tests/` is run by `make test` (which loud-skips on unset DSN) but is NOT in the explicit `test-pg` file list — so the LDATA-03 deliverable might not run under the named durable lane.
**Why it happens:** `test-pg` passes explicit file paths, not a marker selecting all DSN-gated tests.
**How to avoid:** Either (a) add the new test file to the `test-pg` target's file list (recommended, keeps the lane explicit and the existing contract intact), or (b) confirm the new test is collected and loud-skips correctly under `make test`. Per CONTEXT, keep the existing `test-pg` contract intact — option (a) extends it without breaking it.
**Warning signs:** `make test-pg` passes but never exercises the new assertion (it lives in `test`'s default collection only).

### Pitfall 4: Conflating Langfuse server secrets with client API keys
**What goes wrong:** RUNBOOK tells operators to set `LANGFUSE_PUBLIC_KEY`/`SECRET_KEY` as server env vars; they're actually UI-generated per-project client keys. Server-side needs `NEXTAUTH_SECRET`/`SALT`/`ENCRYPTION_KEY`/`DATABASE_URL`/ClickHouse/Redis/S3.
**Why it happens:** Both are "Langfuse env vars," but they live on opposite sides of the boundary.
**How to avoid:** RUNBOOK explicitly states: (1) server secrets are set in the upstream compose's `# CHANGEME` lines (Phase 10 territory), (2) the mesh's `LANGFUSE_PUBLIC_KEY`/`SECRET_KEY` are created in the UI after first boot and exported into the operator's `.env`. [CITED: langfuse.com/self-hosting/configuration]
**Warning signs:** Operator can't find where to "set" the public/secret key in the compose file.

### Pitfall 5: `git status` noise from `.env`-style local activation
**What goes wrong:** N/A here for config-swap (unlike Phase 8's `model_gateway.config.yaml`), but pinning defaults into the TRACKED `.env.example` is correct; operators copy to an untracked `.env`. Do NOT pin secrets into `.env.example`.
**How to avoid:** Only pin NON-secret local dev defaults (DSN with dev creds, host, image) into `.env.example`; keep `LANGFUSE_PUBLIC_KEY`/`SECRET_KEY` blank. Disclose dev-only nature in RUNBOOK.

## Code Examples

### Existing migration applier (reference — already applies all four)
```python
# tests/conftest.py (CURRENT STATE, 2026-06-10) — already 0001->0004
_MIGRATIONS = (
    "0001_init.sql",
    "0002_self_improvement.sql",
    "0003_tool_call_fields.sql",
    "0004_active_version.sql",
)
# _apply_migrations loops _MIGRATIONS in order, strips `--` comments via
# re.sub(r"(?m)--.*$", "", raw), then splits the comment-free text on ';'.
```

### Existing `pg_dsn` loud-skip fixture (reference — reuse, don't rebuild)
```python
@pytest.fixture
def pg_dsn() -> str:
    dsn = os.getenv("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL unset; SQL-backed tests require a local Postgres")
    _apply_migrations(dsn)   # applies 0001->0004
    _truncate(dsn)
    return dsn
```

### Existing `.env.example` lines to pin defaults into
```bash
# CURRENT (blank / cloud):
DATABASE_URL=                                   # L13 — pin local default
LANGFUSE_HOST=https://cloud.langfuse.com        # L27 — pin http://localhost:3000 (local)
LANGFUSE_PUBLIC_KEY=                            # L44 — leave blank (UI-generated)
LANGFUSE_SECRET_KEY=                            # L45 — leave blank (UI-generated)
# NOTE: TEST_DATABASE_URL has no current line in .env.example — add one.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Langfuse v2 self-host (lighter: web + postgres) | Langfuse v3 self-host (web + worker + postgres + clickhouse + redis/valkey + minio) | v3 GA (2024–2025 line) | The full standup is heavier — exactly why D-02 defers it to Phase 10 and P9 only documents the path. [CITED: langfuse.com/self-hosting/docker-compose — header marks v3, links a v2→v3 upgrade guide] |
| `ankane/pgvector` image | `pgvector/pgvector:pg<NN>` official namespace | image renamed/migrated | Use `pgvector/pgvector:pg16` (already pinned in-repo). |

**Deprecated/outdated:**
- D-03's premise that `_apply_migrations` applies "only 0001/0002" — outdated as of commit `9011377` (2026-06-07). See Open Questions Q1.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `pgvector/pgvector:pg16` is the current correct image tag for Postgres-16 + pgvector | Standard Stack | Low — corroborated by in-repo usage (conftest + RUNBOOK both rely on it) and Docker Hub; if the tag moved, the existing durable lane would already be broken. |
| A2 | Langfuse self-host UI default port is 3000 | Langfuse pattern / D-04 | Low — confirmed by official docs ("Open `http://localhost:3000`"); could change in a future major, hence "verified 2026-06-10, may drift." |
| A3 | Langfuse PUBLIC/SECRET keys are UI-generated (not server env) | Pitfall 4 / Pattern 2 | Low-Medium — confirmed by configuration docs not listing them as server env vars; if upstream adds env-seeded keys, the RUNBOOK note would be incomplete but not wrong. |
| A4 | A future `0005` migration is not in scope (so tuple-vs-glob is a latent, not active, concern) | Open Questions Q1 | Low — no 0005 exists today; flagged for planner intent only. |

## Open Questions (RESOLVED — carried into 09-01-PLAN.md)

1. **[RESOLVED — 09-01 objective + Task 2] D-03 premise is stale — what does "apply all migrations in lexical order" actually require now?** (HIGHEST PRIORITY for the planner.) → Plan keeps applier behavior untouched (explicit tuple, no glob); the only conftest change is the stale L37 docstring; the new schema-assertion test is the LDATA-03 deliverable.
   - **What we know:** `_apply_migrations` already iterates a hardcoded 4-tuple `0001`→`0004` in order; `_truncate` already lists the 0003/0004 tables; committed `9011377` (2026-06-07), before CONTEXT was gathered (2026-06-10). The contract/repository layers already assert the 0003/0004 objects (`tests/test_tool_call_contract.py`, `tests/test_read_path.py`), but **no test asserts they exist in the migrated DB schema (DDL layer).**
   - **What's unclear:** Does D-03 intend (a) merely "0003/0004 must be applied + schema-asserted" — **already applied; only the schema-assertion test is new**, OR (b) future-proof the applier to a **directory glob** so a future `0005` auto-applies (a behavior change the tuple does not currently have)?
   - **Recommendation:** Treat applier-completeness as DONE for 0003/0004; ship the NEW schema-assertion test as the LDATA-03 deliverable. Flag the glob-vs-tuple intent to the planner/discuss-phase — do NOT silently swap the tuple for a glob (it changes the documented invariant and could pick up non-migration `.sql` files). If glob is desired, the conftest comment-strip/`;`-split invariant must be re-verified against any future file, but that is forward-looking.

2. **[RESOLVED — 09-01 Task 1 Edit 3 + key_link] Where exactly does the new test wire into `test-pg`?**
   - **What we know:** `test-pg` names two explicit files; the new test must run under the named durable lane to satisfy LDATA-03's "`make test-pg` against the local DSN."
   - **Recommendation:** Add the new test file to the `test-pg` file list (keeps the lane explicit; preserves the existing contract). Confirm it loud-skips cleanly under plain `make test` too (it will, via `pg_dsn`).

3. **[RESOLVED — 09-01 Task 1 action] `run-pg` lifecycle flags (discretion):** persistent `-d` + named volume (recommended, so `test-pg` can re-run and data survives) vs `--rm` ephemeral. Document teardown either way.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | `make run-pg` (operator) | not probed (research env) | — | Best-effort target; documented to fail acceptably without Docker, exactly like P8 `run-vllm`/`run-ollama`. Operator may point `TEST_DATABASE_URL` at any pgvector Postgres. |
| `psycopg` | `_apply_migrations` + new test | ✓ (existing test dep) | existing pin | — |
| `pgvector/pgvector:pg16` image | local DB | pulled on demand by `run-pg` | `pg16` | Any pgvector-enabled Postgres reachable at the DSN. |
| Self-hosted Langfuse | LDATA-02 (documented only) | n/a (P9 doesn't run it) | v3 | Cloud Langfuse or telemetry loud-skip when keys unset (existing behavior). |

**Missing dependencies with no fallback:** None — every external dependency is either operator-best-effort (Docker) or documentation-only (Langfuse standup → Phase 10).
**Missing dependencies with fallback:** Docker absence → `make run-pg` fails acceptably; operator supplies any pgvector DSN. Langfuse absence → telemetry loud-skips (no behavior change).

## Sources

### Primary (HIGH confidence)
- Codebase (verified by direct read, 2026-06-10): `tests/conftest.py` (`_MIGRATIONS` 4-tuple, `_apply_migrations`, `_truncate`, `pg_dsn`), `migrations/0001`-`0004`, `Makefile` (`test-pg` L47-49, `test-live` L40-41, `run-*`/`use-*` L70-95), `.env.example`, `src/agent_mesh/settings.py` (env names), `RUNBOOK.md` (durable lane L72-94, local inference L96-160), `tests/test_checkpointer_resume.py`, `tests/e2e/test_e2e_mcp_durable_job_live.py`.
- `git log` (verified): commit `9011377` (2026-06-07) added 0004 to the conftest tuple, three days before CONTEXT (2026-06-10) — proving D-03's premise stale.
- `grep` (verified): 0003/0004 objects asserted only at contract (`test_tool_call_contract.py`) and repository (`test_read_path.py`) layers — NOT at the migrated-DDL layer.

### Secondary (MEDIUM confidence — datable, may drift)
- langfuse.com/self-hosting/docker-compose (fetched 2026-06-10) — `git clone` + `docker compose up`; UI at `http://localhost:3000`; v3; services include web/worker/postgres/clickhouse/redis-valkey/minio.
- langfuse.com/self-hosting/configuration (fetched 2026-06-10) — server secrets (`NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY`), `DATABASE_URL`, ClickHouse/Redis/S3 vars; public/secret API keys are UI-generated, not server env.

### Tertiary (LOW confidence)
- hub.docker.com/r/pgvector/pgvector `pg16` tag — corroborated by in-repo reliance; not independently re-fetched this session.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all artifacts already present/relied-upon in the repo; no new packages.
- Architecture / patterns: HIGH — mirror the existing Phase 8 run-target + loud-skip-fixture patterns verbatim.
- Pitfalls: HIGH — drawn from in-repo warnings + the verified D-03 discrepancy.
- Langfuse self-host facts: MEDIUM — official docs fetched today; v3 stack is drift-prone, marked datable.

**Research date:** 2026-06-10
**Valid until:** ~2026-07-10 for codebase facts (stable); ~2026-06-24 for Langfuse self-host facts (fast-moving — re-verify port/services before Phase 10).
