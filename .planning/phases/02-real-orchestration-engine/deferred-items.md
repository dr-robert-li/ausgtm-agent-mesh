# Deferred Items — Phase 02 Real Orchestration Engine

Out-of-scope discoveries logged during plan execution (not fixed — outside the
current task's change scope).

## From 02-03 (hardened-sandbox)

- **`fastapi` not installed in this worktree env** — 6 failures in
  `tests/test_approval_security.py` and 1 in
  `tests/test_importability.py::test_module_imports[agent_mesh.api.app]` fail with
  `ModuleNotFoundError: No module named 'fastapi'`. These belong to the API/approval
  surface (plans 02-01/02-02), not the sandbox. The sandbox path imports cleanly and
  `tests/test_sandbox.py` is fully green. Not caused by 02-03 changes.
- **`make smoke` uses `python` but env only has `python3`** — `make smoke` fails with
  `/bin/sh: python: command not found`. `make smoke` does NOT touch the sandbox path;
  running it directly as `PYTHONPATH=src python3 -m tests.smoke` reports `SMOKE OK`.
  This is an environment/Makefile alias mismatch, not a 02-03 regression.

## From 02 code review (02-REVIEW.md)

- **CR-01 (BLOCKER) — RESOLVED** in `d3febd9`. Sandbox wall-clock timeout SIGKILLed
  only the `docker run` client; the daemon-owned container kept running and `--rm`
  never reaped it. Fixed with a pinned `--name` + `docker rm -f` on `TimeoutExpired`;
  added Docker-gated `test_timeout_kills_container` asserting the container is gone.
- **WR-01 (WARNING) — RESOLVED** in `d3febd9`. `max_cpu_seconds` was declared but never
  passed to Docker; now enforced as a hard `--ulimit cpu=<seconds>` (RLIMIT_CPU).
- **WR-02 (WARNING) — DEFERRED.** Multi-write resume completes the task while sibling
  approval records are still PENDING (fail-safe: the unapproved write does not execute,
  but the undecided write is silently dropped). Only reachable once Phase 3 emits >1
  write per task. Fix when the orchestrator gains real multi-write fan-out.
- **WR-03 (WARNING) — DEFERRED (quality).** Substring write-trigger matching over-matches
  (e.g. "increase" → `create`) and the trigger heuristic is hand-duplicated across
  graph.py / orchestrator.py / `_run_stub`. Consolidate into one word-boundary matcher.
- **IN-02 (INFO) — NOT A BUG (verified).** No pin drift. The pinned BACKENDS
  `langgraph-checkpoint-sqlite~=3.1` / `-postgres~=3.1` match the installed 3.1.0. The
  4.1.1 is the core `langgraph-checkpoint` meta-package, which pyproject does not pin —
  it is transitive under `langgraph>=1.0,<2` (1.2.4). Reproducible as-is.
