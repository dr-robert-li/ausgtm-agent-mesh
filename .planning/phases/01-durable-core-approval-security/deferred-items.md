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
