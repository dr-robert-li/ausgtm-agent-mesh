---
phase: 02-real-orchestration-engine
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  - src/agent_mesh/worker/orchestrator.py
  - src/agent_mesh/worker/graph.py
  - src/agent_mesh/worker/roster.py
  - tests/conftest.py
  - tests/test_orchestration_graph.py
autonomous: true
requirements: [ORCH-01]
must_haves:
  truths:
    - "A task runs through a real LangGraph StateGraph that delegates planner -> researcher/tool-router -> code-writer -> reviewer"
    - "The declared roster has exactly four members and its size (4) is logged at startup"
    - "With the agents stack absent, run_mesh still returns an OrchestrationResult via the deterministic stub path (make test / make smoke stay green on macOS, no cloud deps)"
  artifacts:
    - path: "src/agent_mesh/worker/graph.py"
      provides: "StateGraph builder with 4 declared role nodes + state schema (topology only; no checkpointer/interrupt yet)"
      contains: "def build_graph"
      min_lines: 40
    - path: "src/agent_mesh/worker/roster.py"
      provides: "Declared bounded roster (4 members) + startup size log + deepagents wiring"
      contains: "create_deep_agent"
      min_lines: 30
    - path: "src/agent_mesh/worker/orchestrator.py"
      provides: "_run_langgraph compiles+invokes the real graph; OrchestrationResult contract preserved"
      contains: "build_graph"
    - path: "pyproject.toml"
      provides: "Raised agents-extra pins (langgraph 1.x, checkpoint x2, deepagents ~=0.6.8)"
      contains: "deepagents~=0.6.8"
    - path: "tests/test_orchestration_graph.py"
      provides: "ORCH-01 coverage (4-node delegation + roster-size log, agents-gated; always-on stub fallback)"
      contains: "test_stub_fallback"
  key_links:
    - from: "src/agent_mesh/worker/orchestrator.py"
      to: "src/agent_mesh/worker/graph.py"
      via: "build_graph().compile().invoke()"
      pattern: "build_graph"
    - from: "src/agent_mesh/worker/graph.py"
      to: "src/agent_mesh/worker/roster.py"
      via: "nodes delegate to declared roster"
      pattern: "roster"
---

<objective>
Replace the orchestration stub's placeholder `_run_langgraph` with a REAL LangGraph
`StateGraph` whose four declared nodes (planner, researcher/tool-router, code-writer,
reviewer) genuinely execute and delegate, while emitting deterministic outputs (no model
calls — D-01/D-02). Declare the bounded Deep Agents roster, disable the auto
general-purpose subagent so roster size == 4, and log that size at startup. Raise the
stale `agents`-extra pins to the verified current set.

This plan delivers TOPOLOGY ONLY. The Postgres checkpointer and the write-gate
`interrupt()` are added in 02-02 — do NOT wire a checkpointer or `interrupt()` here.

Purpose: ORCH-01 — a real supervisor graph delegating to a bounded, declared, observable
roster, proven against the stubbed model path so swapping real models in Phase 3 is a
config change, not a topology rebuild.
Output: graph.py, roster.py, modified orchestrator.py, raised pyproject pins, conftest
agents-extra skip marker, and tests/test_orchestration_graph.py.
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

<interfaces>
<!-- Contracts the executor must preserve. Extracted from the codebase. -->

OrchestrationResult (src/agent_mesh/worker/orchestrator.py:39-45) — preserve this dataclass shape exactly:
  summary: str
  proposed_writes: list[dict] = field(default_factory=list)
  evidence: list[str] = field(default_factory=list)
  trace_id: str | None = None     # leave UNSET in Phase 2 (Langfuse = Phase 3)

Existing stub-fallback gates to REUSE, not reinvent (orchestrator.py:48-67):
  langgraph_available() -> bool      # load-bearing import gate
  deep_agents_available() -> bool

run_mesh(task: TaskRecord) -> OrchestrationResult   # public entry; branches on langgraph_available()

