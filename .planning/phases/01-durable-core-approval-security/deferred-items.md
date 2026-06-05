# Deferred / Out-of-Scope Items — Phase 01

Discovered during execution, NOT caused by the current plan's changes. Logged per
the executor scope-boundary rule (do not fix issues unrelated to the task).

## 01-02 (Pub/Sub dispatch, DUR-03)

- **`tests/test_importability.py::test_module_imports[agent_mesh.api.app]` fails in this
  worktree's minimal environment** because `fastapi` is not installed
  (`importlib.util.find_spec('fastapi') is None`). `src/agent_mesh/api/app.py` imports
  `fastapi` at module top level, so the importability matrix (which asserts the package
  imports under minimal deps) fails for that one module. This is pre-existing, unrelated
  to the Pub/Sub dispatch work, and reproduces independently of the 01-02 changes
  (the 01-02 test file and helper import cleanly with the suite green when this single
  pre-existing failure is deselected: `59 passed, 1 skipped, 3 deselected`).
  Resolution belongs to the API/ingress plan or to the test environment setup
  (install the `api` extra), not to 01-02.
