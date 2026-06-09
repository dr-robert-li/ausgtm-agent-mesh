# Phase 9: Local Data & Telemetry Plane - Pattern Map

**Mapped:** 2026-06-10
**Files analyzed:** 5 (4 modified, 1 new) — config/Makefile/docs/tests ONLY, ZERO `src/` change
**Analogs found:** 5 / 5 (4 in-repo exact/role analogs, 1 role-match riding an existing fixture)

> **Milestone guardrail (carried from Phase 8, do not regress):** config/Makefile/docs/tests
> only. The planner MUST be able to assert `git diff <base>..HEAD -- src/` is empty. `settings.py`
> already reads `DATABASE_URL` + `LANGFUSE_*`; local wiring is env defaults + operator run-paths +
> docs + one test. NO `src/` edit is needed or permitted.

> **D-03 reconciliation (highest-priority planner note):** CONTEXT D-03's premise that
> `_apply_migrations` "currently applies only 0001/0002" is **factually stale** (RESEARCH Q1;
> committed `9011377`, 2026-06-07). The `_MIGRATIONS` tuple already lists 0001→0004 and `_truncate`
> already covers the 0003/0004 tables. **Applier-completeness is already DONE.** The only stale
> artifact in conftest is the **docstring** (L37 says "Apply 0001/0002"). The genuinely-new LDATA-03
> deliverable is a **DDL-level schema-assertion test** — no existing test asserts the 0003/0004
> objects exist in the migrated Postgres schema (only at the Pydantic-contract + repository layers).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `Makefile` | config / operator tooling | batch (operator-run) | `Makefile` `run-vllm`/`run-ollama` block (L70-84) + `test-pg` (L47-49) | exact (same file, mirror existing target) |
| `RUNBOOK.md` | docs | n/a | `RUNBOOK.md` "Local inference lane" section (L96-163) + "Postgres durable checkpointer lane" (L72-94) | exact (same file, mirror prior section) |
| `.env.example` | config | n/a | `.env.example` existing `DATABASE_URL` (L13), `LANGFUSE_HOST` (L27) keys | exact (pin defaults into existing keys; +1 new line) |
| `tests/conftest.py` | test fixture | n/a | `tests/conftest.py` itself — `_MIGRATIONS`/`_apply_migrations`/`pg_dsn` (L8-87) | exact (reconcile docstring only) |
| `tests/test_local_data_plane.py` (NEW) | test | request-response (DB introspection) | `pg_dsn` fixture (conftest L74-87) + skip-gating shape of `tests/test_checkpointer_resume.py` | role-match (no existing `information_schema` test) |

## Pattern Assignments

### `Makefile` (config / operator tooling, batch) — THREE edits

**Analog:** `Makefile` `run-vllm`/`run-ollama` best-effort block (L70-84) and the `test-pg` lane (L47-49).

This is **three discrete edits**, not one. "Keep the `test-pg` contract intact" means *extend the
file list, do not restructure the lane* — it does NOT mean "don't touch test-pg" (RESEARCH Pitfall 3).

**Edit 1 — add `run-pg` to `.PHONY`** (L1). The line currently ends `... use-vllm use-ollama use-cloud`.
Add `run-pg` (and any DB-apply alias the planner chooses, e.g. nothing extra per D-01 — a single target).

**Edit 2 — add the `run-pg` target**, modeling the existing best-effort run-target block verbatim
(comment header stating best-effort/operator-only/never-CI; `?=` overridable vars; single `docker run`).
Existing analog to copy structure + comment tone from (L70-84):
```makefile
# --- Local inference lane (LOCAL-01/02/03) -----------------------------------
# run-vllm / run-ollama actually start a local backend. They are best-effort,
# operator-run, and DELIBERATELY never wired into `test` or any CI path (D-07):
# they require a GPU (vLLM) / an installed Ollama and may fail on a box without
# them, which is acceptable and documented in RUNBOOK.md.
...
VLLM_MODEL ?= Qwen/Qwen2.5-7B-Instruct
run-vllm:
	vllm serve $(VLLM_MODEL) --port 8000 --enable-auto-tool-choice --tool-call-parser hermes
```
New `run-pg` target (RESEARCH Pattern 1; exact flags — `-d`/`--rm`, healthcheck, volume name —
are planner discretion per CONTEXT, but creds/port/db are LOCKED to match D-04):
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
Also add a `help:` line for `run-pg` mirroring the existing run-target help entries (L20-21).

**Edit 3 — extend the `test-pg` file list** so the NEW LDATA-03 test runs under its named lane
(RESEARCH Pitfall 3 — without this, `make test-pg` passes but never exercises the new assertion).
Current target (L47-49):
```makefile
test-pg:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m pytest -q -m "not live" \
		tests/e2e/test_e2e_mcp_durable_job_live.py tests/test_checkpointer_resume.py
```
Append the new file to the explicit list (keeps the lane explicit; preserves the contract):
```makefile
test-pg:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m pytest -q -m "not live" \
		tests/e2e/test_e2e_mcp_durable_job_live.py tests/test_checkpointer_resume.py \
		tests/test_local_data_plane.py
```

