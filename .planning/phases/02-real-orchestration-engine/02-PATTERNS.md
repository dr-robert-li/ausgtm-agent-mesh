# Phase 2: Real Orchestration Engine - Pattern Map

**Mapped:** 2026-06-05
**Files analyzed:** 12 (5 source modified, 1 config modified, 2 new source, 4 new tests, 1 test fixture modified)
**Analogs found:** 9 with in-codebase analog / 12 total (2 new source modules have no analog → RESEARCH patterns; 1 checkpointer schema is library-owned, convention-only)

> **Source-of-truth note for the planner.** The single load-bearing decision in this phase
> is RF-1: the LangGraph `interrupt()` is the durable **pause mechanism**; the Phase-1
> signed-token + payload-hash ledger (`approvals.py`) remains the **decision authority**.
> The analogs below preserve that boundary. See `## Shared Patterns` — those entries are
> security-load-bearing and apply across `orchestrator.py` / `graph.py` / `runner.py`.

## File Classification

| New/Modified File | N/M | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|-----|------|-----------|----------------|---------------|
| `src/agent_mesh/worker/orchestrator.py` | M | service (orchestration adapter) | event-driven / request-response | itself — existing `run_mesh` + `langgraph_available()` stub-fallback | exact (extend in place) |
| `src/agent_mesh/worker/graph.py` | N | service (StateGraph builder + interrupt node) | event-driven (graph) | none in codebase → RESEARCH Pattern 1/2; structural skeleton from `orchestrator.py` stub-fallback | no analog (structure-only) |
| `src/agent_mesh/worker/roster.py` | N | service (declared roster + deepagents wiring) | event-driven (delegation) | none in codebase → RESEARCH RF-3; gate shape from `orchestrator.py` `deep_agents_available()` | no analog (structure-only) |
| `src/agent_mesh/worker/runner.py` | M | service (worker driver) | event-driven / request-response | itself — existing `_resume_after_approval` (runner.py:106-132) | exact (extend in place) |
| `src/agent_mesh/sandbox/executor.py` | M | utility (sandbox executor) | file-I/O / batch (subprocess) | itself — existing `_preexec` / `execute_code` | exact (replace fail-open block) |
| `pyproject.toml` | M | config | n/a | itself — existing `agents` / `runtime` optional-extras block | exact (raise pins) |
| LangGraph checkpointer schema | N | migration (library-owned) | n/a | `migrations/0001`/`0002` header + idempotency convention + `README.md` apply step | convention-only (see ⚠ below) |
| `tests/test_orchestration_graph.py` | N | test (ORCH-01) | n/a | `tests/test_stack_and_toolpacks.py` (stack-present assertion) + `tests/test_approval_gating.py` (worker flow) | role-match |
| `tests/test_checkpointer_resume.py` | N | test (ORCH-02) | n/a | `tests/test_repository_sql.py::test_restart_survival_all_four_state_families` (pool-drop → reopen-same-DSN) | strong (data-flow match) |
| `tests/test_interrupt_hitl.py` | N | test (ORCH-03) | n/a | `tests/test_approval_security.py` (SEC-01/SEC-02 pause→approve→resume) | strong |
| `tests/test_sandbox.py` | N | test (SBX-01) | n/a | `tests/test_repository_sql.py` skip-when-unset gating shape (no existing sandbox test) | role-match (gating-pattern only) |
| `tests/conftest.py` | M | test fixture | n/a | itself — existing `pg_dsn` / `sql_repo` skip-when-unset fixtures | exact (add markers) |

> ⚠ **Checkpointer schema is NOT a hand-written `0003` of app tables.** Per RESEARCH §RF-2,
> `PostgresSaver.setup()` creates and owns `checkpoints` / `checkpoint_writes` /
> `checkpoint_blobs` as a **sibling schema in the same DB** — it does NOT extend
> `0001`/`0002`. Do **not** copy the `CREATE TABLE` DDL pattern to hand-roll these tables.
> The canonical mechanism is `checkpointer.setup()` (idempotent). The only legitimate
> analog use is the `0001`/`0002` **header + IF-NOT-EXISTS idempotency convention** and the
> `migrations/README.md` apply step — and that only if a thin *documentary*
> `0003_langgraph_checkpointer.sql` is added that records/runs the `.setup()`-equivalent.

