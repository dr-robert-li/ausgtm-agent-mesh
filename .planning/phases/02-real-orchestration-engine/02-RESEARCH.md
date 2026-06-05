# Phase 2: Real Orchestration Engine - Research

**Researched:** 2026-06-05
**Domain:** Durable multi-agent orchestration (LangGraph state graph + checkpointer + interrupt HITL) + Deep Agents roster + hardened sandbox
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Keep the layering — durability → orchestration → model plane. Phase 2 runs the real graph against a stubbed/deterministic model path; no model credentials or live gateway required to pass Phase 2. Do NOT pull Phase 3's live model gateway forward.
- **D-02:** Real graph, deterministic node outputs. Build the actual LangGraph supervisor graph with the four declared roster nodes (planner, researcher/tool-router, code-writer, reviewer). Each node executes for real and emits *deterministic* output instead of calling a model. The delegation path is genuinely exercised and roster size is logged at startup (ORCH-01). Swapping in real models in Phase 3 should be a configuration change, not a topology rebuild. Avoid a thin name-and-route pass-through.
- **D-03:** Docker required for sandbox execution. The hardened container path (cgroup memory limit) is the only real execution path. The executor must never run unbounded: on `RLIMIT_AS` rejection or absent Docker, the sandbox refuses/skips rather than failing open.
- **D-03a:** The sandbox memory-enforcement test should skip cleanly when Docker is unavailable (pytest skip + clear message), and assert real cgroup enforcement wherever Docker exists (Linux/CI). Non-negotiable invariant tested everywhere: the executor refuses to run unbounded.

