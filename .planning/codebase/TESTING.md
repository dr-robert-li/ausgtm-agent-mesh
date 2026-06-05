# Testing Patterns

**Analysis Date:** 2026-06-05

## Test Framework

**Runner:**
- Pytest 8.0+
- Config: `src/agent_mesh/` configured as pythonpath for absolute imports
- pytest config in `pyproject.toml`:
  ```
  [tool.pytest.ini_options]
  pythonpath = ["src"]
  testpaths = ["tests"]
  ```

**Assertion Library:**
- Plain Python `assert` statements (no specialized assertion library)
- `pytest.raises(ExceptionType)` for exception testing

**Run Commands:**
```bash
make test                # Run full test suite
make lint                # Run ruff lint checks (not tests)
make fmt                 # Auto-format and fix lint issues
make smoke               # Run standalone e2e smoke test (no pytest, no DB, no network)
```

## Test File Organization

**Location:**
- Tests are co-located in a top-level `tests/` directory (separate from `src/`)
- Not placed alongside source code

**Naming:**
- Test modules: `test_*.py` (pytest discovery convention)
- Standalone smoke test: `tests/smoke.py` (run via `make smoke`, not pytest)

**Structure:**
```
tests/
├── __init__.py
├── conftest.py           # pytest fixtures (shared across all tests)
├── smoke.py              # Standalone end-to-end smoke check (no DB/network)
├── test_contracts.py     # Contract models, JSON schema, state machine
├── test_approval_gating.py  # Approval workflow + write-action gating
├── test_importability.py # Package import matrix under minimal deps
├── test_self_improvement.py  # Self-improvement proposal lifecycle
├── test_slack_verify.py  # Slack signature verification
└── test_stack_and_toolpacks.py  # Architecture validation + manifest checks
```

## Fixtures & Dependency Injection

**Shared Fixtures:**
- `conftest.py` defines a single reusable fixture: `repo` (InMemoryRepository)
- Example from `tests/conftest.py`:
  ```python
  @pytest.fixture
  def repo() -> InMemoryRepository:
      """Fresh in-memory repository per test (avoids the process-wide singleton)."""
      return InMemoryRepository()
  ```

**Factory Helpers:**
- Test-local helper functions to construct needed objects (not separate fixture libraries)
- Example from `tests/test_approval_gating.py`:
  ```python
  def _service_and_worker(repo):
      dispatcher = InProcessDispatcher()
      svc = TaskService(repo=repo, dispatcher=dispatcher)
      worker = Worker(repo=repo)
      return svc, worker
  ```
- Example from `tests/test_self_improvement.py`:
  ```python
  def _task(repo) -> TaskRecord:
      task = TaskRecord(
          tenant_id="t",
          client_slug="c",
          entrypoint=Entrypoint.API,
          requester={"requester_id": "u1", "entrypoint": "api"},
          session_id="s1",
          prompt="summarize the kickoff notes",
      )
      return repo.create_task(task)
  ```

## Test Structure

**Suite Organization:**
- Flat test functions per module (no test classes)
- Function name pattern: `test_<describes_what_is_being_tested>`
- Example from `tests/test_contracts.py`:
  ```python
  def test_all_contract_models_emit_json_schema():
      for name, model in CONTRACT_MODELS.items():
          schema = model.model_json_schema()
          assert schema["type"] == "object", name
          assert "properties" in schema, name

  def test_task_request_round_trips():
      req = TaskRequest.model_validate({
          "tenant_id": "t",
          "client_slug": "c",
          ...
      })
      assert req.entrypoint == "api"
  ```

**Assertion Pattern:**
- Plain `assert` statements; `pytest.raises()` for exceptions
- Example from `tests/test_contracts.py`:
  ```python
  def test_illegal_transition_rejected():
      assert not can_transition(TaskState.COMPLETED, TaskState.RUNNING)
      with pytest.raises(IllegalTransition):
          assert_transition(TaskState.COMPLETED, TaskState.RUNNING)
  ```

## Testing Strategy: Fakes, Not Mocks

**Core Convention:**
- **Do NOT mock or patch** — instead, inject real in-memory implementations
- The codebase uses Protocol-based dependency injection: every testable module accepts its dependencies as constructor args
- Tests provide lightweight in-memory implementations (fakes) for repositories, dispatchers, and gateways