deepagents verified API surface (RESEARCH RF-3, docs.langchain.com/oss/python/deepagents/subagents):
  create_deep_agent(model=..., subagents=[<dict>, ...])
  each subagent dict: {"name": str, "description": str, "system_prompt": str, "tools": [...], "model": "provider:model"}
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Raise stale agents-extra pins + add agents-extra skip marker to conftest</name>
  <files>pyproject.toml, tests/conftest.py</files>
  <read_first>
    - pyproject.toml (the `[project.optional-dependencies]` `agents` block, lines 31-35, and `runtime` block 18-27 — psycopg already present)
    - tests/conftest.py (the `pg_dsn` skip-when-unset fixture, lines 65-78 — mirror its skip-cleanly shape)
    - src/agent_mesh/worker/orchestrator.py (langgraph_available / deep_agents_available, lines 48-67 — the marker REUSES these, does not re-derive an import probe)
    - .planning/phases/02-real-orchestration-engine/02-RESEARCH.md (Standard Stack table + "Installation" block — the exact pin set)
  </read_first>
  <action>
    In pyproject.toml replace the stale `agents` extra (currently langchain>=0.3, langgraph>=0.2,
    deepagents>=0.0.2) with the verified current set: langchain>=1.0, langgraph>=1.0,<2,
    langgraph-checkpoint-postgres~=3.1, langgraph-checkpoint-sqlite~=3.1, deepagents~=0.6.8.
    Include BOTH checkpoint packages now even though 02-02 consumes them, so 02-02 never edits
    pyproject. Do NOT add langsmith to any extra (CLAUDE.md: never a dependency). Leave the
    `runtime` extra (psycopg[binary]>=3.1, psycopg-pool>=3.2) unchanged — PostgresSaver reuses them.
    In tests/conftest.py add a fixture `agents_stack` mirroring the `pg_dsn` skip shape: it calls
    orchestrator.langgraph_available() and orchestrator.deep_agents_available() and, when either is
    False, pytest.skip("agents extra not installed; real-graph tests require .[agents]"). Import
    from agent_mesh.worker.orchestrator — reuse the existing gates, do not write a new import probe.
  </action>
  <verify>
    <automated>grep -v '^#' pyproject.toml | grep -c 'deepagents~=0.6.8'</automated>
    <automated>grep -v '^#' pyproject.toml | grep -c 'langgraph-checkpoint-postgres~=3.1'</automated>
    <automated>python -c "import ast,sys; ast.parse(open('tests/conftest.py').read())"</automated>
    <automated>python -m pytest -q tests/ -x</automated>
  </verify>
  <acceptance_criteria>
    - pyproject.toml `agents` extra contains all five: langchain>=1.0, langgraph>=1.0,<2, langgraph-checkpoint-postgres~=3.1, langgraph-checkpoint-sqlite~=3.1, deepagents~=0.6.8
    - pyproject.toml contains no occurrence of `langsmith` and no `deepagents>=0.0.2` / `langgraph>=0.2` floors
    - tests/conftest.py defines an `agents_stack` fixture that calls orchestrator.langgraph_available()/deep_agents_available() and pytest.skip()s cleanly when absent
    - `python -m pytest -q tests/` exits 0 in this env (agents stack absent → existing suite unaffected)
  </acceptance_criteria>
  <done>agents-extra pins raised to the verified set; conftest has a clean-skip agents_stack marker reusing the existing gates; existing suite stays green with no agents stack installed.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Build the declared bounded roster + the real StateGraph topology</name>
  <files>src/agent_mesh/worker/roster.py, src/agent_mesh/worker/graph.py</files>
  <read_first>
    - src/agent_mesh/worker/orchestrator.py (the stub-fallback gate shape at 48-79 and the deterministic _run_stub at 82-102 — graph nodes mirror this `if available(): real else: deterministic` shape)
    - .planning/phases/02-real-orchestration-engine/02-RESEARCH.md (RF-3 deepagents API + the two A1/Open-Question-1 risks; Pattern 1 deterministic-node-under-real-graph)
    - .planning/phases/02-real-orchestration-engine/02-PATTERNS.md (graph.py and roster.py "NEW, no analog" sections; Shared Patterns "Optional-dep stub-fallback degradation")
    - CLAUDE.md §1-§3 (bounded supervisor-orchestrated roster, no self-spawning; LangSmith never a dependency)
  </read_first>
  <behavior>
    - roster declares exactly 4 members: planner, researcher (researcher/tool-router), code_writer, reviewer
    - roster exposes a size accessor returning 4 and logs "roster size 4" (or equivalent ROSTER_SIZE=4) at startup/build
    - the deepagents create_deep_agent call disables/replaces the auto general-purpose subagent so the effective roster is 4 not 5
    - graph.build_graph() returns an uncompiled StateGraph with nodes wired planner -> researcher -> code_writer -> reviewer (terminal); each node executes for real and returns deterministic role-shaped output when model creds absent
    - graph state schema carries at least: prompt, plan, research, code, review, proposed_writes
  </behavior>
  <action>
    Create src/agent_mesh/worker/roster.py: declare the four members as create_deep_agent subagent
    dicts (name/description/system_prompt; model optional — Phase 3 swaps it in). Provide
    ROSTER = [planner, researcher, code_writer, reviewer], a roster_size() -> int returning 4, and a
    build_roster() that calls deepagents.create_deep_agent(subagents=ROSTER) ONLY when
    deep_agents_available(); it MUST disable the auto general-purpose subagent so the effective count
    is 4. A1/Open-Question-1: the exact 0.6.8 disable mechanism is unverified — at execution time
    consult the deepagents 0.6.8 reference (reference.langchain.com/python/deepagents or the installed
    package) to confirm the disable param/flag; do NOT guess a flag name. Assert the effective roster
    size == 4 and log it (logging.getLogger(__name__).info) at build time. Do NOT import or enable
    LangSmith; do not set LANGCHAIN_TRACING_V2 / LANGSMITH_API_KEY.
    Create src/agent_mesh/worker/graph.py: define a MeshState TypedDict (prompt, plan, research, code,
    review, proposed_writes) and node functions planner_node, researcher_node, code_writer_node,
    reviewer_node. Each follows Pattern 1: if model creds available, delegate via the roster harness;
    else return deterministic role-shaped output (e.g. {"plan": f"[stub-plan] {state['prompt'][:80]}"}).
    The reviewer node derives proposed_writes from the prompt using the SAME write-trigger heuristic as
    orchestrator._run_stub (create/update/send/publish/invoice/commit/delete) so the approval path is
    exercised. Provide build_graph() -> StateGraph wiring planner->researcher->code_writer->reviewer
    with reviewer terminal. Do NOT add a checkpointer, do NOT add an interrupt() node, do NOT add a
    write-gate node — those are 02-02. Avoid a thin name-and-route pass-through (forbidden by D-02):
    nodes must read upstream state and produce role-distinct output.
  </action>
  <verify>
    <automated>python -c "import ast; ast.parse(open('src/agent_mesh/worker/roster.py').read()); ast.parse(open('src/agent_mesh/worker/graph.py').read())"</automated>
    <automated>grep -c "def build_graph" src/agent_mesh/worker/graph.py</automated>
    <automated>grep -c "create_deep_agent" src/agent_mesh/worker/roster.py</automated>
  </verify>
  <acceptance_criteria>
    - roster.py defines ROSTER with exactly 4 members and roster_size() returns 4 (source-assertable)
    - roster.py logs the roster size at build (grep for an `.info(` call referencing size/4)
    - roster.py contains no `import langsmith` and does not set LANGCHAIN_TRACING_V2
    - graph.py defines build_graph() returning a StateGraph with nodes planner/researcher/code_writer/reviewer; reviewer is terminal
    - graph.py contains NO `interrupt(` and NO `checkpointer` reference (those are 02-02)
    - each node returns deterministic output when creds absent (no model call on the stub path)
  </acceptance_criteria>
  <done>The declared bounded 4-member roster and the real 4-node StateGraph topology exist; nodes execute deterministically without model creds; roster size 4 is logged; no checkpointer/interrupt present.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Wire orchestrator._run_langgraph to the real graph + ORCH-01 test</name>
  <files>src/agent_mesh/worker/orchestrator.py, tests/test_orchestration_graph.py</files>
  <read_first>
    - src/agent_mesh/worker/orchestrator.py (preserve OrchestrationResult 39-45 and the langgraph_available gate 77-79; replace the _run_langgraph placeholder 105-122 that currently returns _run_stub)
    - src/agent_mesh/worker/graph.py and roster.py (the build_graph + roster API created in Task 2)
    - tests/test_stack_and_toolpacks.py (assert-contract-when-stack-present shape — analog)
    - tests/test_approval_gating.py (worker-flow helper shape — analog for the OrchestrationResult assertions)
    - .planning/phases/02-real-orchestration-engine/02-RESEARCH.md (Validation Architecture → ORCH-01 test rows: real-graph agents-gated + always-on stub fallback)
  </read_first>
  <behavior>
    - test_stub_fallback (always-on, no agents stack): run_mesh(task) returns an OrchestrationResult with a summary; a mutating-verb prompt yields proposed_writes; runs green in THIS env
    - test_real_graph_delegation (agents_stack-gated): run_mesh routes through build_graph (4 nodes execute, role-distinct state populated) and returns OrchestrationResult; roster size logged == 4
  </behavior>
  <action>
    In orchestrator.py replace the _run_langgraph placeholder body (currently `return _run_stub(task)`)
    with: build the graph via graph.build_graph(), compile it WITHOUT a checkpointer (compile() with no
    checkpointer is valid; the checkpointer arrives in 02-02), invoke with the initial state
    {"prompt": task.prompt}, and map the terminal state into OrchestrationResult(summary=...,
    proposed_writes=state.get("proposed_writes", []), evidence=[]). Leave trace_id unset (Phase 3).
    Preserve the langgraph_available() branch in run_mesh so the stub path remains the no-stack fallback.
    Trigger the roster startup-size log once on the real path. Do NOT add resume_mesh here (that is 02-02).
    Create tests/test_orchestration_graph.py with: test_stub_fallback (always-on) asserting run_mesh
    returns an OrchestrationResult and that a mutating prompt produces proposed_writes WITHOUT the agents
    stack; and test_real_graph_delegation marked to use the conftest `agents_stack` fixture (skips cleanly
    when stack absent) asserting the 4 nodes ran (role-distinct state) and roster_size()==4. Use the
    `repo` fixture from conftest where a TaskRecord is needed.
  </action>
  <verify>
    <automated>python -m pytest -q tests/test_orchestration_graph.py::test_stub_fallback -x</automated>
    <automated>python -m pytest -q tests/test_orchestration_graph.py -x</automated>
    <automated>python -m pytest -q tests/ -x</automated>
    <automated>grep -c "build_graph" src/agent_mesh/worker/orchestrator.py</automated>
  </verify>
  <acceptance_criteria>
    - tests/test_orchestration_graph.py::test_stub_fallback exits 0 in THIS env (no agents stack) and asserts an OrchestrationResult with proposed_writes for a mutating prompt
    - the agents-gated test SKIPS cleanly (not fails) when the stack is absent
    - orchestrator.py _run_langgraph calls graph.build_graph() and maps the terminal state to OrchestrationResult (no longer `return _run_stub(task)`)
    - orchestrator.py contains NO `resume_mesh`, NO `interrupt(`, NO `checkpointer` (all 02-02)
    - `python -m pytest -q tests/` exits 0
  </acceptance_criteria>
  <done>The real graph drives run_mesh on the stack path, the stub remains the no-stack fallback, OrchestrationResult is preserved, and ORCH-01 is covered by an always-on stub test plus an agents-gated delegation test.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| package index → build | `pyproject.toml` pin bump pulls the agents stack from PyPI |