## Pattern Assignments

### `src/agent_mesh/worker/orchestrator.py` (service, event-driven) — MODIFY in place

**Analog:** itself. Preserve `OrchestrationResult` (orchestrator.py:39-45) and the
`langgraph_available()` / `deep_agents_available()` gates (orchestrator.py:48-67). Replace
the `_run_langgraph` placeholder (orchestrator.py:105-122, currently returns `_run_stub`)
with a real `builder.compile(checkpointer=...).invoke(...)`; add a NEW `resume_mesh`.

**Stub-fallback gate to preserve** (orchestrator.py:48-58, 77-79):
```python
def langgraph_available() -> bool:
    try:
        import langgraph  # noqa: F401
        return True
    except Exception:
        return False

def run_mesh(task: TaskRecord) -> OrchestrationResult:
    if langgraph_available():
        return _run_langgraph(task)   # ← becomes the real compiled-graph invoke
    return _run_stub(task)            # ← deterministic path stays = Phase 2 test surface
```

**Return contract to preserve** (orchestrator.py:39-45) — both `run_mesh` and the new
`resume_mesh` return this; `proposed_writes` presence is the paused signal the worker
branches on (runner.py:57):
```python
@dataclass
class OrchestrationResult:
    summary: str
    proposed_writes: list[dict] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    trace_id: str | None = None   # leave unset/stubbed in Phase 2 (Langfuse = Phase 3)
```

**Checkpointer construction** — analog `RepositorySQL.__init__` (repository.py:463-477): lazy
import of the optional driver, construct from `DATABASE_URL`/DSN, expose `close()`. Mirror this
shape for `PostgresSaver` (prod) selection; `SqliteSaver`-file for the dep-light test path.
```python
# RESEARCH §RF-2 / Code Examples:
from langgraph.checkpoint.postgres import PostgresSaver   # prod
checkpointer = PostgresSaver.from_conn_string(database_url)
checkpointer.setup()                                       # idempotent table create
graph = builder.compile(checkpointer=checkpointer)
config = {"configurable": {"thread_id": task.task_id}}     # DUR-02: task loaded tenant-scoped
result = graph.invoke(initial_state, config)
if "__interrupt__" in result:
    proposed = result["__interrupt__"][0].value["proposed_writes"]  # → OrchestrationResult.proposed_writes
```

**New `resume_mesh(task, decision)`** — RESEARCH §RF-1 step 4 + Code Examples:
```python
from langgraph.types import Command
# same store, same thread_id; resume carries ONLY an already-verified decision
graph.invoke(Command(resume=verified_decision), {"configurable": {"thread_id": task.task_id}})
# return a terminal OrchestrationResult(proposed_writes=[]) so runner's completion logic holds
```

---

### `src/agent_mesh/worker/graph.py` (service, event-driven) — NEW, no analog

**Analog:** none in codebase. Pattern source = RESEARCH Pattern 1 & 2. **Structural** skeleton
only is borrowed from `orchestrator.py`'s `if <available>(): real else: deterministic` gate.

**Deterministic-node-under-real-graph** (RESEARCH Pattern 1 — D-02):
```python
def planner_node(state: MeshState) -> dict:
    if model_creds_available():            # Phase 3 flips on via config, not topology
        return _run_deepagents_planner(state)
    return {"plan": f"[stub-plan] {state['prompt'][:80]}", "next": "researcher"}
```

**Write-gate interrupt node** (RESEARCH Pattern 2 — ORCH-03):
```python
from langgraph.types import interrupt
def write_gate_node(state: MeshState) -> dict:
    if not state.get("proposed_writes"):
        return {"done": True}
    decision = interrupt({"proposed_writes": state["proposed_writes"]})  # pauses + checkpoints
    return {"decision": decision}          # arrives already-verified via Command(resume=...)
```

**Anti-patterns (reject in review):** executing the write inside a graph tool-node;
`Command(resume=...)` carrying an `approver_id` the graph trusts; treating `interrupt()` as
the approval record; thin name-and-route pass-through (D-02).

---

### `src/agent_mesh/worker/roster.py` (service, event-driven) — NEW, no analog