**What to Inject (Fakes):**
- `InMemoryRepository` — from `src/agent_mesh/services/repository.py`, thread-safe dict-backed store for tasks, approvals, proposals, etc.
- `InProcessDispatcher` — from `src/agent_mesh/services/dispatch.py`, in-process task dispatch (no Pub/Sub)
- Real service classes (`TaskService`, `Worker`) with injected fakes

**Example from `tests/test_approval_gating.py`:**
```python
def test_write_task_pauses_then_completes_after_approval(repo):
    svc, worker = _service_and_worker(repo)  # _service_and_worker injects fakes
    req = request_from_slack(
        tenant_id="t", client_slug="c", slack_user_id="U1", slack_channel_id="C1",
        text="create a hubspot deal",
    )
    task = svc.create_task(req)
    state = worker.process(task.task_id)
    assert state == "awaiting_approval"

    # Find the opened approval and approve it (direct repo access, no mocking)
    (approval_id,) = list(repo._approvals.keys())
    svc.submit_approval_decision(approval_id, ApprovalDecision.APPROVED, "slack:U1", "slack")
    assert repo.get_task(task.task_id).state == "approved"

    final = worker.process(task.task_id)
    assert final == "completed"
```

**No mocking framework used** — no `unittest.mock`, `monkeypatch`, or `MagicMock`

## Test Types & Coverage

**Unit Tests:**
- Contract validation (JSON schema round-trips, enum serialization)
- State machine transitions (legal vs. illegal, terminal states)
- Approval payload hashing (payload mutation detection)
- Self-improvement proposal lifecycle (draft → evaluation → approval → promotion)
- Located in `tests/test_*.py`

**Integration Tests:**
- Slice across layers: ingress → task service → dispatch → worker → approval gating
- No database or external network; all state in-memory
- Examples: `test_write_task_pauses_then_completes_after_approval`, `test_read_task_completes_without_approval` in `tests/test_approval_gating.py`

**End-to-End Smoke Test:**
- Standalone script `tests/smoke.py` (not pytest; run via `make smoke`)
- Exercises full flow: schema export → task creation → write gating → approval → completion, for both write and read tasks
- No database, network, or model credentials required
- Self-contained; can be run locally without any external setup
- Output: "SMOKE OK" on success
- Example invocation:
  ```bash
  make smoke
  # Output: [schemas] exported 14 contract schemas
  #         [write] Slack task paused for approval, approved, completed
  #         [read] MCP task completed without approval
  #         SMOKE OK
  ```

**Import Matrix Test:**
- `tests/test_importability.py` validates that every module in the codebase is importable in a minimal environment (no optional heavy deps)
- Parametrized over all modules: `@pytest.mark.parametrize("module", MODULES)`
- Ensures optional deps (LangChain, LangGraph, Langfuse, LiteLLM, Slack, MCP) are lazy-imported or feature-gated
- Example:
  ```python
  @pytest.mark.parametrize("module", MODULES)
  def test_module_imports(module):
      """Whole package must import without optional heavy deps."""
      importlib.import_module(module)
  ```

**Architecture Validation Tests:**
- `tests/test_stack_and_toolpacks.py` validates design contracts, not live behavior
- Checks: required toolpack providers present, write-class tools approval-gated, deployment manifest declares required stack, model gateway supports Anthropic and Vertex
- Loads and parses YAML manifests and validates Python code invariants
- Example:
  ```python
  def test_required_toolpack_providers_present():
      providers = {t["provider"] for t in _manifest()["tools"]}
      missing = REQUIRED_PROVIDERS - providers
      assert not missing, f"missing required toolpack providers: {sorted(missing)}"
  ```

## Mocking & Stubbing

**Mocking Framework:**
- Not used. No `unittest.mock`, `monkeypatch`, or `pytest-mock` in the dependency tree

**Stubbing Pattern:**
- The orchestrator layer (`src/agent_mesh/worker/orchestrator.py`) includes a deterministic stub for `run_mesh(task)` when LangChain/LangGraph are not installed
- This allows the entire architecture to be tested without the agent framework installed (minimal environment)

## Async Testing

**Async Endpoints:**
- The API layer includes async endpoints (e.g., `async def slack_events(request: Request)` in `src/agent_mesh/api/app.py`)
- Tests are **not async** — no `pytest-asyncio`
- To test async endpoints, tests invoke service layer methods directly (sync wrappers), bypassing the async HTTP transport
- Example: tests call `request_from_slack(...)` and `_service.create_task(req)` directly, not HTTP POST to `/slack/events`

