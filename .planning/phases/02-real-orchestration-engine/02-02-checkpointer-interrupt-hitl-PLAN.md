---
phase: 02-real-orchestration-engine
plan: 02
type: execute
wave: 2
depends_on: ["02-01"]
files_modified:
  - src/agent_mesh/worker/graph.py
  - src/agent_mesh/worker/orchestrator.py
  - src/agent_mesh/worker/runner.py
  - tests/test_checkpointer_resume.py
  - tests/test_interrupt_hitl.py
autonomous: true
requirements: [ORCH-02, ORCH-03]
must_haves:
  truths:
    - "A (simulated >60-min) run resumes from its durable checkpoint after a process restart — proven without InMemorySaver and without a real timer"
    - "A proposed write pauses the graph as a LangGraph interrupt and resumes from the checkpoint when the verified decision arrives"
    - "The write executes ONLY in runner._resume_after_approval under is_approved() re-hash; the interrupt is the pause mechanism, the signed-token ledger remains the decision authority"
    - "SEC-01/SEC-02 still hold through the new interrupt/resume path (test_approval_security.py stays green — phase gate)"
  artifacts:
    - path: "src/agent_mesh/worker/graph.py"
      provides: "write-gate node calling interrupt(); graph compiles with a checkpointer"
      contains: "interrupt("
    - path: "src/agent_mesh/worker/orchestrator.py"
      provides: "checkpointer selection (PostgresSaver prod / SqliteSaver-file test) + new resume_mesh(task, decision) with stub-fallback gate"
      contains: "def resume_mesh"
    - path: "src/agent_mesh/worker/runner.py"
      provides: "_resume_after_approval calls resume_mesh; write still executes only here under is_approved()"
      contains: "resume_mesh"
    - path: "tests/test_checkpointer_resume.py"
      provides: "ORCH-02 restart-sim (SqliteSaver-file always-on agents-gated; PostgresSaver env-gated)"
      contains: "SqliteSaver"
    - path: "tests/test_interrupt_hitl.py"
      provides: "ORCH-03 interrupt pause -> verified resume -> write gated; forged-resume rejected"
      contains: "interrupt"
  key_links:
    - from: "src/agent_mesh/worker/graph.py"
      to: "checkpointer"
      via: "builder.compile(checkpointer=...)"
      pattern: "compile\\(checkpointer"
    - from: "src/agent_mesh/worker/runner.py"
      to: "src/agent_mesh/worker/orchestrator.py"
      via: "resume_mesh(task, decision) inside _resume_after_approval"
      pattern: "resume_mesh"
    - from: "src/agent_mesh/worker/runner.py"
      to: "src/agent_mesh/services/approvals.py"
      via: "is_approved() re-hash before Tool Gateway execute (unchanged)"
      pattern: "is_approved"
---

<objective>
Wire the LangGraph Postgres checkpointer so a long (simulated >60-min) run resumes from its
durable checkpoint after a process restart (ORCH-02), and express the write approval as a
LangGraph `interrupt()` that pauses the graph and resumes from the checkpoint when the
decision arrives (ORCH-03).

THE LOAD-BEARING SECURITY DECISION (RF-1): the `interrupt()` is the durable PAUSE mechanism
ONLY. The Phase-1 signed-token + payload-hash ledger (`approvals.py` + `approval_records` +
task state) remains the single DECISION AUTHORITY. The worker's existing approval branch
(`open_approval` → token stash → `AWAITING_APPROVAL`) fires unchanged; the write still
executes ONLY in `runner._resume_after_approval` under `is_approved()` re-hash. `Command(resume=...)`
carries an ALREADY-VERIFIED decision — NEVER an approver_id the graph trusts. Done wrong this
reopens the SEC-01 bypass Phase 1 closed.

Depends on 02-01 (graph.py/roster.py/orchestrator.py topology + raised pins + the
`langgraph_available()` gate must exist first).

Purpose: ORCH-02 (durable resume-after-restart) + ORCH-03 (interrupt-based HITL) without
weakening SEC-01/SEC-02.
Output: write-gate interrupt node + checkpointer in graph.py; checkpointer selection +
resume_mesh in orchestrator.py; resume_mesh call in runner.py; restart-sim and interrupt-HITL tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/02-real-orchestration-engine/02-RESEARCH.md
@.planning/phases/02-real-orchestration-engine/02-PATTERNS.md
@src/agent_mesh/worker/runner.py
@src/agent_mesh/services/approvals.py

