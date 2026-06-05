---
phase: 02-real-orchestration-engine
reviewed: 2026-06-05T22:57:12Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - src/agent_mesh/worker/graph.py
  - src/agent_mesh/worker/roster.py
  - src/agent_mesh/worker/orchestrator.py
  - src/agent_mesh/worker/runner.py
  - src/agent_mesh/sandbox/executor.py
  - pyproject.toml
  - tests/conftest.py
  - tests/test_orchestration_graph.py
  - tests/test_checkpointer_resume.py
  - tests/test_interrupt_hitl.py
  - tests/test_sandbox.py
findings:
  critical: 1
  warning: 3
  info: 3
  total: 7
status: issues_found
resolved:
  - "CR-01 — fixed in d3febd9 (named container + docker rm -f on timeout; containment test added)"
  - "WR-01 — fixed in d3febd9 (max_cpu_seconds passed as --ulimit cpu)"
deferred:
  - "WR-02 — multi-write resume orphan; tracked in deferred-items.md (reachable in Phase 3)"
  - "WR-03 — substring write-trigger over-match + duplication; quality, tracked in deferred-items.md"
---

# Phase 02: Code Review Report

> **Resolution (post-review):** CR-01 (BLOCKER) and WR-01 (WARNING) fixed in
> commit `d3febd9` with a live Docker-gated containment test
> (`test_timeout_kills_container`). WR-02 and WR-03 deferred to `deferred-items.md`.
> The three INFO items are documented-safe / cosmetic.

**Reviewed:** 2026-06-05T22:57:12Z
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

Reviewed the Phase 02 orchestration engine: the real LangGraph `StateGraph`
topology (`graph.py`), the bounded Deep Agents roster (`roster.py`), the
orchestration adapter with the durable-checkpointer lifecycle (`orchestrator.py`),
the worker runner / approval gate (`runner.py`), and the hardened Docker sandbox
executor (`executor.py`), plus the four phase test modules and `pyproject.toml`.

**The three security invariants the phase brief flagged hold as written, and are
affirmed below — they are not the source of the findings:**

1. *Interrupt value is never trusted as approver identity.* `write_gate_node`
   (graph.py:164-167) records the resumed value under `decision` for observability
   only and never branches on it; `resume_mesh` (orchestrator.py:246) takes
   `(task, decision)` with no `approver_id` channel; `runner._resume_after_approval`
   (runner.py:117) passes a literal `True`. The approver is derived solely from
   `verify_approval_token` (approvals.py), which **fails closed** when no signing
   secret is configured.
2. *The write executes only under `is_approved()` re-hash.* The only Tool Gateway
   `.execute` call is `runner._execute`, reachable only inside the
   `approvals.is_approved(record, call.parameters)` branch (runner.py:127), which
   re-hashes the live payload against the approved hash — a post-approval payload
   mutation blocks the write (proven by `test_mutated_payload_blocks_write_through_resume`).
3. *The sandbox never falls back to an uncapped native subprocess.* `execute_code`
   raises `SandboxUnavailable` when `docker` is absent (executor.py:103-106); there
   is no native-subprocess path. `--memory-swap` is pinned equal to `--memory`
   (executor.py:69-70) so the cgroup cap is not a no-op.

Two previously-feared regressions were investigated and **do not apply**:
(a) a REJECTED approval re-running the whole mesh — `REJECTED` is in `TERMINAL_STATES`
(enums.py:38-39), so `runner.process`'s `is_terminal` guard (runner.py:46) returns
early; and (b) `interrupt()` crashing on the no-`DATABASE_URL` real-graph path — this
was empirically settled (see IN-01): LangGraph 1.2.4 *returns* `__interrupt__` without
a checkpointer rather than raising, so the path is safe.

The findings below center on sandbox **containment** (the headline BLOCKER: the
timeout does not actually stop the container), an unenforced CPU limit, a multi-write
approval lifecycle gap, and maintainability items.

## Critical Issues

### CR-01: Sandbox `timeout_s` kills the `docker` CLI, not the container — the timeout does not contain

