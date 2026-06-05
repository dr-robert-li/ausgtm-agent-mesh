# Phase 1: Durable Core & Approval Security - Research

**Researched:** 2026-06-05
**Domain:** Postgres persistence (psycopg3), GCP Pub/Sub dispatch, HMAC-signed approval tokens — all for an explicitly synchronous Python POC
**Confidence:** HIGH (every recommendation is grounded in a real file/symbol in this repo; library versions verified against PyPI 2026-06-05)

## Summary

Phase 1 hardens the three load-bearing weaknesses of the scaffold: durability (in-memory singleton → Postgres), tenant isolation (unscoped reads), and the **critical** unauthenticated `/v1/approvals` write-gate bypass. The codebase is already structured for this — `Repository`, `Dispatcher` are `Protocol`s with in-memory/in-process fakes and a `DATABASE_URL`/`USE_PUBSUB` gating story in `settings.py`. The migrations (`0001_init.sql`, `0002_self_improvement.sql`) already define the exact target schema. Much of the Pub/Sub path (`PubSubDispatcher` publish + `worker/main.py` `_run_pubsub` consumer) already exists; DUR-03 is mostly *runtime wiring + local emulator validation*, not new construction.

The single most important non-obvious finding: **`RepositorySQL` is NOT a clean drop-in behind the current protocol.** Callers reach into the in-memory repo's *private dict state* — `runner.py:_pending_calls` does `getattr(self._repo, "_tool_calls", {})`, and `tests/test_approval_gating.py` + `tests/smoke.py` do `repo._approvals.keys()`. Against a SQL repo those attributes don't exist, so the resume-after-approval loop silently finds zero tool calls and completes the task **without executing the approved write** — defeating DUR-01's "resumes from durable record" criterion while tests still pass. The protocol must be *widened* (add `list_tool_calls`, `list_approvals`) and every private reach-in migrated, **before** RepositorySQL is implemented. This is cross-plan coupling that 01-01 must own first.

The codebase is **fully synchronous** (TaskService, Worker, sessions, the `Repository` protocol). Therefore RepositorySQL must use **sync psycopg3 + `psycopg_pool.ConnectionPool`** — not async. The async psycopg gotchas in project memory (`AsyncConnectionPool`, `AsyncPostgresSaver.setup()` + `autocommit=True`) belong to the **LangGraph checkpointer in Phase 2 (ORCH-02)**, not to this phase's repository. SEC-01 should mirror `slack_verify.py` exactly: stdlib `hmac`/`hashlib`/`compare_digest`, a stateless self-contained signed token — no PyJWT needed for a single-issuer/single-verifier deployment.

**Primary recommendation:** In 01-01, first widen the `Repository` protocol (tenant_id on `list_events`/`list_evaluations`; add `list_tool_calls`/`list_approvals`), migrate all private-state reach-ins in `runner.py`/tests/`smoke.py`, update `InMemoryRepository`, then implement `RepositorySQL` (sync psycopg3 `ConnectionPool`) selected by `DATABASE_URL` in `get_repository()`. 01-03 mirrors `slack_verify.py` with an HMAC approval token binding `approval_record_id|payload_hash|exp`, enforced at **both** `/v1/approvals` and the MCP `submit_approval` tool. 01-02 wires/validates the already-existing Pub/Sub path against the local emulator. Build order: **01-01 → 01-03** (SEC-02 resume tests sit on the resume path 01-01 fixes); **01-02 is independent**.

<user_constraints>
## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for this phase (standalone/integrated research run without a prior discuss-phase). Constraints below are extracted from the normative `./CLAUDE.md`, `.planning/REQUIREMENTS.md` "Out of Scope", and `.planning/ROADMAP.md`, and carry the same authority.

### Locked Decisions (from CLAUDE.md + REQUIREMENTS.md)
- **Durable stores stay in `australia-southeast1`.** Schema region is fixed; model/inference traffic may leave AU but Postgres does not.
- **No live GCP provisioning this milestone.** Validate locally only — local Postgres + Pub/Sub emulator. (REQUIREMENTS Out-of-Scope; DEP-03 is v2.)
- **Task contract stays Temporal-ready.** Do not introduce Temporal; keep the lifecycle/state machine clean so Temporal can slot in later (CLAUDE.md §3).
- **In-process dispatcher is RETAINED as the fallback** (DUR-03 wording), not replaced. `use_pubsub` gates Pub/Sub vs in-process.
- **Approval ledger stays mutable `approval_records`** for the POC. Immutable/hash-chained ledger is explicit production hardening (caveat §4) — OUT OF SCOPE here.
- **Mirrored ingress capabilities.** Slack, MCP, and API funnel into the same `TaskService` and the same shared approval ledger. SEC-01 must therefore cover **both** HTTP `/v1/approvals` and the MCP `submit_approval` tool.

### Claude's Discretion
- Token mechanism: HMAC stdlib token vs PyJWT vs itsdangerous (recommendation below: stdlib HMAC).
- psycopg connection-pool sizing, JSON column handling, upsert SQL style.
- Exact new protocol method names (`list_tool_calls` / `list_approvals` recommended).

