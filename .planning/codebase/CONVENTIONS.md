# Coding Conventions

**Analysis Date:** 2026-06-05

## Naming Patterns

**Files:**
- Module files: lowercase with underscores (`approvals.py`, `task_service.py`, `admin_console.py`)
- Package directories: lowercase with underscores (`agent_mesh`, `contracts`, `services`)

**Functions:**
- Public functions: `snake_case` (e.g., `requires_approval`, `can_transition`, `build_approval_request`)
- Private functions: leading underscore + `snake_case` (e.g., `_coerce`, `_utcnow`, `_new_id`, `_base`)

**Variables:**
- Local variables: `snake_case`
- Private module variables: leading underscore (e.g., `_ALLOWED`, `_settings`, `_service`)
- Constants: `UPPER_CASE` (e.g., `TERMINAL_STATES`, `WRITE_CATEGORIES`, `REQUIRED_PROVIDERS`)

**Types & Classes:**
- Classes: `PascalCase` (e.g., `TaskRecord`, `TaskRequest`, `RequesterIdentity`, `Worker`, `Repository`)
- Enum classes: `PascalCase` (e.g., `TaskState`, `ToolCategory`, `ApprovalDecision`)
- Protocol classes: `PascalCase` (e.g., `Repository` protocol at `src/agent_mesh/services/repository.py`)

## Code Style

**Formatting:**
- Tool: Ruff (explicit config via `pyproject.toml`)
- Line length: 100 characters
- Command: `make fmt` runs `ruff check --fix` followed by `ruff format`

**Linting:**
- Tool: Ruff
- Selected rules: `E` (errors), `F` (Pyflakes), `I` (isort imports), `UP` (pyupgrade), `B` (flake8-bugbear)
- Ignored rules:
  - `B008` — FastAPI `Depends()` in function defaults is idiomatic and intentional
  - `UP042` — `str + Enum` concatenation is intentional for clean JSON/value serialization under Pydantic
- Command: `make lint` runs `ruff check src tests`

**Python Version:**
- Minimum: Python 3.11+
- Modern union syntax required: `X | None` instead of `Optional[X]`
- `from __future__ import annotations` at the top of every module for forward-reference annotation compatibility

## Import Organization

**Order:**
1. Standard library (`datetime`, `typing`, `json`, `hashlib`)
2. Third-party imports (`pydantic`, `fastapi`, `uvicorn`, `httpx`)
3. Local agent_mesh imports (`from agent_mesh.contracts import ...`)

**Pattern:**
- Absolute imports only (no relative imports)
- Full module path using `agent_mesh` prefix (e.g., `from agent_mesh.contracts.models import TaskRecord`)
- Enforced by Ruff `I` rule (isort)

**Pythonpath:**
- Configured via `pyproject.toml`: `pythonpath = ["src"]`
- All imports reference `agent_mesh.*` as the top-level package

**No path aliases** — all paths are absolute from the `agent_mesh` root.

## Type Hints

**Coverage:**
- Every function signature is fully type-hinted: parameters, return types, and generics
- Union syntax: `X | None` (PEP 604), not `Optional[X]`
- Examples from `src/agent_mesh/contracts/lifecycle.py`:
  ```python
  def can_transition(current: TaskState | str, target: TaskState | str) -> bool:
  def assert_transition(current: TaskState | str, target: TaskState | str) -> None:
  ```

**Pydantic Models:**
- All contract models inherit from a shared `_Base` class at `src/agent_mesh/contracts/models.py`
- `_Base` uses `ConfigDict(use_enum_values=True, extra="forbid")`:
  - Enums are serialized to string values in JSON (intentional under Pydantic v2)
  - Extra fields are forbidden to catch schema drift
- Example: `RequesterIdentity`, `TaskRequest`, `TaskRecord` all extend `_Base`

## Error Handling

**Custom Exceptions:**
- Subclass appropriate builtin bases: `class IllegalTransition(ValueError)` in `src/agent_mesh/contracts/lifecycle.py`
- Raised with clear context messages: `raise IllegalTransition(f"Illegal task transition: {current.value} -> {target.value}")`

**Error Recovery Patterns:**
- `KeyError` for unknown record lookups (e.g., `repo.get_approval(...)` returning `None` → caller raises `KeyError`)
- API layer maps exceptions to HTTP status codes via FastAPI's `HTTPException` (e.g., `status_code=404` for not found, `status_code=400` for bad request)
- Chain exceptions with `raise ... from exc` for context preservation
- Example from `src/agent_mesh/api/app.py`:
  ```python
  except KeyError as exc:
      raise HTTPException(status_code=400, detail=f"missing field: {exc}") from exc
  ```

**Optional-Dependency Graceful Degradation:**
- Broad `try/except Exception` only used for optional heavy dependencies (Langfuse, LangChain, model gateway)
- Example in `src/agent_mesh/observability.py`: langfuse client initialization fails silently if credentials are absent
- Core architecture (contracts, repository, lifecycle) remains importable without optional deps