### Claude's Discretion
- Checkpointer backend choice and the exact restart-simulation mechanism (research focus #2), within the constraint that the durable prod path is the Postgres checkpointer over the existing migrations.
- Internal node/state-schema shape of the LangGraph supervisor.

### Deferred Ideas (OUT OF SCOPE)
- Real-model agent behaviour (live LiteLLM gateway, real delegation against models) — Phase 3/5.
- Langfuse trace wiring of graph spans (`OrchestrationResult.trace_id`) — Phase 3. Phase 2 may leave `trace_id` unset/stubbed.
- Production sandbox isolation (gVisor/Cloud Run Job, signed images, default-deny egress) — production hardening, out of v1 scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ORCH-01 | A real LangGraph supervisor graph delegates to a bounded Deep Agents roster (planner, researcher/tool-router, code-writer, reviewer); roster is declared and its size logged at startup | §RF-1, §RF-3, §Architecture Patterns — own a `StateGraph` with 4 declared nodes; use deepagents `create_deep_agent(subagents=[...])` within nodes with the auto general-purpose subagent disabled |
| ORCH-02 | The LangGraph Postgres checkpointer is wired; a >60-min run resumes from its durable checkpoint after a process restart | §RF-2 — `PostgresSaver` (prod) / file-backed `SqliteSaver` (dep-light restart-sim); thread_id = task_id; `.setup()` for table creation |
| ORCH-03 | A write approval is a LangGraph interrupt that pauses the graph and resumes from the checkpoint when the decision arrives | §RF-1 — `interrupt()` in the write-gate node pauses+checkpoints; worker maps `__interrupt__`→`proposed_writes`; existing signed-token ledger remains the decision authority; `Command(resume=...)` carries the already-verified decision |
| SBX-01 | The prompt-to-code sandbox enforces memory limits without failing open and executes via a hardened container path | §RF-4 — Docker `--memory`+`--memory-swap` equal, `--network=none`, `--read-only`, non-root, `--cap-drop=ALL`; refuse (never silent fail-open) when Docker absent or rlimit rejected |
</phase_requirements>

## Summary

Phase 2 replaces the deterministic stub in `worker/orchestrator.py:_run_langgraph` with a real LangGraph state graph whose four nodes (planner, researcher/tool-router, code-writer, reviewer) genuinely execute and delegate, emitting deterministic outputs while the model path stays stubbed (D-01/D-02). The graph compiles with a checkpointer keyed on `thread_id = task_id`, and the existing write-approval pause becomes a LangGraph `interrupt()` — but the **interrupt is only the pause mechanism; the Phase-1 signed-token + payload-hash approval ledger remains the single source of truth for the decision**. This reconciliation is the highest-risk part of the phase: done wrong it reopens the SEC-01 bypass that Phase 1 closed.

The verified library set is current and first-party (langchain-ai org): `langgraph` 1.x, `langgraph-checkpoint-postgres` 3.1.0 (`PostgresSaver`, has `.setup()`), `langgraph-checkpoint-sqlite` 3.1.0 (file-backed `SqliteSaver` — the dep-light restart simulator), and `deepagents` 0.6.8 (`create_deep_agent(subagents=[...])`). The current pyproject pins (`langgraph>=0.2`, `deepagents>=0.0.2`) are dangerously stale and resolve to APIs that no longer match — **updating these pins is a Phase-2 deliverable, not a footnote.** The sandbox hardening is a Docker cgroup path (`--memory` with equal `--memory-swap`, network-off, read-only, non-root) that works even on macOS (Docker Desktop runs a Linux VM), with a hard refuse-to-run-unbounded invariant everywhere Docker is absent.

**Primary recommendation:** Own the `StateGraph` (4 declared nodes + `PostgresSaver`/`SqliteSaver` checkpointer + `interrupt()` in the write-gate node) so the checkpointer and interrupt are under your direct control; use `deepagents.create_deep_agent` *within* nodes (auto `general-purpose` subagent disabled) for the roster harness. Keep `interrupt() = pause`, `ledger = authority`; keep `make smoke` on the stub path; gate real-graph tests behind the `agents` extra and the Docker test behind `shutil.which("docker")`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Graph topology + node delegation | Execution plane (`worker/orchestrator.py`) | — | The mesh worker owns orchestration; `run_mesh(task)` is the seam (`orchestrator.py:70`) |
| Durable run state (checkpoint) | Data layer (Postgres via `PostgresSaver`) | Execution plane | LangGraph owns durability per CLAUDE.md §3; checkpointer persists, worker drives |
| Approval **decision authority** | Control plane (`services/approvals.py` + `approval_records`) | Ingress (`/v1/approvals`, MCP) | SEC-01/SEC-02 live here; the interrupt must NOT become a second weaker path |
| Approval **pause mechanism** | Execution plane (`interrupt()` in graph node) | Data layer (checkpoint persists the pause) | Pause is durable graph state; the decision that resumes it is verified elsewhere |
| Write **execution** | Execution plane (`runner.py:_resume_after_approval` → Tool Gateway) | — | Writes execute only after `is_approved()` re-check (SEC-02a) — unchanged |
| Sandbox code execution | Isolated container (Docker/Cloud Run Job) | — | Never the host; cgroup is the only real enforcement boundary (SBX-01, D-03) |
| Tenant isolation on graph reads | Control plane (worker binds `thread_id` to a tenant-scoped task) | — | Checkpointer tables are keyed on `thread_id`, NOT `tenant_id` — DUR-02 must be enforced at the worker boundary |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `langgraph` | `>=1.0,<2` (current 1.2.4) | State graph, checkpointer attach point, `interrupt()`/`Command` HITL | REQUIRED stack (CLAUDE.md §1). LangGraph owns durability. `[VERIFIED: PyPI]` `[CITED: docs.langchain.com/oss/python/langgraph]` |
| `langgraph-checkpoint-postgres` | `~=3.1` (current 3.1.0) | `PostgresSaver` — durable prod checkpointer; `.setup()` creates its tables | Official LangGraph Postgres persistence backend `[VERIFIED: PyPI]` `[CITED: docs.langchain.com/oss/python/langgraph/persistence]` |
| `langgraph-checkpoint-sqlite` | `~=3.1` (current 3.1.0) | `SqliteSaver` (file-backed) — dep-light restart-simulation checkpointer for `make test` | Official LangGraph SQLite backend; file-backed → survives object teardown → simulates restart `[VERIFIED: PyPI]` |
| `deepagents` | `~=0.6.8` (current 0.6.8) | Bounded subagent harness: `create_deep_agent(subagents=[...])` | REQUIRED stack (CLAUDE.md §1). First-party langchain-ai, built on LangGraph `[VERIFIED: PyPI]` `[CITED: docs.langchain.com/oss/python/deepagents]` |
| `langchain` / `langchain-core` | `>=1.0` (current 1.3.4 / 1.4.0) | Tool/model abstraction underlying deepagents nodes | REQUIRED stack. Already an `agents`-extra member |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `psycopg[binary]` | `>=3.1` (already in `runtime` extra) | DB driver `PostgresSaver` uses | Prod checkpointer path; already installed for `RepositorySQL` |
| `psycopg-pool` | `>=3.2` (already in `runtime` extra) | Connection pool; `PostgresSaver` can take a pool | Prod path — reuse the existing pool pattern |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| File-backed `SqliteSaver` for restart-sim | `InMemorySaver` | **REJECTED for restart-sim:** in-memory state IS what dies on restart, so it cannot prove resume-after-restart. `InMemorySaver` is fine only for a same-process interrupt/resume unit test, not the restart criterion (#2). |
| Own the `StateGraph` + deepagents-in-nodes | Let `create_deep_agent` own the whole graph | **REJECTED as the primary boundary:** ORCH-02/03 need *your* checkpointer + *your* `interrupt()` placement. deepagents' checkpointer/interrupt injection and disabling the auto `general-purpose` subagent are not cleanly documented (verified: docs page does not specify them). Owning the StateGraph guarantees control and keeps the deterministic-node stub trivial. |
| Postgres checkpointer in `make test` | `DATABASE_URL`-gated Postgres test (mirror `test_repository_sql.py`) | Use BOTH: SqliteSaver-file as always-on dep-light proof; Postgres test env-gated for CI/local-with-DB. |

**Installation (update `pyproject.toml` `agents` extra — this is a deliverable):**
```toml
agents = [
    "langchain>=1.0",
    "langgraph>=1.0,<2",
    "langgraph-checkpoint-postgres~=3.1",
    "langgraph-checkpoint-sqlite~=3.1",
    "deepagents~=0.6.8",
]
```
> **Stale-pin warning (HIGH severity):** current pins are `langchain>=0.3`, `langgraph>=0.2`, `deepagents>=0.0.2` (pyproject.toml:31-35). `deepagents>=0.0.2` and `langgraph>=0.2` resolve to APIs that predate `create_deep_agent`'s current `subagents` signature and the `langgraph.checkpoint.*` package split. A fresh `pip install '.[agents]'` today would pull 1.x/0.6.x anyway (good), but the floor is misleading and must be raised so the lockfile and the code agree.

## Package Legitimacy Audit

> slopcheck could not run: the sandbox classifier correctly denied installing an agent-chosen package (`slopcheck`) not in the repo manifest. All four packages are instead verified via **official LangChain documentation + deep first-party release history** (the authoritative-source path), which is stronger than registry-existence alone.

| Package | Registry | Age (release history) | Source Repo | slopcheck | Disposition |
|---------|----------|----------------------|-------------|-----------|-------------|
| `langgraph` | PyPI | 100+ releases (0.0.9 → 1.2.4) | github.com/langchain-ai/langgraph | n/a (denied) | Approved — `[VERIFIED: docs.langchain.com]` |
| `langgraph-checkpoint-postgres` | PyPI | 40+ releases (1.0.0 → 3.1.0) | github.com/langchain-ai/langgraph | n/a (denied) | Approved — `[VERIFIED: docs.langchain.com]` |
| `langgraph-checkpoint-sqlite` | PyPI | 20+ releases (1.0.0 → 3.1.0) | github.com/langchain-ai/langgraph | n/a (denied) | Approved — `[VERIFIED: PyPI]` |
| `deepagents` | PyPI | 60+ releases (0.0.1 → 0.6.8) | github.com/langchain-ai/deepagents | n/a (denied) | Approved — `[VERIFIED: docs.langchain.com]`; **no postinstall script** (confirmed via PyPI metadata) |

**Packages removed due to slopcheck [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none. All four are official langchain-ai packages with multi-year release histories and public source repos. The planner does NOT need to gate these behind `checkpoint:human-verify` — they are the project's own REQUIRED stack (CLAUDE.md §1), already declared in pyproject.

---

## Research-Focus Answers (the 4 questions, in priority order)

### RF-1 (HIGHEST PRIORITY): Interrupt ↔ Phase-1 ledger binding

**Decision: the LangGraph `interrupt()` is the durable *pause mechanism*; the approval ledger (`approvals.py` + `approval_records` + task state) remains the *source of truth for the decision*. The interrupt never becomes a second, weaker approval path.**

**Why this is the only safe design:** Phase 1's SEC-01/SEC-02 invariants (`tests/test_approval_security.py`) are: (a) a forged/self-asserted `approver_id` is rejected — the recorded approver is derived ONLY from the verified token (`approvals.verify_approval_token` → returns the token's `requester_id`, never the request body); (b) a mutated payload invalidates a prior approval (`is_approved` re-hashes, `approvals.py:200`); (c) no cross-task replay (token bound to one `approval_record_id`, `approvals.py:138`). The fail-closed verification (`approvals.py:129`) is the load-bearing gate. **If `Command(resume=...)` carried an approver identity the graph trusted, or if the write executed inside a graph tool-node, that bypass reopens.**

**Concrete reconciliation flow (changes nothing security-critical):**

1. **Pause:** The write-gate node calls `interrupt(proposed_write)` (`from langgraph.types import interrupt`). The graph pauses; the checkpointer writes the exact paused state under `thread_id = task_id`. `[CITED: docs.langchain.com/oss/python/langgraph/interrupts]`
2. **Surface:** `run_mesh(task)` runs `graph.invoke(initial_state, config={"configurable": {"thread_id": task.task_id}})`. When paused, the result carries `result["__interrupt__"]`. The orchestrator maps that payload → `OrchestrationResult.proposed_writes` (contract at `orchestrator.py:40` preserved). **The presence of `proposed_writes` is exactly the signal the worker already branches on** (`runner.py:57`) — so the worker's existing path fires *unchanged*: build `ToolCall` → `approvals.open_approval` (issues signed token) → stash token in task metadata → transition `AWAITING_APPROVAL` (`runner.py:65-104`).
3. **Decide:** The decision arrives at `/v1/approvals` (or MCP `submit_approval`). `verify_approval_token` runs fail-closed (SEC-01); cross-record/expiry/HMAC checks run (SEC-02b). **Unchanged.** `record_decision` writes the verified `approver_id` to the ledger.
4. **Resume:** Worker `process()` sees `TaskState.APPROVED` and calls `_resume_after_approval` (`runner.py:106`). Add a NEW orchestrator entry point — `orchestrator.resume_mesh(task, decision)` — that loads the checkpoint and re-invokes the graph with `Command(resume=decision)` and the same `thread_id`. The `interrupt()` call returns the *already-verified* decision; the graph runs to terminal. **The write still executes in `_resume_after_approval` under `is_approved()` (SEC-02a re-hash) before any Tool Gateway call (`runner.py:116`) — unchanged.**

**The invariant the planner must assert (and reject the opposite of):** the token is verified at exactly one trusted point (the existing endpoint), and `Command(resume=...)` carries an already-verified boolean/decision, **never** an approver identity the graph trusts. Explicitly rejected anti-patterns: (i) executing the write inside a graph tool-node; (ii) letting the resume value carry an `approver_id`; (iii) treating `interrupt()` as the approval record. All three recreate the bypass.

**Seams to verify in planning (not assume):**
- Lifecycle already supports `AWAITING_APPROVAL → APPROVED → RUNNING → COMPLETED` (`lifecycle.py:26-29`). **No state-machine change needed.** Confirm in plan.
- `OrchestrationResult` stays the return shape for both `run_mesh` and the new `resume_mesh`; `proposed_writes`-presence is the paused signal. Confirm the resume path returns a `proposed_writes=[]` (terminal) result so `_resume_after_approval`'s completion logic stays correct.
- `self_improvement.open_promotion_approval` already unpacks `(record, _token)` (`self_improvement.py:223`) — the interrupt path does not touch that call site, so it does not regress. Confirm no shared mutation.

**Source-of-truth verdict:** worker/task-state + ledger is authoritative; the graph interrupt is a durable pause that the authoritative decision releases.

### RF-2: Checkpointer backend + restart-simulation

**Prod backend:** `PostgresSaver` from `langgraph-checkpoint-postgres~=3.1`.
```python
from langgraph.checkpoint.postgres import PostgresSaver
checkpointer = PostgresSaver.from_conn_string(database_url)  # or wrap the existing pool
checkpointer.setup()  # creates checkpoints / checkpoint_writes tables (idempotent)
graph = builder.compile(checkpointer=checkpointer)
```
`[CITED: docs.langchain.com/oss/python/langgraph/persistence]`

**Where it lives relative to 0001/0002 migrations:** `PostgresSaver` creates and owns its **own** thread_id-keyed tables (`checkpoints`, `checkpoint_writes`, `checkpoint_blobs`). It does **not** share or extend the 0001/0002 application schema. Document it as a **sibling schema applied via `.setup()`** in the same database — NOT as a hand-written `0003` migration of those tables. (Optionally add a thin `0003_langgraph_checkpointer.sql` that just documents/runs `.setup()`-equivalent, but the library's `.setup()` is the canonical path and is idempotent.)

**What stands in for Postgres in `make test` (dep-light, no DB):** file-backed `SqliteSaver` from `langgraph-checkpoint-sqlite~=3.1`.
```python
from langgraph.checkpoint.sqlite import SqliteSaver
# file-backed, NOT :memory: — the file is what survives the simulated restart
```
`InMemorySaver` is acceptable ONLY for a same-process interrupt/resume unit test; it CANNOT prove resume-after-restart (memory is exactly what a restart loses).

**Exact restart-simulation mechanism (no real 60-min wait — criterion #2 blesses a *simulated* >60-min run):**
1. Open `SqliteSaver` against a tempfile path; compile graph; `graph.invoke(..., thread_id=T)` → runs to the `interrupt()` (the "long run is now paused" point).
2. **Drop the graph + saver objects** (simulate process death) — del / leave the `with` block / new test function.
3. Open a **fresh** `SqliteSaver` against the **same tempfile**, compile a **fresh** graph, invoke `Command(resume=decision)` with the **same `thread_id=T`**.
4. Assert the graph resumes from the persisted checkpoint and reaches terminal — proving durable resume-after-restart logic without a database or a timer.

**Tenant scoping (DUR-02) is NOT free on the checkpointer.** The checkpointer tables key on `thread_id`, not `tenant_id`. Enforce at the worker boundary: `thread_id = task_id` where the task was loaded tenant-scoped (`repo.get_task` + the existing tenant-scoped `list_*` methods). **Never resume a thread without first re-loading the task tenant-scoped.** State this as an explicit verification step.

**Test layering:**
- Always-on (no deps gate the *logic*): SqliteSaver-file restart-sim — gated only by the `agents` extra being installed (skip cleanly otherwise).
- Env-gated (`DATABASE_URL`, mirror `test_repository_sql.py`): the real `PostgresSaver` restart test for CI/local-with-DB.

### RF-3: `deepagents` stability / version risk

**Verdict:** Deep Agents is REQUIRED (CLAUDE.md §1) — this is *how to integrate safely*, not *whether*. The minimal API surface for a bounded 4-member roster is stable and documented at 0.6.8.

**Verified API surface** `[CITED: docs.langchain.com/oss/python/deepagents/subagents]`:
```python
from deepagents import create_deep_agent
research = {
    "name": "researcher",                 # required — referenced by the supervisor's task() call
    "description": "...",                  # required — action-oriented
    "system_prompt": "...",               # required
    "tools": [...],                        # optional
    "model": "provider:model",            # optional — Phase 3 swaps this in
}
agent = create_deep_agent(model=..., subagents=[planner, research, code_writer, reviewer])
```
Subagents are **explicitly declared and bounded — no self-spawning** (CLAUDE.md guardrail satisfied). The main agent delegates via explicit `task()` calls by name.

**Two concrete risks the plan must address:**
1. **Auto `general-purpose` subagent:** docs state deepagents auto-adds a `general-purpose` subagent "unless disabled or replaced." ORCH-01 requires *exactly four declared* — the auto-add would make five and the startup roster-size log would read 5. **The plan must disable/replace the auto subagent** and assert roster size == 4 at startup. (Confirm the disable mechanism — `subagents` overriding by name, or a documented flag — during planning against the 0.6.8 reference.)
2. **Checkpointer/interrupt injection into a deepagents-owned graph is not cleanly documented** (verified: the overview page does not specify a `checkpointer=` param, `general-purpose` disable, or `interrupt()` placement). **Therefore choose the safe boundary: own the `StateGraph` (4 nodes + checkpointer + `interrupt()`), and use `create_deep_agent` *within* nodes** as the per-role harness. This guarantees ORCH-02/03 control and keeps the deterministic-node stub (D-02) trivial — a node calls deepagents only when the stack+creds exist, else returns deterministic output.

**LangSmith guardrail:** deepagents' overview mentions LangSmith for tracing. CLAUDE.md says LangSmith is **never a dependency**. Confirm LangSmith is optional-at-runtime (it is gated behind `LANGCHAIN_TRACING_V2`/`LANGSMITH_API_KEY` env and not imported unless enabled) — do **not** set those env vars and do **not** add `langsmith` to any extra.

### RF-4: Hardened container path on macOS

**The macOS framing has a trap to avoid:** "macOS rejects `RLIMIT_AS`" is true only for the **native subprocess** path (`executor.py:_preexec`, line 48-51 — the current fail-open bug). **Docker Desktop on macOS runs a Linux VM, so `--memory` cgroup enforcement DOES work on macOS when Docker is running.** Do not imply macOS cannot enforce — it can, via Docker.

**Exact Docker invocation (the cgroup path):**
```bash
docker run --rm \
  --memory=512m --memory-swap=512m \   # MUST be equal — unequal/unset swap defeats the cap (most common mistake)
  --network=none \                      # no egress
  --read-only \                         # immutable rootfs
  --tmpfs /work:rw,size=64m \           # only writable surface = ephemeral workdir
  --user 65534:65534 \                  # non-root (nobody)
  --cap-drop=ALL \
  --security-opt no-new-privileges \
  --pids-limit=128 \
  --workdir /work \
  python:3.11-slim \                    # pinned base; mount snippet read-only into /work
  python -I /work/snippet.py
```
Wrap with a wall-clock `timeout` (subprocess `timeout=` already exists, `executor.py:69`). **Enforcement assertion:** a snippet that allocates beyond the limit is OOM-killed → exit code **137**.

**Refuse-to-run-unbounded invariant (D-03, closes the fail-open bug):** the executor must NEVER silently continue without a memory cap. Replace the `except (ValueError, OSError): pass` fail-open at `executor.py:49-51`. Behaviour:
- Docker present → run the cgroup path above (real enforcement, even on macOS).
- Docker absent → **raise/refuse** (a clear `SandboxUnavailable` error), NEVER fall back to the unbounded native subprocess.
- Native rlimit rejected (macOS) → also refuse if that were ever the only path; but the design makes Docker the only real path, so rlimit is no longer a fallback at all.

**Two tests (D-03a):**
- **Always-on invariant:** with Docker forced-absent (monkeypatch `shutil.which` → None), `execute_code` **raises/refuses** — asserts it never runs the unbounded subprocess. This runs everywhere including macOS `make test`.
- **Docker-gated enforcement:** `@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not available")` — allocate-beyond-limit snippet → assert exit 137 (OOM). Runs on Linux/CI (and macOS with Docker running).

`make smoke` does not touch the sandbox path, so it stays green on macOS with no Docker.

---

## Architecture Patterns

### System Architecture Diagram

```
Ingress (Slack / MCP / API)
        │  create_task (tenant-scoped)
        ▼
   TaskService ──dispatch──▶ Worker.process(task_id)          [runner.py]
                                   │
                    APPROVED? ─────┤───── fresh run
                       │           │
              resume_mesh          run_mesh(task)              [orchestrator.py]
              (Command(resume))     │
                       │            ▼
                       │   LangGraph StateGraph  (thread_id = task_id)
                       │   ┌─────────────────────────────────────────┐
                       │   │ planner → researcher/tool-router →       │
                       │   │ code-writer → reviewer → write-gate node │
                       │   │   (each node: deepagents harness OR      │
                       │   │    deterministic stub when no creds)     │
                       │   └───────────────┬─────────────────────────┘
                       │                   │ interrupt(proposed_write)
                       │                   ▼
                       │            CHECKPOINTER  (Postgres prod / Sqlite-file test)
                       │            persists paused state ◀── resume loads here
                       ▼                   │
        __interrupt__ → proposed_writes ───┘
                       │
                       ▼
   For each proposed write:  ToolCall + open_approval(signed token)  [approvals.py]
                       │      transition AWAITING_APPROVAL
                       ▼
        /v1/approvals  ──verify_approval_token (FAIL CLOSED)──▶ record_decision
                       │      (approver_id derived from token ONLY — SEC-01)
                       ▼
   Worker resume: is_approved() re-hash (SEC-02a) ──▶ Tool Gateway execute ──▶ COMPLETED
```
The single trusted verification point is `verify_approval_token` at the endpoint; the graph never trusts an identity carried in `Command(resume=...)`.

### Recommended Project Structure
```
src/agent_mesh/worker/
├── orchestrator.py    # run_mesh + NEW resume_mesh; build/compile graph; checkpointer selection
├── graph.py           # NEW: StateGraph builder — 4 declared nodes + write-gate interrupt node, state schema
├── roster.py          # NEW: declared roster (planner/researcher/code-writer/reviewer) + size log; deepagents wiring
└── runner.py          # unchanged approval branch; add the resume_mesh call in _resume_after_approval
src/agent_mesh/sandbox/
└── executor.py        # replace fail-open _preexec with Docker cgroup path + refuse-unbounded
migrations/
└── (PostgresSaver.setup() owns checkpoint tables — sibling schema, not 0003 of app tables)
```

### Pattern 1: Deterministic node under a real graph (D-02)
**What:** Each roster node is a real graph node. It calls the deepagents/model harness only when the stack+creds exist; otherwise it returns a deterministic, role-shaped output. Topology is real; behaviour is stubbed.
**When to use:** All four nodes in Phase 2.
**Example:**
```python
# Source: pattern derived from orchestrator.py stub-fallback + docs.langchain.com/oss/python/deepagents
def planner_node(state: MeshState) -> dict:
    if model_creds_available():           # Phase 3 flips this on via config, not topology
        return _run_deepagents_planner(state)
    return {"plan": f"[stub-plan] {state['prompt'][:80]}", "next": "researcher"}
```

### Pattern 2: Write-gate interrupt node
```python
# Source: docs.langchain.com/oss/python/langgraph/interrupts
from langgraph.types import interrupt
def write_gate_node(state: MeshState) -> dict:
    if not state.get("proposed_writes"):
        return {"done": True}
    decision = interrupt({"proposed_writes": state["proposed_writes"]})  # pauses + checkpoints
    return {"decision": decision}         # decision arrives already-verified via Command(resume=...)
```

### Anti-Patterns to Avoid
- **Executing the write inside a graph tool-node.** Writes execute only in `runner._resume_after_approval` after `is_approved()` — keeps the gate single and re-hashed (SEC-02a).
- **Letting `Command(resume=...)` carry an `approver_id` the graph trusts.** Recreates the SEC-01 bypass. Resume carries only an already-verified decision.
- **Using `InMemorySaver` to prove resume-after-restart.** Memory is what a restart loses; use file-backed Sqlite (test) / Postgres (prod).
- **Thin name-and-route pass-through that defers real delegation** (forbidden by D-02).
- **Native-subprocess fallback when Docker is absent** (fail-open; forbidden by D-03).
- **Equal-omitting `--memory-swap`** — without it the memory cap is defeated by swap.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Durable pause/resume of a long run | Custom task-state snapshotting of graph internals | LangGraph checkpointer (`PostgresSaver`/`SqliteSaver`) | Persists exact graph state incl. interrupt; battle-tested; thread_id cursor |
| Multi-agent delegation harness | Custom subagent dispatcher | `deepagents.create_deep_agent(subagents=[...])` | REQUIRED stack; bounded, declared, no self-spawning |
| In-process memory cap | `RLIMIT_AS` only | Docker `--memory`+equal `--memory-swap` cgroup | rlimit is rejected on macOS and fail-open today; cgroup is real and cross-platform via Docker VM |
| Approval auth | New approval path off the interrupt | Existing `approvals.verify_approval_token` + ledger | Phase 1 already proves SEC-01/SEC-02; a second path weakens it |

**Key insight:** The riskiest temptation is to let the graph "own" approvals because LangGraph makes interrupts easy. Resist it — the interrupt is plumbing; the signed-token ledger is the law.

## Runtime State Inventory

> This is a refactor of the orchestration seam, so the inventory applies.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Existing `tasks`/`approval_records`/`tool_calls` (0001) — unchanged shape. NEW: LangGraph `checkpoints`/`checkpoint_writes`/`checkpoint_blobs` created by `PostgresSaver.setup()` | Code edit (wire checkpointer) + run `.setup()` once per DB; no migration of existing rows |
| Live service config | None — Phase 2 is local/stubbed-model; no external service holds orchestration state | None — verified: model gateway/Langfuse are Phase 3 (deferred) |
| OS-registered state | None — no scheduler/daemon registrations introduced | None — verified: worker is invoked via `make run-worker` / dispatch, not OS-registered |
| Secrets/env vars | `APPROVAL_SIGNING_SECRET` (unchanged, still the gate's key). `DATABASE_URL` now also selects the Postgres checkpointer path | Code reads existing env; no new secret keys. Confirm checkpointer reuses `DATABASE_URL`. |
| Build artifacts / installed packages | `agents` extra pins are stale (pyproject.toml:31-35); a stale lock would resolve wrong APIs | Update pins (deliverable); reinstall `.[agents]` |

## Common Pitfalls

### Pitfall 1: The interrupt becomes a second approval path
**What goes wrong:** A graph tool-node executes the write, or `Command(resume=...)` is trusted to name the approver, bypassing `verify_approval_token`.
**Why it happens:** LangGraph HITL examples often show the decision flowing straight back through `Command(resume=...)`; copying that naively skips the signed-token gate.
**How to avoid:** Verify at the endpoint only; resume carries an already-verified decision; write executes in `_resume_after_approval` under `is_approved()`.
**Warning signs:** `approver_id` read from graph state; Tool Gateway `.execute` called inside a node; a test that approves without a token passes.

### Pitfall 2: `--memory-swap` omitted → memory cap is a no-op
**What goes wrong:** Container swaps past the RAM limit; OOM never fires; the "enforcement" test passes for the wrong reason.
**How to avoid:** Always set `--memory-swap` equal to `--memory`. Assert exit 137 on an over-allocation snippet.
**Warning signs:** Over-allocation snippet exits 0; no 137.

### Pitfall 3: Tenant leakage via the checkpointer
**What goes wrong:** Resuming a `thread_id` without re-loading the task tenant-scoped lets a cross-tenant caller drive another tenant's run.
**Why it happens:** Checkpointer tables key on `thread_id` only — DUR-02 is not automatic.
**How to avoid:** `thread_id = task_id`; always `repo.get_task(task_id)` (tenant-scoped) before resume; never resume a bare thread_id.
**Warning signs:** A resume path that takes a `thread_id` but no tenant context.

### Pitfall 4: `InMemorySaver` used for the restart test
**What goes wrong:** Test "passes" but proves nothing about durability.
**How to avoid:** File-backed Sqlite / Postgres; drop-and-recreate the saver+graph between phases of the test.

### Pitfall 5: Stale pins resolve a different deepagents API
**What goes wrong:** `deepagents>=0.0.2` could (with a constrained index) resolve to a 0.0.x with no `subagents` param; the supervisor wiring fails to import.
**How to avoid:** Pin `~=0.6.8` (and the langgraph 1.x / checkpoint ~=3.1 set) before writing roster code.

## Code Examples

### Compile graph with a checkpointer and invoke with thread_id
```python
# Source: docs.langchain.com/oss/python/langgraph/persistence
from langgraph.checkpoint.postgres import PostgresSaver        # prod
# from langgraph.checkpoint.sqlite import SqliteSaver          # test (file-backed)
checkpointer = PostgresSaver.from_conn_string(database_url)
checkpointer.setup()
graph = builder.compile(checkpointer=checkpointer)
config = {"configurable": {"thread_id": task.task_id}}
result = graph.invoke(initial_state, config)
if "__interrupt__" in result:
    proposed = result["__interrupt__"][0].value["proposed_writes"]  # → OrchestrationResult.proposed_writes
```

### Resume after a (simulated) restart
```python
# Source: docs.langchain.com/oss/python/langgraph/interrupts
from langgraph.types import Command
# fresh process: new saver on the SAME store, new graph, SAME thread_id
graph.invoke(Command(resume=verified_decision), {"configurable": {"thread_id": task.task_id}})
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `langgraph.checkpoint.postgres` in core langgraph | Separate `langgraph-checkpoint-postgres` / `-sqlite` packages | langgraph 0.2→1.x split | Must add the checkpointer package(s) explicitly to the `agents` extra |
| `deepagents` 0.0.x experimental | `create_deep_agent(subagents=[...])` stable at 0.6.8 | through 2026 | The `>=0.0.2` floor is misleading; pin `~=0.6.8` |
| `MemorySaver` naming | `InMemorySaver` (`langgraph.checkpoint.memory`) | langgraph 1.x | Use `InMemorySaver` for same-process unit only |

**Deprecated/outdated:**
- `executor.py:_preexec` `RLIMIT_AS` fail-open — replaced by the Docker cgroup path (SBX-01).
- pyproject `agents` floors `langgraph>=0.2`, `deepagents>=0.0.2` — raise to current.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The auto `general-purpose` subagent in deepagents can be disabled/replaced so roster size == 4 | RF-3 | If not disablable, ORCH-01 startup log reads 5; plan must adjust the assertion or filter the declared four. Verify against 0.6.8 reference in planning. |
| A2 | `create_deep_agent` cannot cleanly accept *your* checkpointer + *your* `interrupt()` placement | RF-3 | Drives the "own the StateGraph" boundary. If deepagents DOES expose clean injection, the own-the-graph boundary is still valid (more control), just not forced. Low risk. |
| A3 | LangSmith is optional-at-runtime (env-gated), not a hard import of deepagents/langgraph | RF-3 | If it were a hard dep it would violate CLAUDE.md; verified-by-design (env gated) but confirm no `import langsmith` at module load. |
| A4 | `PostgresSaver.from_conn_string` / pooled construction reuses `DATABASE_URL` cleanly alongside `RepositorySQL`'s pool | RF-2 | If pool sharing conflicts, use a separate connection for the saver; minor. |

## Open Questions (RESOLVED)

1. **Disable mechanism for the auto general-purpose subagent (A1).**
   - What we know: docs say "added unless disabled or replaced."
   - What's unclear: the exact param/flag at 0.6.8.
   - Recommendation: planner reads reference.langchain.com/python/deepagents at plan time; assert roster size == 4 (filter to declared if needed).
   - **RESOLVED:** defer exact flag name to execution-time reference check; the roster `size == 4` assertion (02-01 Task 2) is the fail-closed guard — failure to disable surfaces as a failing test, not a silent extra subagent.

2. **Checkpointer construction vs. the existing psycopg pool (A4).**
   - What we know: `RepositorySQL` owns a `ConnectionPool` (`repository.py:470`); `PostgresSaver` can take a conn string or pool.
   - Recommendation: simplest correct path is a dedicated saver connection from `DATABASE_URL`; optimize to shared pool only if needed.
   - **RESOLVED:** construct a separate `PostgresSaver` connection via `from_conn_string(DATABASE_URL)`, mirroring the `RepositorySQL.__init__` lazy-import pattern; shared-pool optimization deferred until measured need.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `langgraph` + `deepagents` + checkpointers | Real graph (ORCH-01/02/03) | ✗ (not installed; optional-by-design) | target: lg 1.x / da 0.6.8 / ckpt 3.1 | Deterministic stub path (`langgraph_available()` gate) — `make smoke`/`make test` stay green without them |
| Docker | Hardened sandbox (SBX-01) | ✗ (not detected in sandbox) | — | **No fallback by design (D-03):** refuse to run unbounded; Docker-gated test skips cleanly |
| Postgres (`DATABASE_URL`) | Prod checkpointer | ✗ locally | — | File-backed SqliteSaver for restart-sim; Postgres test env-gated |

**Missing dependencies with no fallback:** Docker for the real SBX-01 enforcement *test* (skips, does not block — D-03a). The refuse-to-run invariant is tested everywhere without Docker.
**Missing dependencies with fallback:** the entire agent stack (stub path) and Postgres (Sqlite-file sim).

## Validation Architecture

> nyquist_validation is not explicitly false in config → section included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8 (pyproject.toml:42), `pythonpath=["src"]`, `testpaths=["tests"]` |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `make test` (`python -m pytest -q`) |
| Full suite command | `make test` + `make smoke` (stub path, no deps) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ORCH-01 | Real graph delegates to 4 declared roster members; size logged | unit (agents-extra gated) | `pytest tests/test_orchestration_graph.py -x` | ❌ Wave 0 |
| ORCH-01 | Stub path still produces `OrchestrationResult` w/o stack | unit (always-on) | `pytest tests/test_orchestration_graph.py::test_stub_fallback -x` | ❌ Wave 0 |
| ORCH-02 | Resume-after-restart via file-backed Sqlite saver | unit (agents-extra gated) | `pytest tests/test_checkpointer_resume.py -x` | ❌ Wave 0 |
| ORCH-02 | Resume-after-restart via real PostgresSaver | integration (`DATABASE_URL` gated) | `DATABASE_URL=... pytest tests/test_checkpointer_resume.py -k postgres` | ❌ Wave 0 |
| ORCH-03 | interrupt() pauses; verified decision resumes; write executes only after is_approved | unit (agents-extra gated) | `pytest tests/test_interrupt_hitl.py -x` | ❌ Wave 0 |
| ORCH-03 | SEC-01/SEC-02 regression still pass through the new path | unit (always-on) | `pytest tests/test_approval_security.py -x` | ✅ exists — must stay green |
| SBX-01 | Executor refuses to run unbounded when Docker absent | unit (always-on) | `pytest tests/test_sandbox.py::test_refuses_unbounded -x` | ❌ Wave 0 |
| SBX-01 | Docker cgroup OOM → exit 137 | integration (Docker gated) | `pytest tests/test_sandbox.py::test_oom_enforced -x` (skip if no docker) | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `make test` (always-on subset runs; gated tests skip cleanly).
- **Per wave merge:** `make test` + `make smoke`; on CI with the `agents` extra + Docker, the gated tests run for real.
- **Phase gate:** full suite green; `test_approval_security.py` (Phase 1 SEC suite) MUST remain green through the new interrupt path.

### Wave 0 Gaps
- [ ] `tests/test_orchestration_graph.py` — covers ORCH-01 (4-node delegation + roster-size log + stub fallback)
- [ ] `tests/test_checkpointer_resume.py` — covers ORCH-02 (Sqlite-file restart-sim always; Postgres `DATABASE_URL`-gated)
- [ ] `tests/test_interrupt_hitl.py` — covers ORCH-03 (interrupt pause → verified resume → write gated)
- [ ] `tests/test_sandbox.py` — covers SBX-01 (refuse-unbounded always; Docker OOM gated)
- [ ] `tests/conftest.py` — add `agents`-extra skip marker + `shutil.which("docker")` skip marker (reuse `repo` fixture)
- [ ] Update `pyproject.toml` `agents` extra pins (langgraph 1.x, ckpt ~=3.1 x2, deepagents ~=0.6.8)

## Security Domain

> `security_enforcement` not explicitly false → included. Phase 2 is security-load-bearing because it touches the approval gate.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Approver identity derived ONLY from HMAC-signed token (`verify_approval_token`, fail-closed) — preserved, not modified |
| V4 Access Control | yes | Tenant scoping (DUR-02) extended to checkpointer reads: `thread_id`=tenant-scoped `task_id`; never resume a bare thread |
| V5 Input Validation | yes | Payload-hash binding (`is_approved` re-hash, SEC-02a) on resume; `Command(resume=...)` carries only a decision, never an identity |
| V6 Cryptography | yes | HMAC-SHA256 token signing (`approvals._sign_approval`) — unchanged; never hand-rolled afresh |
| V12/Sandbox (isolation) | yes | Container isolation: cgroup memory cap, network-off, read-only, non-root, cap-drop; refuse-unbounded invariant |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Interrupt resume forges/asserts approver | Spoofing / Elevation | Resume carries verified decision only; approver from token (SEC-01) |
| Mutated payload after approval | Tampering | `is_approved` re-hash before execute (SEC-02a) |
| Cross-task / cross-tenant resume of a checkpoint | Elevation / Info disclosure | thread_id = tenant-scoped task_id; re-load task tenant-scoped before resume (DUR-02) |
| Sandboxed code exhausts host memory / exfiltrates | DoS / Info disclosure | cgroup `--memory`(+equal swap), `--network=none`, `--read-only`, non-root; refuse if Docker absent |
| Replay of approval token across tasks | Spoofing | Token bound to one `approval_record_id` (SEC-02b) — unchanged |

## Sources

### Primary (HIGH confidence)
- `docs.langchain.com/oss/python/langgraph/persistence` — checkpointer import paths, `PostgresSaver.setup()`, compile/invoke with `thread_id`, restart resume
- `docs.langchain.com/oss/python/langgraph/interrupts` — `interrupt()` (`langgraph.types`), `Command(resume=...)`, `__interrupt__` key, durable-across-restart confirmation
- `docs.langchain.com/oss/python/deepagents/subagents` — `create_deep_agent(subagents=[...])`, subagent dict keys, bounded/no-self-spawn, auto general-purpose note
- `pypi.org/pypi/deepagents/json` — version 0.6.8, repo github.com/langchain-ai/deepagents, no postinstall script
- PyPI version lookups (`pip index versions`) — langgraph 1.2.4, langgraph-checkpoint-postgres 3.1.0, langgraph-checkpoint-sqlite 3.1.0, deepagents 0.6.8, langchain 1.3.4, langchain-core 1.4.0
- Codebase (file:line cited throughout): orchestrator.py, runner.py, executor.py, approvals.py, self_improvement.py, repository.py, lifecycle.py, tests/test_approval_security.py, pyproject.toml, migrations/0001/0002

### Secondary (MEDIUM confidence)
- `docs.langchain.com/oss/python/deepagents/overview` — high-level capabilities; did NOT confirm checkpointer injection / general-purpose disable (→ drives A1/A2 and the own-the-StateGraph boundary)

### Tertiary (LOW confidence)
- None relied upon.

## Metadata

**Confidence breakdown:**
- Standard stack / versions: HIGH — PyPI-verified + official docs; first-party packages.
- Interrupt↔ledger reconciliation (RF-1): HIGH — derived from verified `interrupt()`/`Command` semantics + read SEC-01/SEC-02 code and tests.
- Checkpointer + restart-sim (RF-2): HIGH — verified import paths/`.setup()`; restart-sim mechanism is standard.
- deepagents integration (RF-3): MEDIUM-HIGH — `subagents` API verified; auto general-purpose disable + checkpointer injection are open (A1/A2), mitigated by owning the StateGraph.
- Sandbox (RF-4): HIGH — standard Docker cgroup flags; macOS-via-Docker enforcement is well established.

**Research date:** 2026-06-05
**Valid until:** 2026-07-05 (fast-moving stack — re-verify deepagents/langgraph minor versions before implementation).

## RESEARCH COMPLETE

Phase 2 is well-scoped and unblocked. The verified stack is langgraph 1.x + langgraph-checkpoint-postgres/sqlite ~=3.1 + deepagents ~=0.6.8 (current pyproject pins are stale and must be raised as a deliverable). The single load-bearing decision is the interrupt↔ledger reconciliation (RF-1): the LangGraph `interrupt()` is the durable *pause* mechanism, while the Phase-1 signed-token + payload-hash ledger remains the *decision authority* — the worker's existing `open_approval`/`verify_approval_token`/`is_approved` path fires unchanged, `Command(resume=...)` carries only an already-verified decision, and the write still executes in `runner._resume_after_approval`, preserving SEC-01/SEC-02. Recommend owning the `StateGraph` (4 declared nodes + checkpointer + interrupt) and using `deepagents.create_deep_agent(subagents=[...])` within nodes (auto general-purpose disabled) for guaranteed checkpointer/interrupt control and a trivial deterministic-node stub (D-02). The checkpointer keys on `thread_id` only, so DUR-02 tenant scoping must be enforced at the worker boundary (`thread_id = task_id`, re-load tenant-scoped before resume). Sandbox hardening is a Docker cgroup path (`--memory` with equal `--memory-swap`, `--network=none`, `--read-only`, non-root) that enforces even on macOS via Docker's Linux VM, with a hard refuse-to-run-unbounded invariant tested everywhere and an OOM-exit-137 test gated on `shutil.which("docker")`. Validation gates real-graph/checkpointer/interrupt tests behind the `agents` extra (skip cleanly otherwise) while `make smoke` stays on the stub path, so the no-cloud/no-Docker-on-macOS constraint holds.
