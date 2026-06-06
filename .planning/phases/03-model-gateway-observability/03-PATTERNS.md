# Phase 3: Model Gateway & Observability - Pattern Map

**Mapped:** 2026-06-06
**Files analyzed:** 11 (9 modify, 0 new src, 2 config-modify; CF worker referenced-only)
**Analogs found:** 9 / 11 with in-repo analogs; 2 config files self-analog

> **Phase shape (from RESEARCH).** This phase **extends existing seams**; it adds **zero new
> src modules** and **no new migration** (`budget_ledger` + `gateway_events` already exist in
> `migrations/0001_init.sql` lines 201-229 with matching `BudgetEvent`/`GatewayEvent` models in
> `contracts/models.py` lines 219-250). The real work is: repository methods, an in-process
> Router loader + binding subclass, a langfuse v2→v4 + OTel migration, and durable-ledger budget
> persistence. New code lands **inside existing files** + **new test modules** (see test map).

---

## File Classification

| File (modify unless noted) | Role | Data Flow | Closest Analog | Match Quality |
|----------------------------|------|-----------|----------------|---------------|
| `src/agent_mesh/services/repository.py` | model/persistence | CRUD + aggregate | `upsert_tool_call` / `list_tool_calls` (same file, 603-649) | exact (writes/lists); **no-analog** (the SUM aggregate) |
| `src/agent_mesh/worker/budget.py` | service | request-response → durable CRUD | self (`BudgetTracker` 22-46) — swap `_spent` dict for ledger reads | role-match (API kept, backing swapped) |
| `src/agent_mesh/worker/model_gateway.py` | service/provider | request-response (model call) | self (`get_chat_model`/`resolve_route` 48-88) | role-match (extend, add Router loader + subclass) |
| `src/agent_mesh/observability.py` | utility/provider | event-driven (span emission) | self `trace_metadata()` (38-62) for attrs; `get_langchain_callback` 65-84 is **migrate-this** (dead v2 import) | partial (attrs exact; callback dead) |
| `src/agent_mesh/worker/graph.py` | orchestration node | request-response (delegation behind gate) | self `_model_credentials_present` gate (66-81) + node bodies (84-135) | role-match |
| `src/agent_mesh/worker/orchestrator.py` | controller/adapter | request-response | self `_run_langgraph` (200-243) — set `trace_id` on result (124-129) | role-match (one-field extension) |
| `src/agent_mesh/services/approvals.py` | service | event-driven (emit span only) | self `record_decision`/`open_approval` (158-197) — wrap with read-only span | partial (span is additive telemetry) |
| `src/agent_mesh/settings.py` | config | request-response | self model/langfuse fields (42-75) | exact (mirror dataclass-field pattern) |
| `pyproject.toml` | config | n/a | self `runtime` extra (18-27) | exact |
| `config/model_gateway.config.yaml` | config | n/a | self (source of truth; loader reads it) | self-analog |
| `manifests/deployment.manifest.yaml` | config | n/a | self (existing `model_routes`/budget/langfuse keys) | self-analog |

**Referenced, NOT modified this phase** (D-06 / RESEARCH: CF worker deploy is Phase 5 / DEP-02):
`cloudflare/ai-gateway-wrapper/wrangler.toml` + `src/index.ts`. The planner asserts the
`api_base` seam structurally only; **do not implement / publish the worker**.

---

## Pattern Assignments

### `src/agent_mesh/services/repository.py` (model/persistence, CRUD + aggregate)

**Analog:** same file — `upsert_tool_call` (603-632), `get_tool_call` (634-640),
`list_tool_calls` (642-649). RESEARCH Finding 5: the `Repository` protocol (29-53) has **zero**
budget/gateway methods today — that is the gap.

**Four methods to add** (Protocol entry + `RepositorySQL` + `InMemoryRepository` mirror, all
tenant-scoped per DUR-02):
- `record_budget_event(event: BudgetEvent) -> BudgetEvent` — mirror `upsert_tool_call`
- `budget_month_to_date(tenant_id, budget_owner, since) -> float` — **NO ANALOG** (see below)
- `record_gateway_event(event: GatewayEvent) -> GatewayEvent` — mirror `upsert_tool_call`
- `list_gateway_events(task_id, tenant_id) -> list[GatewayEvent]` — mirror `list_tool_calls`