**File:** `src/agent_mesh/sandbox/executor.py:112-127`
**Issue:** `execute_code` runs the container with
`subprocess.run(_docker_run_argv(...), timeout=limits.timeout_s)`. On timeout,
`subprocess.run` sends SIGKILL to the **`docker run` client process**. SIGKILL cannot
be trapped or forwarded, and the container itself is owned by the Docker daemon
(containerd), not the client — so killing the foreground `docker run` CLI does **not**
stop the container; it keeps running and consuming CPU. The `--rm` flag (executor.py:66)
is the daemon-side `AutoRemove`, which fires on container *exit* — a runaway snippet
that never exits is therefore never auto-removed, so a leaked, still-live container also
accumulates per timeout. For a prompt-to-code executor whose entire purpose is bounded,
isolated execution of model-generated code, the primary time-containment control does
not contain: the `timed_out=True` result is returned to the caller while the workload
is still executing on the host.
**Fix:** Give the container a stable handle and force-kill it on timeout instead of
relying on killing the client:
```python
import uuid
name = f"agent-mesh-sbx-{uuid.uuid4().hex}"
argv = _docker_run_argv(workdir, limits)  # insert ["--name", name] after "run"
try:
    proc = subprocess.run(argv, capture_output=True, text=True,
                          timeout=limits.timeout_s, check=False)
except subprocess.TimeoutExpired as exc:
    # Stop the daemon-owned container; the SIGKILLed client cannot.
    subprocess.run(["docker", "kill", name], capture_output=True, check=False)
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
    raw = exc.stdout or ""
    stdout = raw.decode() if isinstance(raw, bytes) else raw
    return CodeExecutionResult(exit_code=124, stdout=stdout,
                              stderr="timed out", timed_out=True)
```
Add a test that runs a `while True: pass` (or `time.sleep(600)`) snippet with a short
`timeout_s` and asserts no container with that name survives after the call returns.

## Warnings

### WR-01: `SandboxLimits.max_cpu_seconds` is declared but never enforced

**File:** `src/agent_mesh/sandbox/executor.py:39` (and `_docker_run_argv`, 56-89)
**Issue:** `max_cpu_seconds` (default 20) is part of the limits contract but is never
passed to `docker run` — `_docker_run_argv` consumes only `max_memory_mb`. There is
no `--cpus`, no `--cpu-quota`, and no CPU `ulimit`. A CPU-bound snippet that allocates
little memory (so the cgroup memory cap never fires) is therefore bounded only by the
wall-clock `timeout_s` — which, per CR-01, also fails to stop the container. The limit
reads as enforced (it sits in the same dataclass as the memory cap that *is* applied)
but silently does nothing, which is worse than its absence because callers will assume
CPU is capped. `max_output_bytes` *is* applied (stdout/stderr slicing, executor.py:135-136),
so this is specifically the CPU field that is dead.
**Fix:** Either enforce it (e.g. add `--cpus` for a fractional core cap and/or a
`--ulimit cpu=<n>` for CPU-seconds) in `_docker_run_argv`, or remove the field and
document CPU bounding as out of scope so the contract does not over-promise:
```python
# in _docker_run_argv, alongside the memory flags:
"--ulimit", f"cpu={limits.max_cpu_seconds}",   # hard CPU-seconds cap
"--cpus", "1.0",                                # cap to one core
```

### WR-02: Multi-write resume completes the task while leaving sibling writes still gated

**File:** `src/agent_mesh/worker/runner.py:65-104` and `:106-143`;
`src/agent_mesh/services/task_service.py:80-86`
**Issue:** `process()` opens one approval record **per** proposed write
(runner.py:67-90), but the task lifecycle is single-decision: `submit_approval_decision`
flips the whole **task** to `APPROVED` on the *first* record approved
(task_service.py:80-82) and re-dispatches. The worker then runs `_resume_after_approval`,
which loops the pending calls, executes only the calls whose record `is_approved()`,
and **unconditionally** transitions the task to `COMPLETED` afterward (runner.py:140-143).
A still-PENDING sibling record is neither APPROVED (so `is_approved()` is False — the
write correctly does not execute) nor REJECTED (so the reject branch at runner.py:133
does not fire) — it is silently abandoned when the task completes. This is **fail-safe**
(the unapproved write does NOT execute, so it is a WARNING not a BLOCKER), but the
lifecycle is wrong: a write the requester never decided on is dropped without a trace.
It is masked today only because every current producer emits exactly one write
(graph.reviewer_node appends a single proposal); it becomes reachable the moment Phase 3
emits more than one write per task.
**Fix:** Do not complete the task while any of its approval records are still PENDING.
Gate the `COMPLETED` transition on "all records for this task are decided" and otherwise
keep the task in `AWAITING_APPROVAL`; or model one approval record per task with a
multi-write payload so a single decision covers the batch. Add a two-write test that
approves only the first and asserts the task stays awaiting (not completed).

### WR-03: Write-trigger substring matching over-matches and is duplicated across two modules

