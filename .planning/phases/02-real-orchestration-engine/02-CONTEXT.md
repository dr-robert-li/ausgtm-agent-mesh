# Phase 2: Real Orchestration Engine - Context

**Gathered:** 2026-06-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the orchestration stub with a **real LangGraph supervisor** delegating to a
**bounded Deep Agents roster** (planner, researcher/tool-router, code-writer, reviewer),
persist graph state in a **Postgres checkpointer** so long runs resume after restart,
express write approvals as **LangGraph interrupts** (pause graph → resume from checkpoint
on decision), and **harden the prompt-to-code sandbox** (non-fail-open memory limit +
hardened container path).

**Proven against the STUBBED model path.** Real agent behaviour against real models is
first exercised in Phase 3/5. Phase 2 proves *topology, checkpointing, and interrupts* —
not real-model behaviour.

Maps to: ORCH-01, ORCH-02, ORCH-03, SBX-01.
Plans (from ROADMAP): 02-01 supervisor+roster (ORCH-01); 02-02 checkpointer+interrupt
HITL (ORCH-02, ORCH-03); 02-03 hardened sandbox (SBX-01).

</domain>

<decisions>
## Implementation Decisions

### P2/P3 Sequencing
- **D-01:** **Keep the layering** — durability → orchestration → model plane. Phase 2
  runs the real graph against a stubbed/deterministic model path; no model credentials
  or live gateway required to pass Phase 2. Do NOT pull Phase 3's live model gateway
  forward. (ROADMAP explicitly offered the P2↔P3 swap; user declined it.)

### Roster Realness Under the Stubbed Model
- **D-02:** **Real graph, deterministic node outputs.** Build the actual LangGraph
  supervisor graph with the four declared roster nodes (planner, researcher/tool-router,
  code-writer, reviewer). Each node executes for real and emits *deterministic* output
  instead of calling a model. The delegation path is genuinely exercised and the roster
  size is logged at startup (ORCH-01). Swapping in real models in Phase 3 should be a
  configuration change, not a topology rebuild. Avoid a thin name-and-route
  pass-through that defers the real delegation topology to later.

### Sandbox Hardening (local dev = macOS)
- **D-03:** **Docker required for sandbox execution.** The hardened container path
  (cgroup memory limit) is the only real execution path. The executor must **never run
  unbounded**: on `RLIMIT_AS` rejection (macOS rejects it — see current `executor.py`
  `_preexec` comment) or absent Docker, the sandbox **refuses/skips** rather than failing
  open. This directly satisfies criterion 4 ("hardened container path") and closes the
  current fail-open bug.
- **D-03a (implication for the test suite — confirm in planning):** Because `make test`
  / `make smoke` must stay green on macOS with no cloud/Docker deps (CLAUDE.md), the
  sandbox memory-enforcement test should **skip cleanly** when Docker is unavailable
  (pytest skip + clear message), and assert real cgroup enforcement wherever Docker
  exists (Linux/CI). The non-negotiable invariant tested everywhere: the executor
  **refuses to run unbounded** — it never silently fails open.