**Protocol-widening pattern** (29-53) — add the four signatures here first:
```python
class Repository(Protocol):
    ...
    def upsert_tool_call(self, call: ToolCall) -> ToolCall: ...
    def list_tool_calls(self, task_id: str, tenant_id: str) -> list[ToolCall]: ...
    # NEW (Phase 3):
    # def record_budget_event(self, event: BudgetEvent) -> BudgetEvent: ...
    # def budget_month_to_date(self, tenant_id: str, budget_owner: str, since: datetime) -> float: ...
    # def record_gateway_event(self, event: GatewayEvent) -> GatewayEvent: ...
    # def list_gateway_events(self, task_id: str, tenant_id: str) -> list[GatewayEvent]: ...
```
> Note: protocol-widening requires the **same method on all THREE** (`Protocol`,
> `RepositorySQL`, `InMemoryRepository`) or the in-memory POC drifts from durable. This is the
> established Phase-1 widening dependency (MEMORY 5577).

**Write pattern — mirror `upsert_tool_call`** (603-632), simpler (append-only, no upsert needed
since `budget_event_id`/`gateway_event_id` are unique; `ON CONFLICT DO NOTHING` for idempotency):
```python
def upsert_tool_call(self, call: ToolCall) -> ToolCall:
    from psycopg.types.json import Jsonb
    with self._pool.connection() as conn:
        conn.execute(
            "INSERT INTO tool_calls (tool_call_id, task_id, tenant_id, ...) "
            "VALUES (%s,%s,%s,...) "
            "ON CONFLICT (tool_call_id) DO UPDATE SET ...",
            (call.tool_call_id, call.task_id, call.tenant_id, ...),
        )
    return call
```
> Columns for the new writers come from `migrations/0001_init.sql` lines 201-229 (verbatim
> `budget_ledger` / `gateway_events` column lists). Use `%s` placeholders only — no value
> interpolation (the file-wide invariant, repository.py 191).

**List pattern — mirror `list_tool_calls`** (642-649), tenant-scoped WHERE (DUR-02):
```python
def list_tool_calls(self, task_id: str, tenant_id: str) -> list[ToolCall]:
    with self._pool.connection() as conn:
        rows = conn.execute(
            f"SELECT {_TOOL_CALL_COLS} FROM tool_calls "
            "WHERE task_id = %s AND tenant_id = %s ORDER BY created_at",
            (task_id, tenant_id),
        ).fetchall()
    return [_row_to_tool_call(r) for r in rows]
```
> Add a `_row_to_gateway_event` / `_row_to_budget_event` helper + `_GATEWAY_COLS` /
> `_BUDGET_COLS` constants, mirroring `_row_to_tool_call` (254-284) and `_TOOL_CALL_COLS`
> (428-432).

**`budget_month_to_date` — NO ANALOG (net-new aggregate).** Every existing `RepositorySQL`
read is `get_*`/`list_*`; there is **no SUM/aggregate read** anywhere in the file. Do NOT
force-fit it onto a `list_*` analog. The closest *WHERE-shape* reference is the tenant-scoped
`list_tool_calls` (642-649); the aggregate itself is new SQL over the existing
`idx_budget_owner_month` index (0001 line 213-214):
```python
def budget_month_to_date(self, tenant_id, budget_owner, since) -> float:
    with self._pool.connection() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(estimated_cost_usd), 0) FROM budget_ledger "
            "WHERE tenant_id = %s AND budget_owner = %s AND created_at >= %s",
            (tenant_id, budget_owner, since),
        ).fetchone()
    return float(row[0])
```
> D-05 per-task variant = the same SUM with an extra `AND task_id = %s` predicate, or compute
> from `list`-style rows. No schema change.

**InMemory mirror — match `list_tool_calls` in-memory shape** (119-125): filter the new
`self._budget_events` / `self._gateway_events` lists by tenant + sum in Python. Keeps
`make test` green without Postgres (the file-wide mirror invariant, repository.py 187).

---

### `src/agent_mesh/worker/budget.py` (service, durable-ledger-backed)

**Analog:** self — `BudgetTracker.check`/`record`/`month_to_date` (22-46). **Keep the API
shape** (D-04: "the API shape D-04 keeps"); swap the in-memory `_spent` dict (25) for
repository reads/writes.