## Coverage

**Coverage Requirements:**
- No minimum threshold enforced
- No coverage reporting configured in `pyproject.toml`

**Coverage Excludes:**
- Lines marked with `# pragma: no cover` are excluded (used in `src/agent_mesh/observability.py` for optional-dependency branches that require external credentials)
- Example:
  ```python
  try:  # pragma: no cover - needs langfuse + keys
      # Langfuse initialization
  except Exception:  # pragma: no cover
      pass
  ```

## Test Patterns

**Happy Path Pattern:**
```python
def test_something_works(repo):
    # Arrange: set up fixtures, create objects
    task = repo.create_task(task_record)
    
    # Act: invoke the code under test
    result = worker.process(task.task_id)
    
    # Assert: verify the outcome
    assert result == expected_state
```

**Error Path Pattern:**
```python
def test_something_raises():
    with pytest.raises(IllegalTransition):
        assert_transition(TaskState.COMPLETED, TaskState.RUNNING)
```

**Stateful Workflow Pattern (Approval Flow):**
```python
def test_write_task_pauses_then_completes_after_approval(repo):
    # Step 1: create and process a write task
    task = svc.create_task(req)
    state = worker.process(task.task_id)
    assert state == "awaiting_approval"
    
    # Step 2: inspect state (no mocking; direct repo access)
    (approval_id,) = list(repo._approvals.keys())
    
    # Step 3: submit approval decision
    svc.submit_approval_decision(approval_id, ApprovalDecision.APPROVED, ...)
    
    # Step 4: resume and verify completion
    final = worker.process(task.task_id)
    assert final == "completed"
```

## Fixture Isolation

**Per-Test Isolation:**
- Each test gets a fresh `InMemoryRepository` instance via the `repo` fixture
- No shared state between tests
- Ensures tests are independent and repeatable

**Example:**
```python
def test_a(repo):
    repo.create_task(...)  # repo is fresh per test
    ...

def test_b(repo):
    # This repo is a DIFFERENT instance from test_a's repo
    ...
```

## YAML Manifest Testing

**Load & Validate Pattern:**
- Load YAML manifests into dicts and iterate over structures
- Example from `tests/test_stack_and_toolpacks.py`:
  ```python
  def _manifest() -> dict:
      path = REPO_ROOT / "manifests" / "tool_pack_manifest.yaml"
      return yaml.safe_load(path.read_text())

  def test_every_tool_declares_an_integration_style():
      allowed = {"direct_api", "mcp_server", "aggregate_mcp", "nango_aggregator"}
      for tool in _manifest()["tools"]:
          assert tool.get("integration_style") in allowed
  ```

## Parameterized Tests

**Usage:**
- `@pytest.mark.parametrize("variable", [values])` for matrix/cartesian testing
- Example from `tests/test_importability.py`:
  ```python
  MODULES = [
      "agent_mesh",
      "agent_mesh.contracts",
      ...
  ]

  @pytest.mark.parametrize("module", MODULES)
  def test_module_imports(module):
      importlib.import_module(module)
  ```

## Test-Only Utilities

**Request Builders (Test Helpers):**
- `request_from_slack(tenant_id, client_slug, slack_user_id, ...)` — creates a TaskRequest from Slack event
- `request_from_mcp(tenant_id, client_slug, mcp_subject, ...)` — creates a TaskRequest from MCP
- Located in `src/agent_mesh/services/task_service.py` (not test-specific; also used by API layer)

**Service Constructors (Test Factories):**
- `_service_and_worker(repo)` — returns both TaskService and Worker with injected in-memory deps
- Inline in test files; not centralized (reused across test modules)

## No External Dependencies for Tests

**Test isolation:**
- No testcontainers (Docker containers for databases, services)
- No external network calls
- No model credentials or API keys required
- All state is in-memory via `InMemoryRepository` and `InProcessDispatcher`
- Tests are fast and can run offline

**Production Postgres Implementation (Not Tested Here):**
- A Postgres-backed repository implementation exists at runtime (specs in migrations/)
- Tests do not exercise it — they use the in-memory fake
- The contract (Protocol) ensures both implementations are compatible

---

*Testing analysis: 2026-06-05*