<interfaces>
<!-- Contracts the executor must preserve. -->

OrchestrationResult (orchestrator.py:39-45) — resume_mesh returns this too; proposed_writes presence is the paused signal the worker branches on (runner.py:57). resume_mesh returns a TERMINAL result (proposed_writes=[]) so runner completion logic holds.

run_mesh gate established in 02-01 (orchestrator.py:77-79) — branches on langgraph_available(); stub path is the no-stack fallback. resume_mesh MUST mirror this SAME gate (see Task 1).

runner._resume_after_approval(task_id) (runner.py:106-132) — the ONLY place a write executes, gated by approvals.is_approved(record, call.parameters) re-hash (runner.py:116). Tenant-scoped task load via self._repo.get_task (DUR-02). Tool Gateway .execute is called here, never in a graph node.

approvals.verify_approval_token (approvals.py, FAIL CLOSED) — the single trusted verification point; returns the token-derived requester_id as the ONLY trusted approver (SEC-01). Unchanged.
approvals.is_approved (approvals.py) — payload re-hash; mutated payload invalidates approval (SEC-02a). Unchanged.

Lifecycle already supports AWAITING_APPROVAL -> APPROVED -> RUNNING -> COMPLETED (lifecycle.py:26-29). No state-machine change needed — confirm.