**Current API to preserve** (22-46):
```python
class BudgetTracker:
    def month_to_date(self, budget_owner: str) -> float:        # → repo.budget_month_to_date(...)
        return self._spent[budget_owner]
    def check(self, budget_owner: str, incremental_usd: float) -> None:   # reads MTD, raises BudgetExceeded
        if self._spent[budget_owner] + incremental_usd > self._cap:
            raise BudgetExceeded(...)
    def record(self, event: BudgetEvent) -> BudgetEvent:        # → repo.record_budget_event(event)
        self._spent[event.budget_owner] += event.estimated_cost_usd
        ...
```
**Rewire:** `__init__(self, repo: Repository, settings)`; `month_to_date` →
`repo.budget_month_to_date(tenant_id, budget_owner, month_start)`; `check` reads MTD from the
ledger then raises `BudgetExceeded` (18-20, kept verbatim); `record` → `repo.record_budget_event`.
D-05: `check` enforces `min(per_user_remaining, per_task_remaining)` using
`settings.model_monthly_budget_usd` (per-user cap) and a new `model_per_task_cap` (defaults to
per-user). The `BudgetExceeded` raise → caller records a `gateway_event` (`provider_status=None`,
note=budget_halt) per RESEARCH Finding 2.

**Pre/post-call wiring** (RESEARCH Finding 2 — `litellm` cost helpers, no hand-rolled price
tables): pre-call `cost_per_token(prompt_tokens=counted, completion_tokens=max_tokens)`
(conservative upper bound) → `check()`; post-call `completion_cost(completion_response=...)` →
`record()`. The ledger stores the **actual** post-call cost.

---

### `src/agent_mesh/worker/model_gateway.py` (service/provider, model call)

**Analog:** self — `resolve_route`/`DEFAULT_PROFILE` (41-54) and `get_chat_model` (66-88) are
the **D-06 egress chokepoint** today (sets `api_base` from settings, line 86). Extend; do not
replace.

**Current chokepoint** (84-88):
```python
return ChatLiteLLM(            # pragma: no cover - needs creds
    model=route.model,
    api_base=settings.model_gateway_base_url,
    max_tokens=settings.model_max_tokens,
)
```

**Lazy optional-dep import gate to mirror** (57-63, 75-82) — keep the importable-without-deps
degradation:
```python
def langchain_available() -> bool:
    try:
        import langchain_core  # noqa: F401
        return True
    except Exception:
        return False
```

**NEW (RESEARCH Finding 1, D-09) — Router loader + binding subclass** (no in-repo analog; the
yaml-load + subclass are net-new, but follow the lazy-import pattern above):
```python
def build_router(config_path="config/model_gateway.config.yaml"):
    import yaml
    from litellm import Router
    cfg = yaml.safe_load(open(config_path))
    rs = cfg.get("router_settings", {})
    return Router(model_list=cfg["model_list"], fallbacks=rs.get("fallbacks"),
                  num_retries=rs.get("num_retries", 2), timeout=rs.get("timeout", 120))

class RouterChatLiteLLM(ChatLiteLLM):
    """The validator at langchain_litellm/.../litellm.py:558 clobbers `client`
    with the bare litellm module, so route completion through a held Router."""
    _router: object = None
    def completion_with_retry(self, run_manager=None, **kwargs):
        return self._router.completion(**kwargs)
    async def acompletion_with_retry(self, run_manager=None, **kwargs):
        return await self._router.acompletion(**kwargs)
```
> **PITFALL (RESEARCH Pitfall 1):** `ChatLiteLLM(client=router)` is **silently ignored** — the
> subclass is mandatory. `get_chat_model()` returns `RouterChatLiteLLM` with `model=` a Router
> *deployment name* (`"high-complexity"` from the yaml `model_name`), not a raw provider id.
> Verify with a trivial `.invoke` against a stubbed deployment before building (RESEARCH A3).

> **D-06 relocation (RESEARCH Finding 6 / Pitfall 3):** under the Router, the egress `api_base`
> lives **per-deployment** in `model_list[*].litellm_params.api_base` (yaml lines 24/34/45/54),
> NOT on the chat model. The guard test asserts the **Router's** routes, plus an AST/grep guard
> that no path constructs `ChatAnthropic`/`ChatVertexAI`/raw `litellm.completion` directly. Map
> `cf_enabled` + `cf_aig_wrapper_url` → settings (below).

---

### `src/agent_mesh/observability.py` (utility/provider, event-driven span emission)

