# Deferred Items — Phase 01

Out-of-scope discoveries logged during execution. NOT fixed by the owning plan.

## 01-01

- **Pre-existing env gap: `fastapi` not installed in this worktree's interpreters.**
  `tests/test_importability.py::test_module_imports[agent_mesh.api.app]` fails with
  `ModuleNotFoundError: No module named 'fastapi'`. `fastapi` is a base dependency in
  `pyproject.toml` but was never `pip install`-ed in this environment (no venv; no
  interpreter on PATH has it). The failure is independent of 01-01 (app.py and the
  importability test were not modified). Resolution: run `make install` (or
  `pip install -e .`) before `make test`. The full suite passes 60/60 once this single
  env-gated test is deselected.

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
  (install the `api` extra), not to 01-02. Same root cause as the 01-01 note above.