**File:** `src/agent_mesh/worker/graph.py:35-43` and `:118-120`; duplicated in
`src/agent_mesh/worker/orchestrator.py:172-174`
**Issue:** Two correctness-adjacent problems in one heuristic. (1) `WRITE_TRIGGERS`
membership is tested with `trigger in lowered` (substring), so non-mutating prompts
containing a trigger as a substring are mis-classified as write-class — e.g.
"increase the budget" matches `create`, "recommit to the plan" matches `commit`,
"updateable fields summary" matches `update`. The failure direction is fail-safe here
(an extra approval gate, not a skipped one), so it is a WARNING not a BLOCKER — but it
generates spurious approval prompts and erodes the trust the gate depends on. (2)
The identical trigger tuple and matching logic are maintained in three places
(graph.py module constant, graph.py reviewer node, orchestrator `_run_stub`); the
docstrings assert they are "kept identical" by hand, which is exactly the drift risk a
shared definition removes. If they diverge, the real-graph and stub paths gate
different prompts, breaking the "exercised identically on both paths" guarantee the
tests rely on.
**Fix:** Match on word boundaries (tokenize the lowered prompt and test set
membership, or use `re.search(r"\b(create|update|...)\b", lowered)`), and hoist the
single canonical `WRITE_TRIGGERS` and a `proposes_write(prompt)` helper into one module
that both `graph.reviewer_node` and `orchestrator._run_stub` import.

## Info

### IN-01: No-checkpointer real-graph interrupt path is safe (verified) but undocumented and untested in CI

**File:** `src/agent_mesh/worker/orchestrator.py:227-235`, `:284-290`
**Issue:** `run_mesh` branches to the real graph on `langgraph_available()` alone, so a
default `.[agents]` install with no `DATABASE_URL` (the common dev config) runs the real
graph and reaches `write_gate_node`'s `interrupt()` with a `None` checkpointer
(`_select_checkpointer` returns `None`, orchestrator.py:95-99). I confirmed empirically
against LangGraph 1.2.4 that `interrupt()` **without** a checkpointer *returns*
`__interrupt__` rather than raising, so this path is safe and `_run_langgraph`'s
`if "__interrupt__" in final_state` handling (orchestrator.py:232) is correct;
`resume_mesh` separately guards `checkpointer is None` and returns a terminal no-op
(orchestrator.py:284-290), which is coherent. The residual concern is only that this
exact behaviour is asserted **only** by the agents-gated `test_real_graph_delegation`,
which skips in CI (the `.[agents]` stack is not installed in the default env), so a
future LangGraph upgrade that changes the interrupt-without-checkpointer contract would
not be caught.
**Fix:** No code change required. Pin the LangGraph minor in `pyproject.toml` to a range
validated against this behaviour, and add a one-line note to `_select_checkpointer`'s
docstring recording that the real path tolerates a `None` checkpointer because
`interrupt()` returns `__interrupt__` (validated, LangGraph 1.2.x).

### IN-02: `langgraph-checkpoint-*` pins (`~=3.1`) diverge from the installed 4.1.1

**File:** `pyproject.toml:37-38`
**Issue:** The `agents` extra pins `langgraph-checkpoint-postgres~=3.1` and
`langgraph-checkpoint-sqlite~=3.1`, but project memory (observation 5828, 2026-06-06)
records the actually-installed checkpoint package as 4.1.1. `~=3.1` resolves to
`>=3.1,<4`, so a clean install from this manifest cannot produce 4.1.1 — the lockfile
and the manifest disagree. Since the checkpointer API surface (`PostgresSaver.setup()`,
`SqliteSaver`, `Command(resume=...)`) is load-bearing for ORCH-02/ORCH-03, a 3.x↔4.x
gap can change behaviour between dev and a fresh deploy.
**Fix:** Reconcile the pin with the validated runtime — bump to the `~=4.1` line the
tests were actually exercised against (or pin the exact validated version) so a clean
`pip install .[agents]` reproduces the tested stack.

### IN-03: `roster_size()` startup log fires from two places with different messages

**File:** `src/agent_mesh/worker/roster.py:151` and `src/agent_mesh/worker/orchestrator.py:223`
**Issue:** ORCH-01's "log roster size at startup" is emitted both by `build_roster`
("roster size %d: %s") and by `_run_langgraph` ("roster size %d at startup"). On the
real path both can fire for a single run with different wording, which makes the
startup log ambiguous for operators grepping for the bound and double-counts in any
log-based assertion.
**Fix:** Emit the size from one place (prefer `build_roster`, the authoritative bound
check) and have `_run_langgraph` rely on it, or unify the message string.

---

_Reviewed: 2026-06-05T22:57:12Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