**Analog (reuse as-is):** `trace_metadata()` (38-62) already builds the **exact** shared-metadata
dict OBS-01 needs (`tenant_id, client_slug, task_id, session_id, requester_id, entrypoint,
agent_role, model_route_profile, approval_state`). It becomes the **span-attribute source** (D-07).
Reuse verbatim; set each key as a span attribute on the root span.

**Migrate-this seam (NOT a copy-me pattern):** `get_langchain_callback` (65-84) uses
```python
from langfuse.callback import CallbackHandler   # line 76 — DEAD under langfuse 4.7.1
```
This is `ModuleNotFoundError` on the installed v4 (RESEARCH Pitfall 2). The v4 path is
`from langfuse.langchain import CallbackHandler`. **Migrate, don't mirror.**

**Feature-gate pattern to mirror** (29-35) for the new `tracing_available()` / OTel init:
```python
def langfuse_available() -> bool:
    try:
        import langfuse  # noqa: F401
        return True
    except Exception:
        return False
```

**NEW (RESEARCH Finding 3) — `init_tracing(settings, *, test_exporter=None)`:** TracerProvider +
`BatchSpanProcessor`; `InMemorySpanExporter` when `test_exporter` is passed (CI, no server),
else OTLP-HTTP exporter to `settings.otel_exporter_otlp_endpoint` (Langfuse default consumer) +
a parallel-SIEM seam (a second processor). **No in-repo analog** — list under No Analog Found.

---

### `src/agent_mesh/worker/graph.py` (orchestration node, delegation behind gate)

**Analog:** self — `_model_credentials_present()` (66-81) is the cred gate the real-model
delegation hides behind; node bodies (84-135) currently take the deterministic path. Phase 3
wires real `get_chat_model()` delegation **inside** the existing `if _model_credentials_present():`
branch (e.g. planner_node 87-90 already has the `build_roster()` placeholder).

**Gate pattern to keep** (66-81, 84-92):
```python
def _model_credentials_present() -> bool:
    return any(os.getenv(v) for v in
        ("MODEL_GATEWAY_BASE_URL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "VERTEX_PROJECT"))

def planner_node(state: MeshState) -> MeshState:
    if _model_credentials_present():   # pragma: no cover - Phase 3 wires real delegation here
        from agent_mesh.worker.roster import build_roster
        build_roster()
    plan = f"[plan] steps to address: {state.get('prompt','')[:80]}"   # deterministic fallback stays
    return {"plan": plan}
```
> **Invariant:** nodes still degrade to deterministic, role-distinct output when creds absent
> (D-01/D-02 — `make test` green, no model calls). RF-1 security (10-16, 138-167): `write_gate`
> never executes the write and never trusts an approver identity from the resumed value. Do not
> relax when adding spans.

---

### `src/agent_mesh/worker/orchestrator.py` (controller/adapter, request-response)

**Analog:** self — `_run_langgraph` (200-243). The `OrchestrationResult` dataclass already
declares `trace_id: str | None = None` (124-129); P2 left it unset (242, 305). D-07 sets it.

**One-field extension** — keep the dataclass shape stable (consumed by runner, ledger, tests):
```python
@dataclass
class OrchestrationResult:
    summary: str
    proposed_writes: list[dict] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    trace_id: str | None = None     # D-07: SET it (was left unset in P2 — lines 242, 305)
```
Set `trace_id` from the per-task root (RESEARCH Finding 3: `langfuse.create_trace_id()` /
`get_current_trace_id`) in both `_run_langgraph` (237-243) and the stack-path `resume_mesh`
(300-306). Cross-process: store W3C `traceparent` in the task record at ingress, restore in the
worker (RESEARCH Pitfall 4 — OTel context does NOT cross Pub/Sub).

---

### `src/agent_mesh/services/approvals.py` (service, event-driven span only)

**Analog:** self — `record_decision` (179-197) and `open_approval` (158-176) are the approval
write points. D-07 wraps them with a **read-only OTel span** carrying `trace_metadata()` attrs.

**Hard constraint (do NOT weaken SEC-01/SEC-02):** the span is **telemetry only**. The signed
HMAC token (`verify_approval_token` 113-155, fails closed on no secret, line 129-130), the
payload-hash binding (`payload_hash` 41-45, `is_approved` 200-210), and the cross-task replay
guard (138-139) stay intact. **Never branch on span data**; the approver is derived solely from
the signed token. The span observes the decision event; it is never a second approval path.

---

### `src/agent_mesh/settings.py` (config, request-response)

