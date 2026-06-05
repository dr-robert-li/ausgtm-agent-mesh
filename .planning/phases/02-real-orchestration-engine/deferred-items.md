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