**Analog:** none. Pattern source = RESEARCH §RF-3 verified API. Gate shape from
`orchestrator.deep_agents_available()` (orchestrator.py:61-67).

```python
from deepagents import create_deep_agent
research = {"name": "researcher", "description": "...", "system_prompt": "...",
            "tools": [...], "model": "provider:model"}  # model optional — Phase 3 swaps in
agent = create_deep_agent(model=..., subagents=[planner, research, code_writer, reviewer])
```

**ORCH-01 requirements the roster must satisfy:** exactly **four** declared members; **disable
the auto `general-purpose` subagent** (Assumption A1 / Open Question #1 — confirm the 0.6.8
disable mechanism at plan time, assert roster size == 4); **log roster size at startup**.
**Bounded, declared, no self-spawning** (CLAUDE.md guardrail). Do NOT import/enable LangSmith
(env-gated; CLAUDE.md: never a dependency).

---

### `src/agent_mesh/worker/runner.py` (service, event-driven) — MODIFY in place

**Analog:** itself. The approval branch (runner.py:57-104) fires **unchanged** — `proposed_writes`
presence still triggers `open_approval` → token stash → `AWAITING_APPROVAL`. The ONLY change is
adding the `orchestrator.resume_mesh(task, decision)` call inside `_resume_after_approval`.

**Resume path to preserve — the write executes ONLY here, under `is_approved()` (SEC-02a)**
(runner.py:106-132):
```python
def _resume_after_approval(self, task_id: str) -> str:
    task = self._repo.get_task(task_id)             # tenant-scoped load (DUR-02)
    for call in self._pending_calls(task_id, task.tenant_id):
        record = self._repo.get_approval(call.approval_record_id)
        if approvals.is_approved(record, call.parameters):   # re-hash gate — SEC-02a
            result = self._execute(call)            # Tool Gateway executes here, not in a graph node
            ...
```
**Add (per RESEARCH §RF-1 step 4):** before/around the existing execute loop, call
`resume_mesh(task, decision)` so the paused graph runs to terminal — but the Tool Gateway
`.execute` stays in this method, gated by `is_approved()`.

---

### `src/agent_mesh/sandbox/executor.py` (utility, file-I/O) — MODIFY (replace fail-open)

**Analog:** itself. **Replace** the fail-open `RLIMIT_AS` block (executor.py:47-51) — the SBX-01
bug — with the Docker cgroup path + refuse-to-run-unbounded.

**The fail-open block to delete** (executor.py:47-51):
```python
        try:
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        except (ValueError, OSError):
            pass     # ← D-03 forbids this: silent fail-open on the memory cap
```

**Preserve** `SandboxLimits.max_memory_mb` default 512 (executor.py:24-28), the temp-dir
isolation + `timeout=limits.timeout_s` wall-clock (executor.py:60-73), and `propose_patch`'s
`approval_required=True` (executor.py:95-107, unchanged — no auto-apply).