**Anti-patterns:** do NOT wire `run-pg` into `make test`/CI; do NOT add a `make run-langfuse` target
(D-02 forbids it); do NOT change `run-pg` creds/port without changing the matching `.env.example`
default in lockstep (D-01 ↔ D-04).

---

### `RUNBOOK.md` (docs) — new "Local data & telemetry plane" section

**Analog:** the "Local inference lane" section (L96-163) for structure/honesty tone, and the
existing "Postgres durable checkpointer lane" section (L72-94) for the DSN/`test-pg`/pgvector facts.

**Insertion point:** after the Phase 8 "Local inference lane" section (ends ~L163), as a new
top-level `## Local data & telemetry plane` section.

**Honest-disclosure pattern to mirror** (from the inference lane, L111-117 / L132-137): state plainly
that `run-pg` is best-effort + operator-only + never CI, that it fails acceptably without Docker, and
that the pinned `.env.example` defaults are **dev-only** local creds.

**pgvector-image fact to carry** (already stated at L82-84 — keep consistent, do not contradict):
> a vanilla `postgres` image will fail the `CREATE EXTENSION vector` migration — use `pgvector/pgvector:pg16`.

**Copy-paste operator block** tying `run-pg` ↔ `make test-pg` ↔ the pinned DSN (model on L86-89):
```bash
make run-pg                                   # single local pgvector Postgres (best-effort, operator-only)
export TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/agent_mesh
make test-pg                                  # DSN-gated durable lane; loud-skips when unset
# teardown: docker rm -f agent_mesh_pg   (optional: docker volume rm agent_mesh_pgdata)
```

**Langfuse documentation-only subsection** (D-02 / RESEARCH Pattern 2 — document the path, ship NO
standup target). Two things to make explicit:
1. Upstream self-host path (datable, MEDIUM confidence — re-verify before P10):
   `git clone https://github.com/langfuse/langfuse.git && cd langfuse && docker compose up`,
   UI at `http://localhost:3000`, v3 stack (web+worker+postgres+clickhouse+redis/valkey+minio).
2. **Client-vs-server key boundary** (RESEARCH Pitfall 4 — do not conflate): the mesh's
   `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` are **UI-generated per-project** keys the operator
   creates after first boot and exports into their `.env`; they are NOT server env vars. Server-side
   secrets (`NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY`, `DATABASE_URL`, ClickHouse/Redis/S3) live in
   the upstream compose `# CHANGEME` lines and are **Phase 10 territory**. Telemetry **loud-skips**
   when keys are unset (existing behavior — no `src/` change). Full multi-container standup is
   **deferred to Phase 10's compose**.

**Anti-pattern:** do NOT document a `make run-langfuse` target — it does not exist and D-02 forbids it.

---

### `.env.example` (config) — pin local defaults into existing keys (+1 new line)

**Analog:** the file's own existing key block (L4-45).

Current relevant lines:
```bash
DATABASE_URL=                                   # L13 — blank
LANGFUSE_HOST=https://cloud.langfuse.com        # L27 — cloud default
LANGFUSE_PUBLIC_KEY=                            # L44 — blank (keep blank)
LANGFUSE_SECRET_KEY=                            # L45 — blank (keep blank)
```

Edits (D-04 — concrete copy-paste dev-only local defaults; creds/port/db LOCKED to the `run-pg`
container so `make test-pg` works out-of-box):
- **L13 (edit existing key):** `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/agent_mesh`
- **NEW line adjacent to L13:** `TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/agent_mesh`
  — `TEST_DATABASE_URL` has **no current line** in `.env.example`; it must be ADDED (RESEARCH §Code
  Examples NOTE). Add a one-line comment that it is the DSN-gated `make test-pg` lane var.
- **L27 (edit existing key):** `LANGFUSE_HOST=http://localhost:3000` (self-host default; the existing
  cloud value moves to a comment or RUNBOOK note).
- **L44/L45 (leave BLANK):** `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` stay blank — UI-generated
  per-project (RESEARCH Pitfall 4/5). **Do NOT pin secrets into the tracked `.env.example`.**

Disclose in a comment (and RUNBOOK) that these are **dev-only local defaults**; operators copy
`.env.example` → untracked `.env`.

---

### `tests/conftest.py` (test fixture) — RECONCILE docstring only, NO applier change

**Analog:** the file itself. **This is a docstring fix, not a functional change.**

The `_MIGRATIONS` tuple already applies all four (L8-13) and `_truncate` already lists the 0003/0004
tables (L14-27). The only stale artifact is the **`_apply_migrations` docstring (L37)**:
```python
def _apply_migrations(dsn: str) -> None:
    """Apply 0001/0002 to the test DB. ...   # <- STALE: applier actually applies 0001->0004
```
Edit the docstring to say it applies all migrations in `_MIGRATIONS` (0001→0004) in lexical order.
Do not touch the loop body, the comment-strip regex, or the `;`-split logic.