### Deferred Ideas (OUT OF SCOPE — do not build in Phase 1)
- LangGraph Postgres checkpointer wiring (Phase 2 / ORCH-02). The async psycopg gotchas live here, not in this phase.
- Row-level security / schema-per-tenant / DB-per-tenant (production hardening §3). Phase 1 enforces tenancy at the *application read layer* via `tenant_id` params, per DUR-02 wording.
- Immutable approval ledger, append-only enforcement, hash chaining (§4).
- pgvector indexes, real SaaS adapters, Langfuse wiring, live LiteLLM gateway (Phases 3–4).
- Live cloud provisioning, FinOps review (v2 / DEP-03/04).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DUR-01 | Postgres-backed repository replaces the in-memory singleton; tasks/sessions/approvals/tool-calls survive a worker restart | `RepositorySQL` (sync psycopg3 `ConnectionPool`) mapped column-by-column to `0001`/`0002` tables (see Schema Mapping). Selected by `DATABASE_URL` in `get_repository()`. **Blocker dependency:** protocol must be widened + private reach-ins migrated first (Don't Hand-Roll #1). |
| DUR-02 | All repository read paths are tenant-scoped (`list_events`, `list_evaluations` require `tenant_id`); cross-tenant read returns nothing | Add `tenant_id` param to the two named methods in `Repository` protocol + `InMemoryRepository` + `RepositorySQL`. SQL `WHERE tenant_id = %s`. Cross-tenant test asserts empty list. |
| DUR-03 | Pub/Sub dispatch wired at runtime with in-process dispatcher retained as fallback | Publish (`PubSubDispatcher`) and consume (`worker/main.py:_run_pubsub`) **already exist**. Gap is runtime validation against the **Pub/Sub emulator** + subscription provisioning. See DUR-03 section. |
| SEC-01 | `/v1/approvals` verifies a signed approval token (HMAC/JWT) issued at request time; forged/self-asserted `approver_id` rejected | Mirror `slack_verify.py` (stdlib HMAC). Self-contained token `record_id|exp|sig` issued in `open_approval()`, verified at endpoint. Must cover MCP `submit_approval` too. See SEC-01 section. |
| SEC-02 | Replay + payload-mutation tests proving a mutated payload invalidates a prior approval and an approval cannot be reused across tasks | Three test cases mapped to three distinct defenses (token, existing `is_approved()` re-hash, endpoint auth). See SEC-02 section. Sits on the resume path 01-01 repairs → depends on 01-01. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Durable task/session/approval/tool-call persistence | Database / Storage (`RepositorySQL` → Cloud SQL Postgres) | Services layer (protocol) | Persistence belongs behind the `Repository` protocol; callers stay storage-agnostic. |
| Tenant isolation (read scoping) | Services layer (`Repository` protocol contract) | Database (WHERE clause) | DUR-02 enforces tenancy at the *application read layer* (RLS is deferred §3). The protocol contract is the right place to mandate it for both impls. |
| Task dispatch (ingress → worker) | API/Backend (publish) + Worker (consume) | Messaging (Pub/Sub / in-process) | `Dispatcher` protocol already separates publish from transport; `worker/main.py` owns the consumer loop. |
| Approval authentication (write-gate) | API/Backend (`/v1/approvals`, MCP tool) | Services (`approvals.py` token issue/verify) | The token must be verified at the *ingress boundary* before `record_decision` mutates the ledger. The signing logic lives in the services layer next to `payload_hash`. |
| Payload-mutation invariance | Services (`approvals.is_approved` re-hash at execution) | Worker (`runner.py:_resume_after_approval`) | Already enforced; SEC-02(a) tests the existing check, no new code. |

## Standard Stack

### Core

| Library | Version (verified) | Purpose | Why Standard |
|---------|--------------------|---------|--------------|
| `psycopg[binary]` | **3.3.4** (pyproject pins `>=3.1`) `[VERIFIED: PyPI 2026-06-05]` | Sync Postgres driver for `RepositorySQL` | Already the declared driver (`pyproject.toml` `runtime` extra, STACK.md). psycopg3 is the current generation; supports sync `connection`/`cursor` + native `dict`/`Jsonb` adaptation. |
| `psycopg-pool` | **3.3.1** `[VERIFIED: PyPI 2026-06-05]` | `ConnectionPool` for the repo | Companion package to psycopg3; provides the **sync** `ConnectionPool` (separate import from `psycopg`). Must be added to the `runtime` extra (currently absent — see Package Audit). |
| `google-cloud-pubsub` | **2.39.0** (pyproject pins `>=2.21`) `[VERIFIED: PyPI 2026-06-05]` | Pub/Sub publish + subscribe | Already declared and already used by `PubSubDispatcher` and `worker/main.py`. No version change needed. |
| stdlib `hmac` + `hashlib` + `secrets` | Python 3.11+ stdlib `[VERIFIED: codebase grep]` | HMAC-signed approval token (SEC-01) | Mirrors the *existing, tested* `slack_verify.py` pattern. Zero new dependency. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `PyJWT` | 2.13.0 `[VERIFIED: PyPI 2026-06-05]` `[ASSUMED suitability]` | JWT approval tokens (alternative to HMAC) | **Not recommended for Phase 1.** Only if a future multi-issuer/asymmetric story emerges. JWT adds a dependency and buys nothing for single-issuer=single-verifier. |
| `itsdangerous` | 2.2.0 `[VERIFIED: PyPI 2026-06-05]` `[ASSUMED suitability]` | Signed-token helper (`TimestampSigner`) | Library alternative to hand-rolled HMAC if the team prefers a battle-tested signer with built-in expiry. Still stdlib-HMAC under the hood; recommendation is stdlib for consistency with `slack_verify.py`. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| sync psycopg3 `ConnectionPool` | `asyncpg` / `AsyncConnectionPool` | **Rejected.** Every caller (`TaskService`, `Worker`, `sessions`, the protocol) is sync. Async would force rewriting all callers and the worker loop — out of scope, high risk. The async memory note is a Phase-2 checkpointer concern. |
| stdlib HMAC token | PyJWT | JWT is for multi-party/asymmetric trust. Here the mesh both issues and verifies → symmetric HMAC is simpler, dependency-free, and already proven in `slack_verify.py`. |
| App-layer `tenant_id` read scoping | Postgres Row-Level Security | RLS is the production answer (caveat §3) but is explicitly deferred. DUR-02's wording ("read paths require `tenant_id`") is an app-layer requirement. |

**Installation (add to `pyproject.toml` `runtime` extra):**
```bash
# psycopg-pool is a SEPARATE package from psycopg and is currently missing.
pip install "psycopg[binary]>=3.1" "psycopg-pool>=3.2" "google-cloud-pubsub>=2.21"
```

## Package Legitimacy Audit

> slopcheck was not available in this environment; all four packages are nonetheless either already declared in `pyproject.toml` (psycopg, google-cloud-pubsub) or are the canonical first-party companion (`psycopg-pool`, same maintainer/org as psycopg). Registry verification done via `pip index versions`.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `psycopg` | PyPI | mature (3.x since 2021) | very high | github.com/psycopg/psycopg | n/a (unavail) | Approved — already declared |
| `psycopg-pool` | PyPI | mature | high | github.com/psycopg/psycopg (same repo) | n/a | Approved — first-party companion |
| `google-cloud-pubsub` | PyPI | mature | very high | github.com/googleapis/python-pubsub | n/a | Approved — already declared |
| `PyJWT` | PyPI | mature | very high | github.com/jpadilla/pyjwt | n/a | Not adopted (HMAC chosen) |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none
**Note for planner:** since slopcheck was unavailable, the planner should treat `psycopg-pool` addition like any new dep — but it is the official companion to an already-trusted package; a `checkpoint:human-verify` is low-value here. The two already-declared packages need no gate.

## Architecture Patterns

### System Architecture Diagram (data flow for this phase)

```
                 Slack / API / MCP ingress
                          │  (TaskRequest)
                          ▼
                   TaskService.create_task        ── sync ──┐
                          │ persist BEFORE dispatch          │
                          ▼                                   │
        ┌──────── Repository (Protocol) ───────┐             │
        │  get_repository(): DATABASE_URL set? │             │
        │   ├─ yes → RepositorySQL (psycopg3   │   DUR-01    │
        │   │         ConnectionPool → Cloud   │   DUR-02    │
        │   │         SQL australia-southeast1)│             │
        │   └─ no  → InMemoryRepository (tests)│             │
        └──────────────────────────────────────┘             │
                          │ publish_task(task_id)             │
                          ▼                                   │
        ┌──────── Dispatcher (Protocol) ───────┐   DUR-03    │
        │  get_dispatcher(): use_pubsub?        │             │
        │   ├─ yes → PubSubDispatcher ─► Pub/Sub topic        │
        │   │         (emulator locally, port 8085)           │
        │   └─ no  → InProcessDispatcher (queue)              │
        └──────────────────────────────────────┘             │
                          │                                   │
                          ▼                                   │
            worker/main.py  ──► Worker.process(task_id) ◄─────┘
              _run_pubsub (pull+ack)   │ run_mesh → proposed writes?
              _run_inprocess (drain)   │
                                       ▼
                         ToolCall + open_approval (token issued)  SEC-01
                                       │ task → AWAITING_APPROVAL
                                       ▼
   ┌─────────── approval decision arrives ───────────┐
   │ POST /v1/approvals      (HTTP)  ── verify token │ SEC-01
   │ MCP submit_approval tool        ── verify token │ SEC-01 (MUST also gate)
   └─────────────────────────────────────────────────┘
                                       │ record_decision → APPROVED
                                       ▼ re-dispatch → Worker._resume_after_approval
                         is_approved(record, call.parameters)   SEC-02(a) re-hash
                         → execute write only if hash still matches
```

### Recommended Project Structure (files this phase touches/adds)

```
src/agent_mesh/
├── services/
│   ├── repository.py        # WIDEN protocol; add RepositorySQL; route get_repository on DATABASE_URL
│   ├── approvals.py         # ADD: issue_approval_token() + verify_approval_token()
│   ├── dispatch.py          # (no change needed; already gated on use_pubsub)
│   ├── task_service.py      # (no change; persists before dispatch already)
│   └── sessions.py          # SQL path: upsert sessions row (in-mem path unchanged)
├── api/
│   ├── app.py               # /v1/approvals: require + verify token before record_decision
│   └── mcp_server.py        # submit_approval tool: require + verify token (DO NOT MISS)
├── settings.py              # ADD: approval_signing_secret_env (mirror slack_signing_secret_env)
└── worker/
    ├── runner.py            # MIGRATE _pending_calls off repo._tool_calls → repo.list_tool_calls(...)
    └── main.py              # (already has _run_pubsub + _run_inprocess; validate only)
migrations/                  # 0001/0002 already define schema — no new migration needed
tests/
├── conftest.py             # ADD: optional pg fixture gated on TEST_DATABASE_URL (skip if unset)
├── test_approval_gating.py # MIGRATE repo._approvals reach-ins → repo.list_approvals(...)
├── test_repository_sql.py  # NEW: RepositorySQL round-trip + restart-survival + cross-tenant (DUR-01/02)
└── test_approval_security.py # NEW: SEC-01/SEC-02 token + replay + mutation + forged-POST
```

### Pattern 1: Protocol widening before SQL implementation (the linchpin)
**What:** Add the methods callers *actually* depend on to the `Repository` protocol, implement them in `InMemoryRepository`, migrate every private reach-in, THEN write `RepositorySQL`.
**When to use:** Always, in 01-01, before any SQL is written.
**Concrete changes:**
```python
# repository.py — add to Repository protocol:
def list_events(self, task_id: str, tenant_id: str) -> list[TaskEvent]: ...          # DUR-02: +tenant_id
def list_evaluations(self, proposal_id: str, tenant_id: str) -> list[EvaluationResult]: ...  # DUR-02
def list_tool_calls(self, task_id: str, tenant_id: str) -> list[ToolCall]: ...       # NEW: replaces runner reach-in
def list_approvals(self, task_id: str, tenant_id: str) -> list[ApprovalRecord]: ...  # NEW: replaces test reach-ins
```
```python
# runner.py:_pending_calls — BEFORE (breaks on RepositorySQL):
store = getattr(self._repo, "_tool_calls", {})
return [c for c in store.values() if c.task_id == task_id]
# AFTER:
return self._repo.list_tool_calls(task_id, task.tenant_id)   # task fetched in caller
```

### Pattern 2: Sync psycopg3 ConnectionPool repository
**What:** One module-level `ConnectionPool`; each method borrows a connection via `with self._pool.connection() as conn:` and uses `conn.execute(...)` / `cursor.fetchone()`. JSONB columns adapted with `psycopg.types.json.Jsonb`.
**Example:**
```python
# Source: psycopg3 official docs (psycopg.org/psycopg3/docs/api/pool.html) [CITED]
from psycopg_pool import ConnectionPool
from psycopg.types.json import Jsonb

class RepositorySQL:
    def __init__(self, dsn: str, *, min_size: int = 1, max_size: int = 8) -> None:
        # GOTCHA (see Pitfall 1): pass connection options via kwargs, NOT appended to the DSN string.
        self._pool = ConnectionPool(conninfo=dsn, min_size=min_size, max_size=max_size, open=True)

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT task_id, tenant_id, client_slug, entrypoint, session_id, "
                "requester, prompt, state, model_route_profile, result_summary, error, "
                "created_at, updated_at FROM tasks WHERE task_id = %s", (task_id,)
            ).fetchone()
        return _row_to_task(row) if row else None

    def create_task(self, task: TaskRecord) -> TaskRecord:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO tasks (task_id, tenant_id, client_slug, entrypoint, session_id, "
                "requester_id, requester, prompt, state, model_route_profile) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (task_id) DO UPDATE SET state=EXCLUDED.state, "
                "result_summary=EXCLUDED.result_summary, error=EXCLUDED.error, updated_at=now()",
                (task.task_id, task.tenant_id, task.client_slug, str(task.entrypoint),
                 task.session_id, task.requester.requester_id,
                 Jsonb(task.requester.model_dump(mode="json")), task.prompt,
                 str(task.state), task.model_route_profile),
            )
        return task
```
Note `requester_id` (TEXT) **and** `requester` (JSONB) are both written from the one `RequesterIdentity`.

### Pattern 3: Stateless HMAC approval token (SEC-01) — mirrors slack_verify.py
**What:** When `open_approval()` persists a pending record, also mint a token binding `approval_record_id`, `payload_hash`, and an expiry. The verifier at the endpoint recomputes the HMAC and re-loads the `ApprovalRecord` to confirm binding. No new storage.
**Example:**
```python
# Source: mirrors src/agent_mesh/api/slack_verify.py (stdlib hmac) [VERIFIED: codebase]
import hashlib, hmac, os, time

def issue_approval_token(record: ApprovalRecord, *, ttl_s: int = 3600, secret: str | None = None) -> str:
    secret = secret or os.getenv("APPROVAL_SIGNING_SECRET", "")
    exp = int(time.time()) + ttl_s
    msg = f"{record.approval_record_id}:{record.payload_hash}:{exp}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return f"{record.approval_record_id}.{exp}.{sig}"

def verify_approval_token(token: str, record: ApprovalRecord, *, secret: str | None = None) -> bool:
    secret = secret or os.getenv("APPROVAL_SIGNING_SECRET", "")
    if not secret:
        return True  # local dev parity with slack_verify (no secret → unverified, signalled)
    try:
        rid, exp_s, sig = token.split(".")
        exp = int(exp_s)
    except (ValueError, AttributeError):
        return False
    if rid != record.approval_record_id:          # SEC-02(b): bound to THIS record/task only
        return False
    if time.time() > exp:                          # expiry / replay window
        return False
    msg = f"{record.approval_record_id}:{record.payload_hash}:{exp}".encode()
    expected = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)      # constant-time, mirrors slack_verify
```
**Endpoint enforcement (`app.py` AND `mcp_server.py`):**
```python
# app.py /v1/approvals — verify BEFORE record_decision; reject self-asserted approver_id
record = _service.repo.get_approval(payload["approval_record_id"])
if record is None:
    raise HTTPException(404, "unknown approval")
if not verify_approval_token(payload.get("approval_token", ""), record):
    raise HTTPException(401, "invalid approval token")
# only now trust the decision
```

### Anti-Patterns to Avoid
- **Implementing `RepositorySQL` before widening the protocol.** Tests pass (they use InMemory) while production silently drops approved writes. ALWAYS widen + migrate reach-ins first.
- **Appending options to the DSN string** (`"postgres://... options=..."` with a space) → psycopg `ProgrammingError`. Use pool `kwargs`. (Pitfall 1.)
- **Trusting `approver_id` from the request body.** That is the exact existing bug. The token is the source of authority; `approver_id` is recorded, not trusted.
- **Forgetting the MCP `submit_approval` tool.** SEC-01 is NOT closed if only the HTTP endpoint is gated — both ingress paths share the ledger.
- **Reaching into `repo._approvals` / `repo._tool_calls` in new tests.** Use the new protocol list methods so tests run against both repos.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| **#1 RepositorySQL drop-in coupling** | A SQL repo that only implements the 18 declared protocol methods | Widen the protocol with `list_tool_calls`/`list_approvals` (+ tenant_id on the two list reads) and migrate `runner.py:_pending_calls`, `test_approval_gating.py`, `smoke.py` off private dict access FIRST | Callers depend on `repo._tool_calls` / `repo._approvals` which don't exist on SQL → silent loss of approved writes. **This is the #1 finding.** |
| Connection lifecycle | Manual `psycopg.connect()` per call + manual close | `psycopg_pool.ConnectionPool` (sync) | Pooling, reconnection, and thread-safety are solved; per-call connect is slow and leaks. |
| Signed token format | Custom serialization / encryption | stdlib `hmac` + `compare_digest` (mirror `slack_verify.py`) | Constant-time comparison and the exact pattern already proven & tested in this repo. |
| Pub/Sub publish/consume | New transport code | `PubSubDispatcher` + `worker/main.py:_run_pubsub` already exist | DUR-03 is wiring/validation, not construction. |
| Cross-tenant filtering at every call site | Ad-hoc per-caller filters | Mandate `tenant_id` in the protocol contract; both impls enforce in one place | Prevents the same tenant-leak bug propagating to SQL (CONCERNS.md §3). |

**Key insight:** The protocol is the contract that keeps the in-memory fake and the SQL impl interchangeable. Every behavior a caller relies on must be IN the protocol — including the ones currently smuggled through private attributes. Fix the contract first; the SQL impl then follows mechanically.

## Runtime State Inventory

> This phase swaps a persistence backend (in-memory → Postgres) but provisions no live cloud state (local validation only). Categories assessed:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None to migrate — in-memory store is ephemeral by definition; there is no existing durable data to carry over. New `RepositorySQL` starts empty against a fresh local Postgres. | None (greenfield data). |
| Live service config | None — no live GCP resources provisioned this milestone (REQUIREMENTS Out-of-Scope). Pub/Sub topics/subscriptions exist only against the **local emulator**, created per-run. | Create topic + `{task_topic}-worker` subscription against emulator in the test/smoke harness. |
| OS-registered state | None — no OS-level registrations; worker runs via `python -m agent_mesh.worker.main`. | None. |
| Secrets/env vars | NEW env var `APPROVAL_SIGNING_SECRET` (code reads it; mirrors `SLACK_SIGNING_SECRET`). `DATABASE_URL`, `USE_PUBSUB`, `TASK_SUBSCRIPTION`, `PUBSUB_EMULATOR_HOST` already referenced. Add `APPROVAL_SIGNING_SECRET` to `.env.example` and the deploy secret manifest. | Add new secret name to settings + `.env.example` + `scripts/gcp_deploy_core.sh --set-secrets` list (code rename only; no live key yet). |
| Build artifacts | None — pure-Python; no compiled artifacts or egg-info renames. Adding `psycopg-pool` to the `runtime` extra requires regenerating `requirements/worker.txt`/`requirements/api.txt` if those lockfiles are committed. | Regenerate the affected `requirements/*.txt` lockfiles. |

## Common Pitfalls

### Pitfall 1: psycopg DSN conninfo formatting bug (from project memory)
**What goes wrong:** Connection options appended to the DSN URL with a space (e.g. `postgres://host/db options=-c...`) raise a psycopg `ProgrammingError`.
**Why it happens:** psycopg parses the conninfo string strictly; trailing `options=` glued onto a URL is invalid.
**How to avoid:** Pass options via the pool/connection `kwargs`, e.g. `ConnectionPool(conninfo=dsn, kwargs={"options": "-c search_path=public"})`. Keep the DSN clean.
**Warning signs:** `ProgrammingError: invalid connection option` at pool open.

### Pitfall 2: `CREATE INDEX CONCURRENTLY` inside a transaction (from project memory) — SCOPE: Phase 2, surfaced here
**What goes wrong:** `AsyncPostgresSaver.setup()` (LangGraph checkpointer) fails with "CREATE INDEX CONCURRENTLY cannot run inside a transaction block."
**Why it happens:** The default pool connection is in a transaction; `CONCURRENTLY` requires autocommit.
**How to avoid:** Use `autocommit=True` on the pool used for checkpointer setup.
**Scope note:** This belongs to **Phase 2 / ORCH-02** (the LangGraph checkpointer), **not** to `RepositorySQL` in Phase 1. The migrations (`0001`/`0002`) are applied by `psql`/migration tooling, not by the repo, and use plain `CREATE INDEX` (no CONCURRENTLY). Surfaced so the planner does not accidentally pull async checkpointer setup into Phase 1.

### Pitfall 3: Silent drop of approved writes on the SQL repo
**What goes wrong:** `runner._pending_calls` returns `{}` on `RepositorySQL` (no `_tool_calls` attr) → resume completes the task without executing the approved write. Tests still pass (they use InMemory).
**Why it happens:** Caller depends on a private attribute, not the protocol.
**How to avoid:** Don't-Hand-Roll #1 — widen protocol + migrate reach-ins before SQL exists. Add a `RepositorySQL`-backed integration test (`test_repository_sql.py`) so the resume path is exercised against SQL, not just the fake.
**Warning signs:** Approval flow "completes" but the tool-call row stays `awaiting_approval`/`approved`, never `executed`.

### Pitfall 4: Forgetting the MCP approval path
**What goes wrong:** `/v1/approvals` is hardened but `mcp_server.py:submit_approval` still trusts a self-asserted `approver_id`.
**Why it happens:** Two ingress paths share one ledger; easy to gate only the HTTP one.
**How to avoid:** Add a `approval_token` parameter to the MCP `submit_approval` tool and run the same `verify_approval_token` before `record_decision`.
**Warning signs:** A forged-approval test passes for HTTP but a parallel MCP test still approves.

### Pitfall 5: `TaskRecord.metadata` has no `tasks` column
**What goes wrong:** `TaskRecord.metadata` (dict) is silently dropped on persist — `tasks` has no `metadata` column; the schema puts operational metadata in the separate `task_metadata` table.
**Why it happens:** Impedance mismatch between the Pydantic model and the normalized schema.
**How to avoid:** In `RepositorySQL.create_task`, either upsert non-empty `metadata` keys into `task_metadata` rows, or explicitly document the drop for the POC. Decide and state it; don't drop silently.
**Warning signs:** Round-trip test: create task with metadata, re-read, metadata is empty.

### Pitfall 6: `state` value coercion across the boundary
**What goes wrong:** Models use `ConfigDict(use_enum_values=True)` so `task.state` may already be a `str` value; the schema `tasks.state` is TEXT. Mixing `TaskState.RUNNING` and `"running"` in SQL params can write inconsistent values.
**How to avoid:** Always coerce with `str(task.state)` (works for both enum and str) on write; on read, the TEXT value re-validates into the enum via Pydantic. `assert_transition` already accepts `TaskState | str`.
**Warning signs:** `WHERE state = 'TaskState.RUNNING'` mismatches.

## DUR-03: Pub/Sub dispatch — already built, validate against emulator

`dispatch.py:PubSubDispatcher.publish_task` (publish) and `worker/main.py:_run_pubsub` (pull + `ack`/`nack` + DLQ-via-subscription) **already exist** and are gated on `settings.use_pubsub`. The in-process fallback (`InProcessDispatcher` + `_run_inprocess`) is retained. **DUR-03 is therefore runtime wiring + local validation, not new code.**

**Local validation via the Pub/Sub emulator (no live GCP):**
```bash
# Start emulator (gcloud SDK, no project billing):
gcloud beta emulators pubsub start --host-port=localhost:8085 --project=local-test
export PUBSUB_EMULATOR_HOST=localhost:8085
export USE_PUBSUB=true PROJECT_ID=local-test TASK_TOPIC=agent-mesh-tasks
# Create topic + worker subscription against the emulator (publisher/subscriber clients
# auto-honor PUBSUB_EMULATOR_HOST):
#   publisher.create_topic(name=topic_path)
#   subscriber.create_subscription(name="agent-mesh-tasks-worker", topic=topic_path)
```
**Recommended 01-02 work:** (1) a small idempotent emulator setup helper (create topic + `{task_topic}-worker` subscription, swallow `AlreadyExists`); (2) an integration test (skipped unless `PUBSUB_EMULATOR_HOST` is set) that publishes a task id and asserts the worker callback processes it; (3) confirm `_run_inprocess` still drains when `USE_PUBSUB` unset. **Temporal-ready note:** keep the dispatch contract (`publish_task(task_id)` + durable task record persisted before publish) unchanged so Temporal can replace Pub/Sub later without touching ingress.

**Confidence:** HIGH on the existing code; MEDIUM on exact emulator subscription-creation calls (verify against current `google-cloud-pubsub` admin API at implementation time — the `create_subscription` signature uses keyword args `name=`/`topic=` in 2.x).

## SEC-01 / SEC-02: token design + test map

### SEC-01 token (decided)
- **Mechanism:** stdlib HMAC-SHA256, self-contained `record_id.exp.sig` (Pattern 3). No PyJWT, no new storage.
- **Binding:** `approval_record_id` + `payload_hash` + `exp`. Binding to `approval_record_id` makes the token single-task (each approval record belongs to one task) → no cross-task replay (SEC-02b).
- **Issued:** inside `approvals.open_approval()` (or returned alongside it) when the approval request is opened — so the token travels with the approval prompt to Slack/MCP/API.
- **Secret:** new `APPROVAL_SIGNING_SECRET` env var; add `approval_signing_secret_env: str = "APPROVAL_SIGNING_SECRET"` to `Settings` mirroring `slack_signing_secret_env`. No-secret-set behavior mirrors `slack_verify` (returns True locally, signalled unverified) so smoke/tests run without secrets.
- **Channel delivery:**
  - **Slack:** token embedded in the interactive button `value`/action payload that calls back to `/v1/approvals` (the requester never types it).
  - **MCP:** token returned to the MCP client when the approval is opened; client passes it back into the `submit_approval` tool's new `approval_token` arg.
  - **API:** token returned in the create-approval response; caller echoes it in the `/v1/approvals` body as `approval_token`.

### SEC-02 test map — three cases, three distinct defenses

| Case | What it proves | Where the defense lives | New code? |
|------|----------------|--------------------------|-----------|
| (a) mutated payload invalidates a prior approval | Editing `ToolCall.parameters` after approval → `is_approved()` re-hash mismatch → write does NOT execute | **Existing** `approvals.is_approved` (`approvals.py:84-94`) + `runner.py:100` | No new logic — the test exercises the existing re-hash. |
| (b) approval cannot be replayed across tasks | A token/approval for task A cannot approve task B | **New** token binds `approval_record_id` (per-task); endpoint loads the record and checks `rid` match | New token verify. |
| (c) forged / unauthenticated POST rejected | POST to `/v1/approvals` (and MCP `submit_approval`) with no/invalid token → 401, no ledger mutation | **New** `verify_approval_token` at both ingress points | New endpoint guard. |

**Test file `tests/test_approval_security.py` (extends `test_approval_gating.py` patterns, uses `repo` fixture + FastAPI `TestClient`):**
1. `test_valid_token_accepted` — issue token, POST, decision recorded.
2. `test_forged_approver_id_rejected` — POST with spoofed `approver_id` and no token → 401 (the exact CONCERNS.md Critical #1).
3. `test_tampered_token_rejected` — flip a sig char → 401 (mirrors `test_tampered_body_rejected`).
4. `test_expired_token_rejected` — `ttl_s` in the past → 401.
5. `test_mutated_payload_invalidates_approval` — approve, then mutate `ToolCall.parameters`, resume → tool call NOT executed (SEC-02a; reuse worker resume path).
6. `test_approval_not_replayable_across_tasks` — token for task A's record → reject when presented for task B's record_id (SEC-02b).
7. MCP parity: `test_mcp_submit_approval_requires_token` — same forged/valid checks against the MCP tool path.

**Existing coverage to build on:** `test_approval_gating.py` already proves payload-hash binding (`test_payload_hash_binds_to_exact_payload`) and the pause→approve→complete flow; `test_slack_verify.py` is the template for the token tests (valid/tampered/stale/no-secret). CONCERNS.md "Test Coverage Gaps" explicitly lists items 2/6/(c) as currently missing — this file closes them.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| psycopg2 (`connect`, separate `psycopg2-pool` ecosystems) | psycopg3 + `psycopg_pool.ConnectionPool`, native `Jsonb`, sync+async parity | psycopg3 GA 2021, 3.3.x current | Use psycopg3 sync pool — already the project's declared driver. |
| `pubsub_v1` callback streaming pull | unchanged (still current in 2.39.0) | — | Existing `worker/main.py` pattern is current; no change. |
| Hand-rolled token crypto | stdlib `hmac.compare_digest` (constant-time) | stable since 3.3 | Mirror `slack_verify.py`; no third-party crypto. |

**Deprecated/outdated:**
- psycopg2 for new code — superseded by psycopg3 (project already on psycopg3).
- Any async-repo direction for Phase 1 — the codebase is sync; async is a Phase-2 checkpointer concern only.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | PyJWT/itsdangerous *suitability* judgement (HMAC preferred) | Standard Stack | Low — if team mandates JWT, swap is mechanical; HMAC remains valid. |
| A2 | `google-cloud-pubsub` admin `create_subscription(name=, topic=)` keyword signature in 2.x | DUR-03 | Low — verify exact kwargs at implement time; emulator path itself is standard. |
| A3 | Migrations are applied by external tooling (`psql`/migration runner), not by `RepositorySQL` at startup | Pitfall 2, DUR-01 | Low–Med — if the team wants the repo to self-apply migrations, that adds the autocommit/CONCURRENTLY concern into Phase 1. Recommend keeping migration application external. |
| A4 | No committed `requirements/*.txt` need regen, OR they do and must be regenerated after adding `psycopg-pool` | Runtime State Inventory | Low — STACK.md says lockfiles are generated from pyproject; regenerate if present. |

**If verifying A2/A3 changes the plan, surface to the planner before locking 01-02/01-01.**

## Open Questions

1. **Should `RepositorySQL` self-apply migrations on first connect, or rely on external `psql`/migration tooling?**
   - What we know: `0001`/`0002` are idempotent (`IF NOT EXISTS`); `scripts/` has a deploy path.
   - What's unclear: whether Phase 1 wants `make migrate` / a runner, or assumes the DB is pre-migrated.
   - Recommendation: keep migration application **external** to the repo (a `make migrate` target running `psql -f`), so the repo stays free of the CONCURRENTLY/autocommit concern. Document the local-Postgres bring-up in the plan.

2. **`TaskRecord.metadata` → `task_metadata` rows, or documented drop for the POC?**
   - Recommendation: write non-empty metadata to `task_metadata` for round-trip fidelity; it's a few lines and the table already exists. If deferred, document explicitly (Pitfall 5).

3. **Does `sessions.ensure_session` need a real `sessions`-table upsert for DUR-01?**
   - DUR-01 names "sessions … survive a worker restart." `ensure_session` currently mints an id only. Recommendation: in the SQL path, upsert a `sessions` row so session survival is real; keep in-mem path as-is.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL 15+ (local) | DUR-01/02 integration tests | ✗ (not provisioned; local only this phase) | — | InMemoryRepository for unit tests; pg tests skip unless `TEST_DATABASE_URL` set |
| `psycopg[binary]` | RepositorySQL | declared `>=3.1`, latest 3.3.4 | install via `runtime` extra | — |
| `psycopg-pool` | ConnectionPool | **MISSING from pyproject** | add `>=3.2` (latest 3.3.1) | — (must add) |
| `google-cloud-pubsub` | DUR-03 | declared `>=2.21`, latest 2.39.0 | install via `runtime` extra | InProcessDispatcher |
| `gcloud beta emulators pubsub` | DUR-03 local validation | ✗ (requires gcloud SDK) | — | InProcessDispatcher path proves dispatch logic without emulator; emulator test skipped if absent |

**Missing dependencies with no fallback:** `psycopg-pool` must be added to `pyproject.toml` `runtime` extra (it is NOT a transitive dep of `psycopg[binary]`).
**Missing dependencies with fallback:** local Postgres and the Pub/Sub emulator are validation-only; unit tests run fully on the in-memory/in-process fakes (skip pg/emulator tests when their env vars are unset — matches TESTING.md "no external deps for tests").

## Security Domain

> This is fundamentally a security phase (SEC-01/02 close a Critical write-gate bypass). `security_enforcement` is not set in config.json — treated as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | HMAC-signed approval token authenticates the approver action (replaces self-asserted `approver_id`). |
| V3 Session Management | partial | Token expiry (`exp`) bounds the approval window; mirrors Slack's 5-min replay window (consider 60s–1h TTL). |
| V4 Access Control | yes | Token bound to `approval_record_id` → an approval authorizes exactly one task's write (no cross-task reuse). |
| V5 Input Validation | yes | `payload_hash` re-validation at execution (`is_approved`) ensures the approved payload is the executed payload. |
| V6 Cryptography | yes | stdlib `hmac` + `compare_digest` (constant-time). Never hand-roll comparison or use `==` on signatures. |
| V8 Data Protection | yes (DUR-02) | Tenant-scoped reads prevent cross-tenant data exposure. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Forged approval (self-asserted `approver_id`) | Spoofing / Elevation of Privilege | HMAC token verified before `record_decision` (SEC-01) — at HTTP and MCP. |
| Approval replay across tasks | Tampering / Repudiation | Token bound to `approval_record_id` + `exp` (SEC-02b). |
| Payload mutation after approval | Tampering | `payload_hash` re-hash at execution (`is_approved`, SEC-02a) — existing. |
| Cross-tenant read | Information Disclosure | `tenant_id` mandated in read protocol (DUR-02). |
| SQL injection in RepositorySQL | Tampering | psycopg3 parameterized queries (`%s` placeholders) — never string-format SQL. |
| Timing attack on token compare | Information Disclosure | `hmac.compare_digest` (constant-time). |

## Recommended Build Order & Cross-Plan Coupling

```
01-01 (DUR-01, DUR-02)  ── LINCHPIN ──┐
   1. Widen Repository protocol:       │
      +tenant_id on list_events/list_evaluations;  ADD list_tool_calls/list_approvals
   2. Update InMemoryRepository to match
   3. Migrate private reach-ins: runner.py:_pending_calls, test_approval_gating.py, smoke.py
   4. Implement RepositorySQL (sync psycopg3 ConnectionPool) over 0001/0002
   5. Route get_repository() on DATABASE_URL
   6. test_repository_sql.py: round-trip, restart-survival, cross-tenant-empty
                                        │
                                        ▼
01-03 (SEC-01, SEC-02)  ── depends on 01-01 ──
   Uses the repaired resume path + new list_* methods for SEC-02(a) mutation test.
   issue/verify token in approvals.py; enforce at app.py AND mcp_server.py;
   test_approval_security.py (7 cases above).

01-02 (DUR-03)  ── INDEPENDENT (can run in parallel) ──
   Validate existing PubSubDispatcher + worker/main.py against the Pub/Sub emulator;
   add idempotent emulator setup helper + skip-unless-emulator integration test.
```

**Cross-plan coupling (call out to planner):** the protocol widening in **01-01 step 1–3 is a prerequisite for 01-03's SEC-02(a) test** (which drives the resume path) and for any new test that needs `list_tool_calls`/`list_approvals` instead of private access. 01-02 touches no shared seam with 01-01/01-03 and can proceed in parallel. Do NOT start RepositorySQL (01-01 step 4) before the protocol/reach-in migration (steps 1–3) — that ordering is the whole point of Pitfall 3.

## Sources

### Primary (HIGH confidence)
- This repository — `src/agent_mesh/services/{repository,approvals,task_service,dispatch,sessions}.py`, `api/{app,slack_verify,mcp_server}.py`, `worker/{runner,main}.py`, `settings.py`, `contracts/{models,enums}.py`, `migrations/0001_init.sql`, `migrations/0002_self_improvement.sql`, `pyproject.toml`, `tests/*` — read in full this session.
- `.planning/codebase/{CONCERNS,TESTING,STACK,CONVENTIONS}.md`, `.planning/{REQUIREMENTS,ROADMAP}.md`, `.planning/config.json` — read this session.
- PyPI version checks via `pip index versions` (2026-06-05): psycopg 3.3.4, psycopg-pool 3.3.1, google-cloud-pubsub 2.39.0, PyJWT 2.13.0, itsdangerous 2.2.0.

### Secondary (MEDIUM confidence)
- Project memory (surfaced by orchestrator): two psycopg gotchas (DSN options kwargs; AsyncPostgresSaver `autocommit=True` for CONCURRENTLY) — scoped to Phase 2 vs the sync-DSN one applicable here.
- psycopg3 ConnectionPool usage pattern — psycopg.org docs (cited, not re-fetched live this session; verify exact API at implement time).

### Tertiary (LOW confidence)
- Exact `google-cloud-pubsub` 2.x admin `create_subscription` kwargs — verify against installed version when wiring 01-02 (Assumption A2).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified on PyPI; psycopg/pubsub already declared in pyproject.
- Architecture / protocol-widening finding: HIGH — confirmed by grep (`repo._`/`_repo._` reach-ins) and reading `runner.py`/`worker/main.py`.
- SEC token design: HIGH — directly mirrors tested `slack_verify.py`; concrete code given.
- DUR-03 emulator API exact calls: MEDIUM — pattern is standard, exact kwargs to verify at implement time.

**Research date:** 2026-06-05
**Valid until:** ~2026-07-05 (stable stack; re-verify pubsub admin API + psycopg-pool pin if implementing later).