**Replacement (RESEARCH §RF-4):** Docker `--memory=512m --memory-swap=512m` (MUST be equal),
`--network=none`, `--read-only`, `--tmpfs /work:rw,size=64m`, `--user 65534:65534`,
`--cap-drop=ALL`, `--security-opt no-new-privileges`, `--pids-limit=128`, pinned
`python:3.11-slim`. **Docker present → run cgroup path (works on macOS via Docker's Linux VM);
Docker absent → raise `SandboxUnavailable`, NEVER the unbounded native subprocess.** OOM →
exit 137.

---

### `pyproject.toml` (config) — MODIFY (raise stale pins — a deliverable)

**Analog:** itself — the `agents` / `runtime` optional-extras block (pyproject.toml:24-35).
Stale floors (`langchain>=0.3`, `langgraph>=0.2`, `deepagents>=0.0.2`) resolve to APIs that
predate `create_deep_agent(subagents=...)` and the `langgraph.checkpoint.*` package split.

```toml
agents = [
    "langchain>=1.0",
    "langgraph>=1.0,<2",
    "langgraph-checkpoint-postgres~=3.1",
    "langgraph-checkpoint-sqlite~=3.1",
    "deepagents~=0.6.8",
]
```
`psycopg[binary]>=3.1` / `psycopg-pool>=3.2` already exist in `runtime` (pyproject.toml:18-19)
— the `PostgresSaver` driver reuses them; no new secret keys.

---

### LangGraph checkpointer schema (migration) — NEW, convention-only (library-owned)

**Analog:** `migrations/0001_init.sql` / `0002_self_improvement.sql` **header + idempotency
convention** ONLY, plus `migrations/README.md` apply step. **NOT** the `CREATE TABLE` DDL —
`PostgresSaver.setup()` owns those tables. See the ⚠ note above.

**Convention to mirror IF a documentary file is added** (0002 header excerpt):
```sql
-- Agent Mesh POC — <subject> schema.
-- Region: australia-southeast1 (durable store stays in Australia).
-- This migration is idempotent: it uses IF NOT EXISTS so it can be re-applied.
```
`migrations/README.md`: migrations are "Applied in lexical order; each file is idempotent;
applied EXTERNALLY (psql -f), the repo never self-applies." The checkpointer's `.setup()` is
the canonical, idempotent create — document it as a **sibling schema in the same DB**.

---

### `tests/test_orchestration_graph.py` (test, ORCH-01) — NEW

**Analogs:** `tests/test_stack_and_toolpacks.py` (assert-contract-when-stack-present shape) +
`tests/test_approval_gating.py` (worker-flow `_service_and_worker` helper). Gate the real-graph
case behind the `agents` extra; keep an always-on `test_stub_fallback` that asserts the stub path
still produces an `OrchestrationResult` without the stack. Assert roster size == 4 + size logged.

---

### `tests/test_checkpointer_resume.py` (test, ORCH-02) — NEW

**Analog (strong):** `tests/test_repository_sql.py::test_restart_survival_all_four_state_families`
(test_repository_sql.py:70-120) — the **drop-then-reopen-same-store** restart proof. Mirror it for
the checkpointer: open `SqliteSaver` on a tempfile → invoke to `interrupt()` → drop graph+saver →
fresh `SqliteSaver` on the SAME tempfile + fresh graph → `Command(resume=...)` same `thread_id` →
assert terminal. NEVER `InMemorySaver` (it loses exactly what a restart loses). Always-on case
gated by the `agents` extra; Postgres case env-gated via `TEST_DATABASE_URL` like `pg_dsn`.

```python
# analog: test_repository_sql.py:98-100
repo.close()                              # drop the pool / saver  = simulated restart
reopened = RepositorySQL(pg_dsn)          # fresh object, SAME DSN/store
assert reopened.get_task(task.task_id) is not None and ... .state == TaskState.QUEUED.value
```

---

### `tests/test_interrupt_hitl.py` (test, ORCH-03) — NEW

**Analog (strong):** `tests/test_approval_security.py` — its `_pause_on_write(repo)` helper
(test_approval_security.py:42-57) drives create→`process`→`awaiting_approval`→read worker-issued
token; reuse that exact pattern. Assert: `interrupt()` pauses; a **verified** decision resumes;
the write executes ONLY after `is_approved()`. The Phase-1 SEC suite (`test_approval_security.py`)
**MUST stay green through the new interrupt path** — that is the phase gate.

```python
# analog: test_approval_security.py:135-164 — forged approver rejected, token-derived approver wins
# the new path must NOT let Command(resume=...) carry/trust an approver_id
```

---

### `tests/test_sandbox.py` (test, SBX-01) — NEW

**Analog:** no existing sandbox test; borrow the **skip-when-unavailable gating shape** from
`conftest.pg_dsn` (conftest.py:65-78) / `test_repository_sql` env-gating.
- **Always-on invariant:** monkeypatch `shutil.which` → `None` → `execute_code` **raises/refuses**
  (never runs the unbounded subprocess). Runs everywhere incl. macOS `make test`.
- **Docker-gated:** `@pytest.mark.skipif(shutil.which("docker") is None, ...)` → over-allocation
  snippet → assert exit **137** (OOM).

---

### `tests/conftest.py` (test fixture) — MODIFY (add markers)

**Analog:** itself — the existing `pg_dsn` skip-when-unset fixture (conftest.py:65-78) and the
`repo` fixture (conftest.py:23-26, reuse it). Add an **`agents`-extra skip marker** that reuses
`orchestrator.langgraph_available()` / `deep_agents_available()` (do NOT re-derive an import probe)
and a `shutil.which("docker")` skip marker — both mirroring `pg_dsn`'s skip-cleanly shape.

```python
# analog: conftest.py:73-75
dsn = os.getenv("TEST_DATABASE_URL")
if not dsn:
    pytest.skip("TEST_DATABASE_URL unset; SQL-backed tests require a local Postgres")
# new marker, same shape:
# if not langgraph_available(): pytest.skip("agents extra not installed")
```

## Shared Patterns

> These are security-load-bearing (RF-1) and cross-cutting. They apply across
> `orchestrator.py`, `graph.py`, and `runner.py` — apply to ALL three, not per-file.

### Approval decision authority = signed-token ledger (NEVER the graph)
**Source:** `src/agent_mesh/services/approvals.py` — `verify_approval_token` (approvals.py:113-155,
FAIL CLOSED, returns the token's `requester_id` as the ONLY trusted approver) + `is_approved`
(approvals.py:200-210, payload re-hash). **Apply to:** the graph/orchestrator interrupt path.
The `interrupt()` is plumbing; this is the law.
```python
# approvals.py:128-130 — the single fail-closed gate
secret_val = _approval_secret(secret)
if not secret_val:
    return None  # FAIL CLOSED — no secret, no approval.
# approvals.py:138-139 — cross-task replay defense
if record_id != record.approval_record_id:
    return None  # token for task A cannot approve task B
```

### Write executes only after re-hash, only in the worker
**Source:** `runner._resume_after_approval` (runner.py:106-132). **Apply to:** orchestrator/graph.
Tool Gateway `.execute` is called ONLY here, under `approvals.is_approved(record, call.parameters)`
(runner.py:116). **Anti-patterns to reject:** (i) write inside a graph tool-node;
(ii) `Command(resume=...)` carrying a trusted `approver_id`; (iii) `interrupt()` AS the approval record.

### DUR-02 tenant scoping on the checkpointer
**Source:** the tenant-scoped reads `repo.get_task` / `repo.list_tool_calls(task_id, tenant_id)`
(runner.py:43, 137; repository.py:455-461). **Apply to:** every `thread_id`-keyed graph read.
Checkpointer tables key on `thread_id` ONLY — set `thread_id = task_id` where the task was loaded
tenant-scoped; **never resume a bare `thread_id`** without re-loading the task tenant-scoped.

### Optional-dep stub-fallback degradation
**Source:** `orchestrator.langgraph_available()` / `deep_agents_available()` (orchestrator.py:48-67)
and `RepositorySQL`'s lazy driver import (repository.py:464-466). **Apply to:** graph/roster nodes
and the new tests. Every heavy-stack seam degrades to a deterministic path so `make test`/`make smoke`
run with no cloud deps — that deterministic path IS the Phase 2 test surface (D-02).

## No Analog Found

| File | Role | Data Flow | Reason | Pattern source |
|------|------|-----------|--------|----------------|
| `src/agent_mesh/worker/graph.py` | service | event-driven | No `StateGraph`/interrupt code exists yet | RESEARCH Pattern 1 & 2; structural gate from `orchestrator.py` |
| `src/agent_mesh/worker/roster.py` | service | event-driven | No deepagents wiring exists yet | RESEARCH §RF-3 verified API; gate from `orchestrator.deep_agents_available()` |
| LangGraph checkpointer tables | migration | n/a | Library-owned (`PostgresSaver.setup()`); NOT a hand-written `0003` of app tables | RESEARCH §RF-2; convention from 0001/0002 headers only |

## Metadata

**Analog search scope:** `src/agent_mesh/worker/`, `src/agent_mesh/services/`,
`src/agent_mesh/sandbox/`, `migrations/`, `tests/`, `pyproject.toml`.
**Files scanned/read:** orchestrator.py, runner.py, executor.py, approvals.py, repository.py
(RepositorySQL `__init__`), lifecycle.py, migrations/0001_init.sql (header), 0002_self_improvement.sql,
migrations/README.md, conftest.py, test_repository_sql.py, test_approval_security.py,
test_approval_gating.py, test_stack_and_toolpacks.py, pyproject.toml.
**Pattern extraction date:** 2026-06-05

## PATTERN MAPPING COMPLETE