**LOCKED invariant to preserve** (conftest L52-60 + 0004 header L10-12): migrations are plain
comment-free DDL split on `;` — no dollar-quoted bodies (`DO $$ ... $$`) and no `--`/`;` inside string
literals. Keep this invariant if anything is generalized.

**Planner decision — tuple vs. glob (RESEARCH Q1, default = leave the tuple):** D-03 says "apply all
migrations in `migrations/` in lexical order." That is *already true* via the explicit 4-tuple. Do
**NOT** silently swap the tuple for a directory glob: a glob is a behavior change — it would
auto-apply a future `0005`, risk picking up non-migration `.sql` files, and could break the
comment-strip/`;`-split invariant. Flag glob-vs-tuple as an explicit planner choice; recommended
default is to **keep the explicit tuple** and only fix the docstring.

---

### `tests/test_local_data_plane.py` (NEW test) — DSN-gated DDL schema-assertion

**Analog:** the `pg_dsn` loud-skip fixture (conftest L74-87) for gating; the skip-gating *shape* of
`tests/test_checkpointer_resume.py` (DSN-gated Postgres path that skips cleanly when the backend/DSN
is absent). **Match quality = role-match:** there is no existing `information_schema` introspection
test in the repo — the introspection body comes from RESEARCH Pattern 3, not a repo analog.

**Gate (reuse, do not rebuild):** depend on the `pg_dsn` fixture — it already loud-skips on unset
`TEST_DATABASE_URL`, applies 0001→0004, and truncates. The new test adds NO new skip helper.
```python
@pytest.fixture
def pg_dsn() -> str:                       # conftest L74-87 — REUSE
    dsn = os.getenv("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL unset; SQL-backed tests require a local Postgres")
    _apply_migrations(dsn)                 # applies 0001->0004
    _truncate(dsn)
    return dsn
```

**Schema assertions — GROUND-TRUTH (read from the actual migrations, not RESEARCH's guess):**
- **0003** (`migrations/0003_tool_call_fields.sql` L19-21) adds three columns to `tool_calls`:
  `integration_style`, `schema_validation`, `is_read`.
- **0004** (`migrations/0004_active_version.sql` L20-45) creates two tables:
  `self_improvement_active_version`, `ai_bom_snapshots`.

Test body (introspect the LIVE migrated schema via `information_schema`; planner picks the precise
assertion set per CONTEXT discretion, but these objects are confirmed present):
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
**Wiring:** add this file to the `test-pg` target file list (see Makefile Edit 3) so it runs under the
named durable lane. It also collects under plain `make test` and loud-skips there via `pg_dsn`.

## Shared Patterns

### Best-effort operator run-target (out of CI, RUNBOOK-documented)
**Source:** `Makefile` L70-84 (`run-vllm`/`run-ollama`).
**Apply to:** the new `make run-pg` target.
Pattern = comment header declaring best-effort/operator-only/never-CI; `?=` overridable vars; a single
real command (`docker run …`); a `help:` entry; never referenced by `test`/CI. `run-pg` fails
acceptably on a box without Docker — exactly like `run-vllm` without a GPU.

### DSN loud-skip gating (never silent, never hard-fail)
**Source:** `tests/conftest.py` `pg_dsn` fixture (L74-87).
**Apply to:** the new LDATA-03 test (depend on `pg_dsn`).
`pytest.skip("TEST_DATABASE_URL unset; …")` on unset env keeps `make test` dependency-free while the
SQL-backed test runs against a local pgvector Postgres when the DSN is exported. Same shape as
`live_creds`/`agents_stack` skip fixtures.

### Honest dev-only disclosure in RUNBOOK
**Source:** `RUNBOOK.md` "Local inference lane" L111-117, L132-137.
**Apply to:** the new "Local data & telemetry plane" section.
State plainly: best-effort targets, dev-only local creds, and exactly what is deferred to Phase 10
(the multi-service compose + Langfuse multi-container standup). No overclaiming.

### pgvector image pin (vanilla postgres fails)
**Source:** `RUNBOOK.md` L82-84 + `conftest.py:_apply_migrations` docstring L40-42.
**Apply to:** `make run-pg`, `.env.example`, RUNBOOK.
Pin `pgvector/pgvector:pg16` everywhere — `CREATE EXTENSION vector` (migration 0001) fails on a
vanilla `postgres:16` image (`IF NOT EXISTS` does not install the extension).

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `tests/test_local_data_plane.py` (introspection body) | test | DB introspection | No existing test queries `information_schema` for migrated-DDL assertions; 0003/0004 objects are asserted only at the Pydantic-contract (`test_tool_call_contract.py`) and repository (`test_read_path.py`) layers. The fixture gating is a strong in-repo analog (`pg_dsn`); the introspection body is sourced from RESEARCH Pattern 3 + the ground-truth migration DDL. |

## Metadata

**Analog search scope:** `Makefile`, `tests/conftest.py`, `tests/test_checkpointer_resume.py`,
`.env.example`, `RUNBOOK.md` (L70-168), `migrations/0003_tool_call_fields.sql`,
`migrations/0004_active_version.sql`.
**Files scanned:** 7.
**Pattern extraction date:** 2026-06-10.