## Docstrings & Comments

**Module Docstrings:**
- Every module has a module-level docstring (triple-quoted block at the very top)
- Explains module purpose, design notes, and key contracts
- Example from `src/agent_mesh/contracts/models.py`:
  ```python
  """Pydantic v2 contract models for the agent mesh.

  Design notes:
  - Every record carries ``tenant_id`` / ``client_slug`` ...
  - Correlation IDs (``task_id``, ``session_id``, ...) are threaded ...
  """
  ```

**Function Docstrings:**
- Public functions have one-line docstrings describing behavior
- Format: plain text or RST double-backtick markup for code references (``` ``task_id`` ```)
- Example from `src/agent_mesh/contracts/lifecycle.py`:
  ```python
  def can_transition(current: TaskState | str, target: TaskState | str) -> bool:
      """Return True if ``current -> target`` is a legal lifecycle transition."""
  ```

**Private Helpers:**
- Leading-underscore functions (e.g., `_coerce`, `_utcnow`, `_new_id`) typically omit docstrings — type hints + names are sufficient

**Inline Comments:**
- Used sparingly; prefer self-documenting code and docstrings
- When used, explain the *why* not the *what*

**Design Decision Documentation:**
- Module-level docstrings capture architectural decisions, state machines, patterns, and contract notes
- Example from `src/agent_mesh/contracts/lifecycle.py`:
  ```python
  """Task lifecycle state machine.

  Centralizes legal transitions so ingress, the task service, and the worker all
  agree on what a valid transition is. Kept Temporal-ready: the transition table
  maps directly onto durable-workflow signals if Temporal is introduced later.
  """
  ```

## State Management & Immutability

**Pattern:**
- Pydantic models are treated as immutable via `model_copy(update={...})`
- Never mutate model fields directly
- Example from `src/agent_mesh/services/repository.py`:
  ```python
  updated = task.model_copy(
      update={
          "state": target.value,
          "updated_at": datetime.now(UTC),
      }
  )
  ```

**Enum Serialization:**
- Enums are stored and serialized as string values (e.g., `TaskState.RUNNING` → `"running"`)
- Model coercion function `_coerce()` handles both types: `TaskState | str` → `TaskState`

## Factory Functions & Builders

**Pattern:**
- Standalone functions return new model instances (e.g., `build_approval_request(...)`)
- Default factories via Pydantic `Field(default_factory=...)` for IDs, timestamps, collections
- Example from `src/agent_mesh/contracts/models.py`:
  ```python
  task_id: str = Field(default_factory=_new_id)
  created_at: datetime = Field(default_factory=_utcnow)
  metadata: dict[str, Any] = Field(default_factory=dict)
  ```

## Module Structure

**Layering:**
1. **Contracts layer** (`src/agent_mesh/contracts/`): enums, lifecycle state machine, Pydantic models, JSON schema export
2. **Services layer** (`src/agent_mesh/services/`): repository protocol, approval gating, task service, dispatch, self-improvement
3. **API ingress** (`src/agent_mesh/api/`): FastAPI app, Slack signature verification, MCP server
4. **Worker layer** (`src/agent_mesh/worker/`): orchestrator runner, model gateway, budget tracking
5. **Tool gateway** (`src/agent_mesh/tools/`): tool registry, approval/category validation, tool pack loader
6. **Observability** (`src/agent_mesh/observability.py`): Langfuse integration, trace callbacks
7. **GUI** (`src/agent_mesh/gui/`): Streamlit admin console
8. **Sandbox** (`src/agent_mesh/sandbox/`): isolated code execution

**Barrel Files (`__init__.py`):**
- Package `__init__.py` re-exports key contracts and enums for convenience
- Example: `src/agent_mesh/contracts/__init__.py` exports `TaskState`, `Entrypoint`, `TaskRequest`, etc.
- Avoids deep import chains in client code

## Dependency Injection

**Pattern:**
- Services accept their dependencies as constructor parameters (`__init__`)
- Example from `src/agent_mesh/worker/runner.py`:
  ```python
  class Worker:
      def __init__(
          self,
          repo: Repository | None = None,
          tool_gateway: ToolGateway | None = None,
      ) -> None:
          self._repo = repo or get_repository()
  ```

**Lazy Defaults:**
- Functions can accept `None` and lazily initialize via singleton getter (e.g., `get_repository()`, `get_settings()`)
- Facilitates testing (inject real fakes) and production (use singletons)

## Timestamp & Identity Handling

**UTC Timestamps:**
- Always use `datetime.now(UTC)` for timezone-aware timestamps
- Import: `from datetime import UTC, datetime`
- Example from `src/agent_mesh/contracts/models.py`:
  ```python
  def _utcnow() -> datetime:
      return datetime.now(UTC)
  ```

**ID Generation:**
- Use `uuid4().hex` for stable string IDs
- Example: `task_id: str = Field(default_factory=_new_id)` where `_new_id() -> str: return uuid4().hex`

---

*Convention analysis: 2026-06-05*