**Analog:** self — the model/langfuse field block (42-75). Mirror the `field(default_factory=...)`
+ env-var pattern; reuse the `_bool` helper (14-18) for flags.

**Pattern to mirror** (47-75):
```python
model_gateway_base_url: str = field(default_factory=lambda: os.getenv("MODEL_GATEWAY_BASE_URL", ...))
model_monthly_budget_usd: float = field(default_factory=lambda: float(os.getenv("MODEL_MONTHLY_BUDGET_USD", "50")))
langfuse_host: str = field(default_factory=lambda: os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"))
```
**Add** (RESEARCH touch-map): `cf_enabled: bool = field(default_factory=lambda: _bool("CF_ENABLED"))`,
`cf_aig_wrapper_url`, `otel_exporter_otlp_endpoint`, `model_per_task_cap: float` (defaults to
`model_monthly_budget_usd`). Langfuse keys (67-75) already present — reuse.

---

### `pyproject.toml` (config) — `runtime` extra (18-27) + pytest config (57-59)

**Analog:** self — existing `runtime` extra (18-27). RESEARCH Standard Stack deltas:
```toml
runtime = [
    # ...
    "litellm>=1.40",                                 # OK (1.83.7 in venv)
    "langchain-litellm>=0.6",                        # was >=0.1 — bump for stable client shape
    "langfuse>=4,<5",                                # was >=2.0 — v2 import path is DEAD under v4
    "opentelemetry-api>=1.42",                       # NEW
    "opentelemetry-sdk>=1.42",                       # NEW
    "opentelemetry-exporter-otlp-proto-http>=1.42",  # NEW (HTTP, NOT gRPC — gRPC not installed)
]
```
**pytest config (57-59):** add a `live` marker registration + (RESEARCH Pitfall 5) confirm
`filterwarnings` does NOT escalate the Python-3.14 pydantic-v1 `UserWarning` to error, or the
green-suite invariant breaks. Add `make test-live` (drives `pytest -m live`) to the Makefile
(current targets: `test` 30-31, `smoke` 40-41).

---

### Config files (self-analog, schema-consistency)

- `config/model_gateway.config.yaml` — **source of truth**, already complete (model_list with
  per-route `api_base: os.environ/CF_AIG_WRAPPER_URL` lines 24/34/45/54, `router_settings.fallbacks`
  61-67, `success_callback:[langfuse,otel]` 75, `general_settings.max_budget:50` 84). The loader
  READS it (Finding 1). Proxy-only fields `master_key` (81) / `max_budget` (84) are **prod-proxy
  config asserted structurally** (D-09 / Finding 6) — config test asserts present/well-formed,
  never executed in-process.
- `manifests/deployment.manifest.yaml` — **CONTEXT lists this; RESEARCH touch-map omits it.**
  Add `cf_*`/OTLP/`per_task_cap` keys + keep `model_routes` schema-consistent with the new
  `settings.py` fields. Analog = its own existing model/langfuse/budget entries. Do NOT drop it.

---

## Shared Patterns

### Stub-fallback degradation (the phase's master invariant — CLAUDE.md "no cloud deps")
**Sources:** `model_gateway.langchain_available` (57-63), `observability.langfuse_available`
(29-35), `orchestrator.langgraph_available`/`deep_agents_available` (132-151),
`graph._model_credentials_present` (66-81).
**Apply to:** every heavy seam touched this phase. Each new live path (Router, OTel OTLP export,
langfuse prompt fetch, real model delegation) MUST degrade to a deterministic stub / in-memory /
local-default when the optional dep or cred is absent. D-02's opt-in live lane is the Phase-3
expression of this.
```python
def langfuse_available() -> bool:
    try:
        import langfuse  # noqa: F401
        return True
    except Exception:
        return False
```

### Lazy optional-dep import (importable-without-runtime)
**Sources:** `get_chat_model` (75-82), `RepositorySQL.__init__` (464-472 — `from psycopg_pool
import ConnectionPool` inside `__init__`), `orchestrator._select_checkpointer` (108-110).
**Apply to:** Router/litellm imports, OTel exporter imports, langfuse v4 imports. Import inside
the function/method, never at module top, so the contract layer stays importable in a minimal env.