| graph node → roster harness | declared subagents only; no self-spawning |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-02-01-SC | Tampering | pip install of langgraph / checkpoint x2 / deepagents | mitigate | RESEARCH Package Legitimacy Audit already completed: all 4 are first-party langchain-ai packages (multi-year release history, public repos, deepagents has no postinstall) — Approved. They are the project's own REQUIRED stack (CLAUDE.md §1). No human-verify gate required. |
| T-02-01-E | Elevation | roster grows beyond declared 4 (auto general-purpose subagent) | mitigate | Disable the auto general-purpose subagent; assert effective roster size == 4 at build; log it (ORCH-01). Bounded, declared, no self-spawning (CLAUDE.md guardrail). |
| T-02-01-I | Info disclosure | LangSmith auto-tracing leaks prompts | mitigate | Do not import/enable LangSmith; do not set LANGCHAIN_TRACING_V2 / LANGSMITH_API_KEY (CLAUDE.md: never a dependency). |
</threat_model>

<verification>
- `python -m pytest -q tests/` exits 0 in this env (no agents stack, no Docker) — agents-gated tests skip cleanly.
- `make smoke` stays green (stub path untouched).
- Roster size 4 logged at startup on the real-graph path; effective roster == 4 (general-purpose disabled).
- No `interrupt(`, no `checkpointer`, no `resume_mesh` introduced in this plan (those are 02-02).
</verification>

<success_criteria>
ORCH-01 satisfied: a real LangGraph StateGraph delegates planner -> researcher/tool-router -> code-writer -> reviewer; the declared roster is bounded at exactly 4 and its size is logged at startup; the stub-fallback path keeps `make test`/`make smoke` green with no cloud deps.
</success_criteria>

<output>
Create `.planning/phases/02-real-orchestration-engine/02-01-SUMMARY.md` when done.
</output>