LangGraph (verified RF-2):
  from langgraph.checkpoint.postgres import PostgresSaver   # prod; .from_conn_string(url); .setup() idempotent
  from langgraph.checkpoint.sqlite import SqliteSaver       # test; file-backed (NOT :memory:)
  from langgraph.types import interrupt, Command
  config = {"configurable": {"thread_id": task.task_id}}    # thread_id = tenant-scoped task_id (DUR-02)
  result = graph.invoke(state, config); "__interrupt__" in result  -> result["__interrupt__"][0].value["proposed_writes"]
  graph.invoke(Command(resume=verified_decision), config)   # resume on the SAME thread_id
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add the write-gate interrupt node + checkpointer compile + stub-aware resume_mesh</name>
  <files>src/agent_mesh/worker/graph.py, src/agent_mesh/worker/orchestrator.py</files>
  <read_first>
    - src/agent_mesh/worker/graph.py (the 02-01 topology: build_graph + 4 nodes + MeshState — extend it here)
    - src/agent_mesh/worker/orchestrator.py (the 02-01 _run_langgraph that compiles+invokes; the run_mesh langgraph_available() gate at 77-79 — resume_mesh MUST mirror it; OrchestrationResult 39-45)
    - src/agent_mesh/services/repository.py (RepositorySQL.__init__ ~463-477 — lazy optional-driver import + DATABASE_URL/DSN construction + close(); mirror this shape for checkpointer selection)
    - .planning/phases/02-real-orchestration-engine/02-RESEARCH.md (RF-2 checkpointer backend + Code Examples; Pattern 2 write-gate interrupt node; Pitfall 3 tenant scoping; Pitfall 4 no InMemorySaver)
    - .planning/phases/02-real-orchestration-engine/02-PATTERNS.md (orchestrator.py MODIFY section; graph.py write-gate node; Shared Patterns DUR-02 tenant scoping)
  </read_first>
  <behavior>
    - write_gate_node returns {"done": True} when no proposed_writes; otherwise calls interrupt({"proposed_writes": ...}) which pauses + checkpoints, and returns {"decision": <resumed value>} on resume
    - build_graph wires reviewer -> write_gate as the new terminal node
    - orchestrator selects PostgresSaver when DATABASE_URL set (prod), else the test path supplies SqliteSaver-file; graph compiles WITH the checkpointer
    - run_mesh invoke with config thread_id=task.task_id; when paused, "__interrupt__" maps to OrchestrationResult.proposed_writes
    - resume_mesh(task, decision) on the STACK path invokes Command(resume=decision) on the SAME thread_id and returns a TERMINAL OrchestrationResult(proposed_writes=[])
    - resume_mesh on the STUB path (langgraph_available() is False) returns a TERMINAL OrchestrationResult(proposed_writes=[]) WITHOUT importing/invoking langgraph — the stub never paused via interrupt() (it paused via the worker's AWAITING_APPROVAL), so there is nothing to graph-resume
  </behavior>
  <action>
    In graph.py add write_gate_node(state) per Pattern 2: if not state.get("proposed_writes") return
    {"done": True}; else `from langgraph.types import interrupt` and decision = interrupt({"proposed_writes":
    state["proposed_writes"]}); return {"decision": decision}. Wire reviewer -> write_gate as terminal in
    build_graph. The node MUST NOT execute the write and MUST NOT read or trust an approver_id from the
    resumed value (reject anti-patterns: write inside a graph node; Command(resume) carrying a trusted
    approver_id; interrupt() as the approval record).
    In orchestrator.py add a checkpointer selector mirroring RepositorySQL.__init__: lazy-import
    PostgresSaver from langgraph.checkpoint.postgres, construct via PostgresSaver.from_conn_string(DATABASE_URL),
    call .setup() (idempotent, library-owned sibling schema — NOT a hand-written 0003 of app tables), expose
    a close(). Provide a hook so tests can inject a SqliteSaver-file checkpointer. Compile the graph WITH the
    checkpointer (builder.compile(checkpointer=...)). In _run_langgraph invoke with
    config={"configurable": {"thread_id": task.task_id}} (DUR-02: task_id is the tenant-scoped task; never a
    bare thread_id); on "__interrupt__" in result map result["__interrupt__"][0].value["proposed_writes"] to
    OrchestrationResult.proposed_writes.
    Add resume_mesh(task, decision) -> OrchestrationResult that MIRRORS the run_mesh gate: if NOT
    langgraph_available(), return a terminal OrchestrationResult(proposed_writes=[], summary=...) immediately
    WITHOUT importing langgraph.types.Command or touching a checkpointer — the stub path never paused via a graph
    interrupt, so there is nothing to resume (this keeps the always-on _resume_after_approval / SEC suite green).
    On the stack path, invoke Command(resume=decision) on the SAME thread_id and return a terminal
    OrchestrationResult(proposed_writes=[], summary=...). resume carries ONLY the already-verified decision,
    never an approver_id. Do NOT use a blanket try/except ImportError that no-ops on the stack path — branch on
    langgraph_available() exactly like run_mesh. Leave trace_id unset. Do NOT use InMemorySaver anywhere (Pitfall 4).
  </action>
  <verify>
    <automated>grep -c "interrupt(" src/agent_mesh/worker/graph.py</automated>
    <automated>grep -c "def resume_mesh" src/agent_mesh/worker/orchestrator.py</automated>
    <automated>grep -c "langgraph_available" src/agent_mesh/worker/orchestrator.py</automated>
    <automated>grep -c "compile(checkpointer" src/agent_mesh/worker/orchestrator.py</automated>
    <automated>test $(grep -c "InMemorySaver" src/agent_mesh/worker/orchestrator.py src/agent_mesh/worker/graph.py | grep -v ':0$' | wc -l) -eq 0</automated>
    <automated>python -c "import ast; ast.parse(open('src/agent_mesh/worker/graph.py').read()); ast.parse(open('src/agent_mesh/worker/orchestrator.py').read())"</automated>
  </verify>
  <acceptance_criteria>
    - graph.py defines write_gate_node calling `interrupt(` and wired as terminal after reviewer; the node neither executes a write nor reads an approver_id
    - orchestrator.py defines resume_mesh(task, decision) that branches on langgraph_available(): stub path returns a terminal OrchestrationResult(proposed_writes=[]) WITHOUT importing langgraph.types.Command; stack path uses `Command(resume=` on thread_id=task.task_id
    - resume_mesh contains NO blanket `try/except ImportError` that would silently no-op the stack-path resume
    - orchestrator.py compiles the graph with a checkpointer and selects PostgresSaver from DATABASE_URL (with a test-injectable SqliteSaver-file hook)
    - neither graph.py nor orchestrator.py references InMemorySaver
    - thread_id is set to task.task_id (tenant-scoped task), never a bare/arbitrary thread_id
  </acceptance_criteria>
  <done>The write-gate interrupt node pauses+checkpoints; the graph compiles with a Postgres/Sqlite-file checkpointer; resume_mesh mirrors the run_mesh stub gate (terminal no-op on the stub path, Command(resume) on the stack path) so the always-on resume/SEC suite stays green; no InMemorySaver.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Call resume_mesh from runner._resume_after_approval (write still gated by is_approved) + ORCH-03 interrupt-HITL test</name>
  <files>src/agent_mesh/worker/runner.py, tests/test_interrupt_hitl.py</files>
  <read_first>
    - src/agent_mesh/worker/runner.py (the approval branch 57-104 fires UNCHANGED; _resume_after_approval 106-132 — the ONLY place a write executes, under is_approved() at line 116; tenant-scoped get_task at 107)
    - src/agent_mesh/services/approvals.py (verify_approval_token FAIL CLOSED; is_approved re-hash; APPROVAL_TOKENS_METADATA_KEY)
    - tests/test_approval_security.py (the _pause_on_write(repo) helper ~42-57 and forged-approver-rejected case ~135-164 — reuse this exact pattern; this suite is the PHASE GATE and must stay green)
    - src/agent_mesh/worker/orchestrator.py (the stub-aware resume_mesh added in Task 1)
    - .planning/phases/02-real-orchestration-engine/02-RESEARCH.md (RF-1 step 4 resume flow; Pitfall 1 interrupt-as-second-approval-path; Security Domain threat table)
  </read_first>
  <behavior>
    - the existing fresh-run approval branch is unchanged: a mutating prompt -> proposed_writes -> open_approval (signed token) -> AWAITING_APPROVAL
    - on resume, _resume_after_approval re-loads the task tenant-scoped, calls orchestrator.resume_mesh(task, decision) with an already-verified decision, then executes each approved-and-unmodified write via the Tool Gateway under is_approved()
    - on the stub env (no agents stack) resume_mesh is a terminal no-op and the existing is_approved() execute loop still completes the task (always-on path stays green)
    - a forged/self-asserted approver via Command(resume) cannot approve — the approver is derived ONLY from the verified token (SEC-01)
    - a mutated payload after approval invalidates execution (SEC-02a) — write does not run
    - resume never executes a write inside a graph node
  </behavior>
  <action>
    In runner._resume_after_approval: after the tenant-scoped get_task and before/around the existing
    is_approved() execute loop (runner.py:110-127), call orchestrator.resume_mesh(task, decision) so the
    paused graph runs to terminal. `decision` is a single already-verified boolean (use True): the task is in
    APPROVED only because verify_approval_token + record_decision already ran at the endpoint, and the
    write_gate node only RELEASES the interrupt — it never executes the write, so a single graph-level
    decision=True is correct and the real per-call gate stays approvals.is_approved() in this method. Do NOT
    thread per-call decisions into the single graph resume; do NOT pass an approver_id into resume. The Tool
    Gateway .execute MUST stay inside _resume_after_approval, gated by approvals.is_approved(record,
    call.parameters) (line 116) — unchanged. Import resume_mesh from agent_mesh.worker.orchestrator. Do NOT add
    a new approval path off the interrupt; do NOT trust any identity carried in the resumed value.
    Create tests/test_interrupt_hitl.py using the test_approval_security.py _pause_on_write pattern:
    (1) create+process a mutating task -> assert AWAITING_APPROVAL and a worker-issued token exists;
    (2) approve via the legitimate verified path -> process again -> assert COMPLETED and the write executed;
    (3) FORGED-RESUME case: a resume carrying a self-asserted approver_id does NOT cause approval — assert the
    recorded approver is the token-derived id, never the body-supplied one (SEC-01); (4) MUTATED-PAYLOAD case:
    mutate call.parameters after approval -> assert is_approved() is False and the write does not execute (SEC-02a).
    Use the `repo` fixture; gate any real-graph resume assertion behind the conftest `agents_stack` fixture but
    keep the SEC-01/SEC-02 invariant assertions always-on (they exercise the ledger, not the stack).
  </action>
  <verify>
    <automated>grep -c "resume_mesh" src/agent_mesh/worker/runner.py</automated>
    <automated>grep -c "is_approved" src/agent_mesh/worker/runner.py</automated>
    <automated>python -m pytest -q tests/test_interrupt_hitl.py -x</automated>
    <automated>python -m pytest -q tests/test_approval_security.py -x</automated>
    <automated>python -m pytest -q tests/ -x</automated>
  </verify>
  <acceptance_criteria>
    - runner.py calls orchestrator.resume_mesh(task, decision) inside _resume_after_approval and still gates the Tool Gateway execute on approvals.is_approved (line ~116 unchanged)
    - runner.py does NOT pass an approver_id into resume_mesh and does NOT execute a write outside _resume_after_approval
    - tests/test_interrupt_hitl.py asserts: forged/self-asserted approver via resume is rejected (approver derived from token only — SEC-01); mutated payload invalidates execution (SEC-02a)
    - `python -m pytest -q tests/test_approval_security.py` exits 0 in THIS env with no agents stack installed (PHASE GATE — SEC-01/SEC-02 hold through the new path; resume_mesh stub no-op keeps it green)
    - `python -m pytest -q tests/` exits 0 in this env (agents-gated assertions skip cleanly)
  </acceptance_criteria>
  <done>resume_mesh resumes the paused graph from the worker (terminal no-op on the stub env), the write still executes only under is_approved() in the worker, the interrupt is never a second approval path, and SEC-01/SEC-02 stay green through the new flow.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: ORCH-02 resume-after-restart test (SqliteSaver-file always-on + PostgresSaver env-gated)</name>
  <files>tests/test_checkpointer_resume.py</files>
  <read_first>
    - tests/test_repository_sql.py (test_restart_survival_all_four_state_families ~70-120 — the drop-then-reopen-same-store restart proof; the pg_dsn env-gating ~98-100 — mirror BOTH)
    - tests/conftest.py (the agents_stack fixture from 02-01 and the pg_dsn fixture — reuse)
    - src/agent_mesh/worker/orchestrator.py (the checkpointer selector + resume_mesh + the SqliteSaver-file injection hook from Task 1)
    - .planning/phases/02-real-orchestration-engine/02-RESEARCH.md (RF-2 exact restart-simulation mechanism steps 1-4; Pitfall 4 no InMemorySaver; Validation Architecture ORCH-02 rows)
    - .planning/phases/02-real-orchestration-engine/02-PATTERNS.md (test_checkpointer_resume.py section — the analog drop/reopen snippet)
  </read_first>
  <behavior>
    - SqliteSaver-file restart-sim (agents_stack-gated, no DB): open SqliteSaver on a tempfile, invoke graph to the interrupt (paused long run), DROP graph+saver (simulated process death), open a FRESH SqliteSaver on the SAME tempfile + fresh graph, invoke Command(resume=decision) on the SAME thread_id, assert it resumes from the persisted checkpoint and reaches terminal
    - PostgresSaver restart-sim (pg_dsn/TEST_DATABASE_URL-gated): the same drop/reopen against real PostgresSaver
    - NEVER InMemorySaver (it loses exactly what a restart loses)
  </behavior>
  <action>
    Create tests/test_checkpointer_resume.py. Always-on (agents_stack-gated) test test_resume_after_restart_sqlite:
    use tempfile.NamedTemporaryFile/TemporaryDirectory for the Sqlite path; `from langgraph.checkpoint.sqlite
    import SqliteSaver`; compile build_graph() with that saver; invoke with thread_id=T and a mutating prompt so
    the run pauses at the interrupt; assert "__interrupt__" present (paused). Then DROP the graph+saver objects
    (del / leave the with-block) to simulate process death; open a FRESH SqliteSaver on the SAME file + a fresh
    compiled graph; invoke Command(resume=<verified decision>) on the SAME thread_id=T; assert the graph resumes
    and reaches terminal state. Env-gated test test_resume_after_restart_postgres using the pg_dsn fixture:
    `from langgraph.checkpoint.postgres import PostgresSaver`, .from_conn_string(pg_dsn), .setup(), same
    drop/reopen-same-DSN proof. Do NOT use InMemorySaver. Add a DUR-02 assertion comment/check: the resume uses
    thread_id == the tenant-scoped task_id (never a bare thread_id).
  </action>
  <verify>
    <automated>grep -c "SqliteSaver" tests/test_checkpointer_resume.py</automated>
    <automated>test $(grep -c "InMemorySaver" tests/test_checkpointer_resume.py) -eq 0</automated>
    <automated>python -m pytest -q tests/test_checkpointer_resume.py -x</automated>
    <automated>python -m pytest -q tests/ -x</automated>
  </verify>
  <acceptance_criteria>
    - tests/test_checkpointer_resume.py uses file-backed SqliteSaver (not :memory:) and contains NO InMemorySaver
    - the restart-sim drops the saver+graph and reopens a FRESH saver on the SAME store before resuming on the SAME thread_id (mirrors test_repository_sql drop/reopen)
    - the SqliteSaver test SKIPS cleanly when the agents stack is absent; the PostgresSaver test SKIPS cleanly when TEST_DATABASE_URL is unset
    - `python -m pytest -q tests/` exits 0 in this env (both gated tests skip cleanly)
  </acceptance_criteria>
  <done>ORCH-02 is proven by a SqliteSaver-file restart simulation (and an env-gated PostgresSaver mirror) that drops and reopens the store on the same thread_id without InMemorySaver and without a real timer.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| approval endpoint → worker | `/v1/approvals` / MCP verifies the signed token (single trusted verification point) |
| Command(resume=...) → graph | the resumed value crosses into the graph; it MUST carry only a verified decision, never identity |
| checkpointer store ↔ thread_id | checkpoints key on thread_id only; tenant scope is NOT free |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-02-02-01 | Spoofing / Elevation | forged/self-asserted approver via `Command(resume=...)` | mitigate | resume carries an already-verified decision only (a bare boolean); approver derived ONLY from `verify_approval_token` (FAIL CLOSED, SEC-01); graph never reads an approver_id. Test asserts the forged case is rejected. |
| T-02-02-02 | Tampering | mutated tool-call payload after approval | mitigate | write executes only in `runner._resume_after_approval` under `approvals.is_approved()` re-hash (SEC-02a); mutated payload → no execution. Test asserts it. |
| T-02-02-03 | Elevation / Info disclosure | cross-tenant / cross-task resume of a checkpoint | mitigate | `thread_id = task_id` where the task is loaded tenant-scoped (`repo.get_task`); never resume a bare thread_id (DUR-02). Token bound to one approval_record_id blocks cross-task replay (SEC-02b, unchanged). |
| T-02-02-04 | Tampering / Spoofing | interrupt() treated as the approval record (second weaker path) | mitigate | interrupt() is the pause mechanism only; the signed-token ledger is the decision authority; no Tool Gateway `.execute` inside any graph node. Pitfall 1 anti-patterns rejected in review. |
| T-02-02-05 | Repudiation | resume-after-restart loses durable state | mitigate | PostgresSaver (prod) / file-backed SqliteSaver (test); InMemorySaver forbidden (loses exactly what a restart loses). Restart-sim test proves durable resume. |
| T-02-02-06 | Tampering | resume silently no-ops on the stack path (e.g. blanket try/except ImportError) defeating ORCH-03 | mitigate | resume_mesh branches on `langgraph_available()` exactly like run_mesh; no blanket ImportError swallow; stub no-op is reachable ONLY when the stack is genuinely absent. Acceptance criterion forbids the try/except pattern. |

**Phase gate:** `tests/test_approval_security.py` (Phase 1 SEC-01/SEC-02 suite) MUST stay green through the new interrupt/resume path. Block on any HIGH-severity regression.
</threat_model>

<verification>
- `python -m pytest -q tests/test_approval_security.py` exits 0 in this env (no agents stack) — SEC-01/SEC-02 hold through the new path; the resume_mesh stub no-op keeps it green (phase gate).
- `python -m pytest -q tests/` exits 0 in this env; agents-gated and TEST_DATABASE_URL-gated tests skip cleanly.
- `make smoke` stays green (stub path untouched).
- No InMemorySaver anywhere; resume always on thread_id == tenant-scoped task_id.
- The write executes only in runner._resume_after_approval under is_approved(); no write inside a graph node.
- resume_mesh branches on langgraph_available() (no blanket ImportError swallow).
</verification>

<success_criteria>
ORCH-02 satisfied: a simulated >60-min run resumes from its durable Postgres/Sqlite-file checkpoint after a process restart. ORCH-03 satisfied: a proposed write pauses the graph as a LangGraph interrupt and resumes from the checkpoint when the verified decision arrives — with SEC-01/SEC-02 preserved (the ledger is the decision authority, the interrupt is the pause mechanism, the write executes only in the worker under is_approved()).
</success_criteria>

<output>
Create `.planning/phases/02-real-orchestration-engine/02-02-SUMMARY.md` when done.
</output>