### Tenant-scoped WHERE on every read (DUR-02)
**Sources:** `list_tool_calls` (642-649), `list_approvals` (687-694), `list_events` (593-600) —
all carry `WHERE ... AND tenant_id = %s`.
**Apply to:** `budget_month_to_date`, `list_gateway_events` (every new budget/gateway read). A
cross-tenant budget read is the named Information-Disclosure threat (RESEARCH Security Domain).

### Protocol + RepositorySQL + InMemory triple-mirror
**Source:** every existing repo method appears in all three (Protocol 29-53, RepositorySQL
454-830, InMemoryRepository 56-181).
**Apply to:** the four new budget/gateway methods — add to all three or durable/in-memory drift.
This is the Phase-1 protocol-widening dependency (MEMORY 5577).

### `%s`-placeholder-only SQL + `Jsonb` adaptation + `_enum_value`
**Sources:** repository.py 191 (invariant), `Jsonb` use (481, 574, 604), `_enum_value` (194-203).
**Apply to:** the new budget/gateway writers (`BudgetEvent`/`GatewayEvent` are flat — no enums,
no JSONB columns per 0001 lines 201-229 — so `Jsonb`/`_enum_value` are likely unneeded, but the
`%s`-only rule is absolute).

### Opt-in live lane = skip-when-unset fixture + optional-extra split (D-02)
**Sources:** `tests/conftest.py` `pg_dsn` (skip when `TEST_DATABASE_URL` unset, 71-78),
`agents_stack` (skip unless `.[agents]` importable, 82-94, reusing the orchestrator import gates),
`sql_repo` (96-105); the `runtime`/`agents` optional-extra split in `pyproject.toml` (18-44).
**Apply to:** the new `live`-marked tests + the `InMemorySpanExporter` / stubbed-Router fixtures.
Register a `live` marker; `make test-live` drives `pytest -m live` with the user's keys + a
cents budget cap. Default `make test` stays on the stub/in-memory path. Mirror `agents_stack`'s
"reuse the import gate, don't re-derive a probe" rule for any new live-creds gate.

---

## No Analog Found

Net-new constructs with **no in-repo pattern to copy** — planner uses RESEARCH Findings instead:

| Construct | Role | Data Flow | Reason / RESEARCH ref |
|-----------|------|-----------|------------------------|
| `budget_month_to_date` SUM aggregate | persistence | aggregate read | No SUM/aggregate read exists in repository.py; net-new SQL on `idx_budget_owner_month` (Finding 5) |
| `RouterChatLiteLLM` subclass + `build_router` loader | provider binding | request-response | No litellm Router usage exists; validator-clobber shim is net-new (Finding 1 / Pitfall 1) |
| `init_tracing` OTel TracerProvider + OTLP/in-memory exporter | telemetry transport | event-driven | No OTel anywhere today; dep absent from pyproject (Finding 3) |
| `InMemorySpanExporter` CI fixture | test util | event-driven | New test seam (ships with otel-sdk; Finding 3) |
| D-06 AST/grep direct-provider-import guard test | guard/test | static analysis | No import-guard test exists; net-new (Finding 6 / Pitfall 3) |
| yaml `api_base` config-assertion test | config/test | n/a | New structural assertion over `model_list` (Finding 6) |
| `mock_testing_fallbacks` stub-lane cascade test | test | request-response | New test using the litellm Router hook (Finding 4) |
| langfuse v4 prompt fetch-with-fallback + dataset/eval seed | provider | request-response | `get_langchain_callback` (dead v2) is the only langfuse code; v4 prompt/dataset API is net-new (Finding 7 / D-08) |
| W3C `traceparent` propagation across task record | telemetry | event-driven | New cross-process correlation field; OTel context does not cross Pub/Sub (Pitfall 4) |

---

## Metadata

**Analog search scope:** `src/agent_mesh/{worker,services}`, `src/agent_mesh/{observability,settings}.py`,
`contracts/models.py`, `migrations/0001_init.sql`, `config/model_gateway.config.yaml`,
`tests/conftest.py`, `pyproject.toml`, `Makefile`.
**Files read (line ranges):** model_gateway.py 1-89; budget.py 1-46; observability.py 1-85;
repository.py 1-854; orchestrator.py 1-307; graph.py 1-195; approvals.py 1-211; settings.py 1-92;
contracts/models.py 210-264; migrations/0001_init.sql 195-230; config yaml 1-86; conftest.py
1-105; pyproject.toml 1-70 + targeted greps; Makefile (targets).
**Pattern extraction date:** 2026-06-06

## PATTERN MAPPING COMPLETE