### Claude's Discretion
- Checkpointer backend choice and the exact restart-simulation mechanism (see research
  focus #2) are left to research + planning, within the constraint that the durable
  prod path is the **Postgres checkpointer** over the existing migrations.
- Internal node/state-schema shape of the LangGraph supervisor (researcher/planner).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Normative design
- `CLAUDE.md` §1–§3 — required stack (LangChain + LangGraph + Deep Agents REQUIRED;
  LangSmith never a dependency), bounded supervisor-orchestrated roster (no uncontrolled
  self-spawning), LangGraph owns durability, approval = LangGraph interrupt.
- `CLAUDE.md` §8 "Guardrails that survive every phase" — write-approval gate
  (payload-hash bound), no runtime autonomous self-modification, bounded declared roster.

### Phase scope & requirements
- `.planning/ROADMAP.md` §"Phase 2: Real Orchestration Engine" — goal, the **P2↔P3
  swap note** (intentionally declined per D-01), success criteria, 3 plans.
- `.planning/REQUIREMENTS.md` — ORCH-01, ORCH-02, ORCH-03, SBX-01 (verbatim acceptance).

### Code seams to replace (this phase's surface area)
- `src/agent_mesh/worker/orchestrator.py` — the stub. `_run_langgraph` currently returns
  `_run_stub`; `langgraph_available()`/`deep_agents_available()` gates already exist.
  Real supervisor goes here. `OrchestrationResult` shape is the framework-agnostic
  contract the worker consumes — preserve it.
- `src/agent_mesh/worker/runner.py` — current approval gating (`Worker.process` /
  `_resume_after_approval`) models the pause via `TaskState.AWAITING_APPROVAL` + return,
  with signed-token issuance stashed in task metadata
  (`approvals.APPROVAL_TOKENS_METADATA_KEY`). The LangGraph interrupt must reconcile
  with THIS flow (research focus #1).
- `src/agent_mesh/sandbox/executor.py` — `_preexec` fails open on `RLIMIT_AS`
  (the line D-03 fixes); `SandboxLimits.max_memory_mb` default 512; `propose_patch`
  keeps `approval_required=True`.
- `src/agent_mesh/services/approvals.py` — signed approval-token issue/verify, payload
  hash binding, replay/mutation guards (Phase 1, SEC-01/SEC-02). The interrupt resume
  must bind through this, not bypass it.
- `pyproject.toml` — `agents` extra (langchain>=0.3, langgraph>=0.2, deepagents>=0.0.2)
  and `runtime` extra (psycopg, langfuse, etc.). Stack is optional-by-design so the POC
  stays importable; the stub fallback pattern must be preserved.

### Self-improvement coupling (don't break)
- `src/agent_mesh/services/self_improvement.py` — already adapts to the approval-token
  tuple API (per Phase 1 work); verify the new interrupt/resume path doesn't regress it.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `OrchestrationResult` dataclass (`orchestrator.py`): stable return contract
  (summary / proposed_writes / evidence / trace_id) consumed by `runner.py`, the
  approval ledger, and tests. Real graph must keep producing it.
- `langgraph_available()` / `deep_agents_available()` import guards already exist —
  reuse for the stub-fallback degradation, don't reinvent.
- Phase-1 approval machinery (`approvals.py`): signed-token issue/verify + payload-hash
  binding + replay guard is done and tested — the interrupt path consumes it.
- `Repository` protocol + `RepositorySQL` over `0001`/`0002` migrations: tenant-scoped,
  durable. The LangGraph Postgres checkpointer should live alongside these migrations.

### Established Patterns
- **Stub-fallback degradation:** every heavy-stack seam degrades to a deterministic stub
  when the optional dep / credential is absent, so `make test`/`make smoke` run with no
  cloud deps. The real graph (D-02) must retain a deterministic path that works without
  model creds — that IS the Phase 2 test surface.
- **Approval = durable pause that survives restart:** current flow already targets this
  via task-state + durable token; Phase 2 upgrades the *mechanism* to a LangGraph
  interrupt without changing the durability guarantee or the signed-token contract.
- **Tenant scoping on all reads** (DUR-02) — any new checkpointer/graph reads must stay
  tenant-scoped.

### Integration Points
- `runner.py` ↔ `orchestrator.py`: the worker calls `run_mesh(task)`; the interrupt/
  resume reconciliation (research #1) decides whether the graph or the worker remains
  the approval source-of-truth.
- Checkpointer ↔ Postgres migrations (`RepositorySQL`).
- Sandbox executor ↔ `propose_patch` ↔ approval gate (no auto-apply).

</code_context>

<specifics>
## Specific Ideas

**Research focus for gsd-phase-researcher (architecture/risk — resolve before planning):**

1. **Interrupt ↔ Phase-1 ledger binding (HIGHEST PRIORITY).** How does a LangGraph
   `interrupt()` for a write approval bind to the existing signed-token + payload-hash
   approval ledger (`approvals.py`) and the current `runner.py` AWAITING_APPROVAL/resume
   flow? Decide the source-of-truth: graph interrupt vs. existing worker/task-state flow.
   Must preserve SEC-01/SEC-02 guarantees (forged approver rejected; mutated payload
   invalidates approval; no cross-task replay).

2. **Checkpointer backend + restart-simulation.** Postgres checkpointer (durable/prod)
   over existing migrations; pick the backend lib (e.g. `langgraph-checkpoint-postgres`)
   and how local tests prove resume-after-restart — criterion #2 explicitly blesses a
   *"simulated >60-min"* run, so no real 60-min wait. Confirm what stands in for Postgres
   in `make test` (and whether a lightweight checkpointer is acceptable for the unit path
   while Postgres is the prod path).

3. **`deepagents>=0.0.2` stability/version risk.** Early/unstable package. Confirm the
   API surface needed for the bounded roster is stable enough; identify the minimal
   integration and a pinned version. (Deep Agents is REQUIRED per CLAUDE.md — this is a
   how-to-integrate-safely question, not a whether-to-use question.)

4. **Hardened container path on macOS.** Confirm the Docker invocation (image, cgroup
   `--memory`, network-off, read-only, non-root, timeouts) and the clean
   refuse/skip behaviour when Docker is absent. macOS rejects `RLIMIT_AS`, so rlimit is
   NOT a valid local enforcement fallback.

</specifics>

<deferred>
## Deferred Ideas

- **Real-model agent behaviour** (live LiteLLM gateway, real delegation against models) —
  Phase 3/5, per D-01 (P2↔P3 swap declined).
- **Langfuse trace wiring of graph spans** (`OrchestrationResult.trace_id`) — Phase 3
  (OBS-01/OBS-02). Phase 2 may leave `trace_id` unset/stubbed.
- **Production sandbox isolation** (gVisor/Cloud Run Job, signed images, default-deny
  egress) — production hardening (caveats), out of v1 scope.

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 2-real-orchestration-engine*
*Context gathered: 2026-06-05*
