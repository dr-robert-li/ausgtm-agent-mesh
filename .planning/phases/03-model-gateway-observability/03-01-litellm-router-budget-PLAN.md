---
phase: 03-model-gateway-observability
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  - Makefile
  - src/agent_mesh/settings.py
  - src/agent_mesh/services/repository.py
  - src/agent_mesh/worker/budget.py
  - src/agent_mesh/worker/model_gateway.py
  - src/agent_mesh/worker/graph.py
  - tests/conftest.py
  - tests/test_model_gateway_router.py
  - tests/test_budget_ledger.py
autonomous: true
requirements: [GW-01]
must_haves:
  truths:
    - "An in-process litellm.Router is built from config/model_gateway.config.yaml (model_list + router_settings.fallbacks + num_retries) — cascades/retries run in-process (D-09)"
    - "RouterChatLiteLLM.invoke() provably routes the completion call through the held Router (asserted by a stubbed-Router unit test in the default suite, NOT assumed) — this defeats the validator clobber at langchain_litellm litellm.py:558"
    - "Budget enforcement is durable-ledger-backed: pre-call check() reads month-to-date from budget_ledger (tenant-scoped) and raises BudgetExceeded → clean halt + a gateway_event recorded; post-call record() persists actual cost (D-04)"
    - "$50/month per-user (budget_owner) is the hard cap that halts; per_task_cap defaults to the per-user cap; every ledger row tagged with task_id (D-05)"
    - "Default make test / make smoke stay GREEN with no cloud deps; the live lane (pytest -m live) is opt-in and never required by the default suite (D-02)"
    - "general_settings.max_budget:50 is asserted by config only — it is INERT in the in-process runtime; the durable ledger is the SOLE enforcer (D-04/D-09)"
  artifacts:
    - path: "src/agent_mesh/worker/model_gateway.py"
      provides: "build_router() yaml loader + RouterChatLiteLLM subclass; get_chat_model() returns a Router-backed model; D-06 api_base relocated to per-route model_list (for 03-02 to guard)"
      contains: "class RouterChatLiteLLM"
    - path: "src/agent_mesh/worker/budget.py"
      provides: "BudgetTracker rewired to durable ledger (repo-backed check/record/month_to_date), per_task_cap enforcement; API shape preserved"
      contains: "def budget_month_to_date"
    - path: "src/agent_mesh/services/repository.py"
      provides: "4 new tenant-scoped methods on Protocol + RepositorySQL + InMemoryRepository (record_budget_event, budget_month_to_date, record_gateway_event, list_gateway_events)"
      contains: "def budget_month_to_date"
    - path: "src/agent_mesh/settings.py"
      provides: "model_per_task_cap + cf_enabled + cf_aig_wrapper_url + otel_exporter_otlp_endpoint fields (shared scaffolding for wave-2 plans)"
      contains: "model_per_task_cap"
    - path: "pyproject.toml"
      provides: "runtime-extra pins (litellm>=1.40, langchain-litellm>=0.6, langfuse>=4,<5, +3 OTel deps) + live pytest marker; filterwarnings does not escalate Py-3.14 pydantic-v1 UserWarning to error"
      contains: "langfuse>=4"
    - path: "tests/conftest.py"
      provides: "live marker + stubbed-Router fixture + InMemorySpanExporter fixture (shared scaffolding consumed by 03-02 and 03-03)"
      contains: "stub_router"
    - path: "tests/test_model_gateway_router.py"
      provides: "GW-01: Router built from yaml; RouterChatLiteLLM.invoke routes through held Router (stubbed)"
      contains: "def test_router_chat_litellm_routes_through_router"
    - path: "tests/test_budget_ledger.py"
      provides: "GW-01: pre-call check halt + post-call record write budget_ledger tenant-scoped; per-task cap"
      contains: "BudgetExceeded"
  key_links:
    - from: "src/agent_mesh/worker/model_gateway.py"
      to: "litellm.Router"
      via: "RouterChatLiteLLM.completion_with_retry -> self._router.completion(**kwargs)"
      pattern: "self\\._router\\.completion"
    - from: "src/agent_mesh/worker/budget.py"
      to: "src/agent_mesh/services/repository.py"
      via: "check() reads budget_month_to_date; record() calls record_budget_event"
      pattern: "budget_month_to_date|record_budget_event"
    - from: "src/agent_mesh/worker/model_gateway.py"
      to: "config/model_gateway.config.yaml"
      via: "build_router() yaml.safe_load of model_list + router_settings"
      pattern: "model_list"
---

<objective>
Land the live in-process LiteLLM control plane (GW-01): a real `litellm.Router` built from
`config/model_gateway.config.yaml` with in-process cascades/retries (D-09), bound into LangChain
via a `RouterChatLiteLLM` subclass that defeats the validator clobber, and a durable-ledger budget
enforcer that halts cleanly at the USD $50/month per-user cap with per-task attribution (D-04/D-05).

THE LOAD-BEARING SEAM (RESEARCH Finding 1 / Pitfall 1): `langchain_litellm.ChatLiteLLM`'s pydantic
validator at `litellm.py:558` runs `values["client"] = litellm` UNCONDITIONALLY, so
`ChatLiteLLM(client=router)` is silently ignored — the Router never executes and budget/cascade are
bypassed with NO error. The fix is the `RouterChatLiteLLM` subclass overriding
`completion_with_retry`/`acompletion_with_retry` to call a held Router. `Router.completion(model,
messages, **kwargs)` is signature-compatible with `litellm.completion`. This plan MUST prove
`.invoke()` routes through the held Router with a deterministic stubbed-Router unit test — not assume it.

This plan also lays the SHARED WAVE-2 SCAFFOLDING (settings fields, pyproject pins + live marker,
conftest fixtures, Makefile target) so 03-02 and 03-03 own zero overlapping files and run parallel.

Purpose: GW-01 — live gateway routing to Anthropic-direct + Vertex AI with cascades and a durable
per-user/per-task budget. The ledger is the SOLE enforcer in the in-process runtime (D-04/D-09); this
IS the GW-01 "gateway enforces budget" control-plane requirement, satisfied deliberately, not as a gap.
Output: Router loader + binding subclass, durable budget ledger, 4 repository methods, shared test scaffolding.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@CLAUDE.md
@.planning/phases/03-model-gateway-observability/03-CONTEXT.md
@.planning/phases/03-model-gateway-observability/03-RESEARCH.md
@.planning/phases/03-model-gateway-observability/03-PATTERNS.md

<interfaces>
<!-- Tables + models ALREADY EXIST (RESEARCH Finding 5). Do NOT add a migration. -->
From migrations/0001_init.sql (lines 201-229) — budget_ledger columns:
  budget_event_id, tenant_id, client_slug, budget_owner, task_id, model,
  prompt_tokens, completion_tokens, estimated_cost_usd NUMERIC(12,6), created_at
  index idx_budget_owner_month ON (tenant_id, budget_owner, created_at)
From migrations/0001_init.sql (lines 216-229) — gateway_events columns:
  gateway_event_id, tenant_id, client_slug, task_id, cf_aig_request_id,
  litellm_request_id, provider, model_route, provider_status, dlp_action, created_at
From contracts/models.py — BudgetEvent (line 219), GatewayEvent (line 235), both tenant-scoped.

From litellm (venv 1.83.7, VERIFIED):
  Router(model_list, fallbacks, num_retries, timeout) ; Router.completion(model, messages, **kwargs)
  token_counter(model, messages) ; cost_per_token(model, prompt_tokens, completion_tokens)
  completion_cost(completion_response=...)
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Dependency pins + shared test scaffolding (Wave 0 gaps)</name>
  <read_first>
    - pyproject.toml (runtime extra lines 18-27; pytest config lines 57-59)
    - Makefile (test target ~30-31, smoke ~40-41)
    - src/agent_mesh/settings.py (model/langfuse field block 42-75; _bool helper 14-18)
    - tests/conftest.py (pg_dsn skip-when-unset 71-78; agents_stack gate 82-94; sql_repo 96-105)
    - .planning/phases/03-model-gateway-observability/03-RESEARCH.md (Standard Stack install delta; Wave 0 Gaps; Pitfall 5)
  </read_first>
  <action>
    In pyproject.toml `runtime` extra, set `litellm>=1.40`, bump `langchain-litellm>=0.6`, change
    `langfuse>=2.0` → `langfuse>=4,<5` (v2 import path is DEAD under installed 4.7.1), and ADD
    `opentelemetry-api>=1.42`, `opentelemetry-sdk>=1.42`, `opentelemetry-exporter-otlp-proto-http>=1.42`
    (HTTP exporter only — gRPC is NOT installed). Register a `live` marker under
    `[tool.pytest.ini_options].markers`. Verify `filterwarnings` does NOT escalate warnings to error
    (Py-3.14 pydantic-v1 UserWarning would break the green-suite invariant — leave warnings as warnings;
    if a `filterwarnings = error` exists, add ignore entries for the pydantic-v1 Py-3.14 UserWarning).
    Add a `test-live` Makefile target that runs `pytest -m live`; keep `test` driving the deterministic
    stub lane (no `-m live`). In settings.py add (mirror the `field(default_factory=lambda: os.getenv(...))`
    pattern and reuse `_bool`): `model_per_task_cap: float` (defaults to `model_monthly_budget_usd`),
    `cf_enabled: bool` (via `_bool("CF_ENABLED")`), `cf_aig_wrapper_url`, `otel_exporter_otlp_endpoint`.
    In tests/conftest.py add: a `live`-marker-aware skip fixture mirroring `pg_dsn`'s skip-when-unset
    shape (skip when provider creds unset), a `stub_router` fixture returning a fake object whose
    `completion(**kwargs)`/`acompletion(**kwargs)` record the call and return a minimal ModelResponse-like
    stub, and an `InMemorySpanExporter` fixture (imported from `opentelemetry.sdk.trace.export.in_memory_span_exporter`).
  </action>
  <verify>
    <automated>python -c "import tomllib;d=tomllib.load(open('pyproject.toml','rb'));r=' '.join(d['project']['optional-dependencies']['runtime']);assert 'langfuse>=4' in r and 'opentelemetry-sdk' in r and 'langchain-litellm>=0.6' in r, r" && grep -q "model_per_task_cap" src/agent_mesh/settings.py && grep -q "stub_router" tests/conftest.py && grep -q "test-live" Makefile</automated>
  </verify>
  <acceptance_criteria>
    - `pyproject.toml` runtime extra contains `langfuse>=4,<5`, the 3 OTel deps, `langchain-litellm>=0.6`, `litellm>=1.40`
    - `live` marker registered; `make test-live` exists and runs `pytest -m live`
    - `make test` still green with no cloud deps (no provider/Postgres/Langfuse creds present)
    - settings.py exposes `model_per_task_cap`, `cf_enabled`, `cf_aig_wrapper_url`, `otel_exporter_otlp_endpoint`
    - conftest.py exposes `stub_router` and an InMemorySpanExporter fixture (consumed by 03-02 / 03-03)
  </acceptance_criteria>
  <done>Pins + marker + Makefile target + settings fields + conftest fixtures land; default suite stays green. NOTE: the 4 new settings fields (`otel_exporter_otlp_endpoint`, `cf_enabled`, `cf_aig_wrapper_url`, `model_per_task_cap`) are deliberately NOT synced to `manifests/deployment.manifest.yaml` in this phase — that manifest sync is INTENTIONALLY DEFERRED to Phase 5 / DEP-02, which owns deploy-readiness (PATTERNS.md flagged the manifest; keeping Phase 3 scope tight to runtime wiring). Do NOT add the manifest to files_modified here.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Durable budget ledger — repository methods + BudgetTracker rewire (GW-01)</name>
  <read_first>
    - src/agent_mesh/services/repository.py (Protocol 29-53; upsert_tool_call 603-632; get_tool_call 634-640; list_tool_calls 642-649; _row_to_tool_call 254-284; _TOOL_CALL_COLS 428-432; InMemoryRepository 56-181; %s-only invariant line 191)
    - src/agent_mesh/worker/budget.py (BudgetTracker.check/record/month_to_date 22-46; BudgetExceeded 18-20)
    - src/agent_mesh/contracts/models.py (BudgetEvent 219; GatewayEvent 235)
    - migrations/0001_init.sql (lines 201-229 — column lists; idx_budget_owner_month 213-214)
    - .planning/phases/03-model-gateway-observability/03-PATTERNS.md (repository.py section; budget.py section; budget_month_to_date NO-ANALOG note)
  </read_first>
  <behavior>
    - record_budget_event persists a BudgetEvent (append-only, ON CONFLICT DO NOTHING) and returns it
    - budget_month_to_date(tenant_id, budget_owner, since) returns SUM(estimated_cost_usd) for that tenant+owner since `since`; 0.0 when none; NEVER returns another tenant's rows
    - record_gateway_event persists a GatewayEvent; list_gateway_events(task_id, tenant_id) returns tenant-scoped rows ordered by created_at
    - BudgetTracker.check raises BudgetExceeded when month_to_date + incremental would exceed min(per_user_remaining, per_task_remaining)
    - BudgetTracker.record writes via repo.record_budget_event; month_to_date reads via repo.budget_month_to_date
    - InMemoryRepository methods mirror RepositorySQL behavior (tenant filter + Python SUM) so make test stays green without Postgres
  </behavior>
  <action>
    Add 4 methods to the `Repository` Protocol (29-53) AND `RepositorySQL` AND `InMemoryRepository`
    (the triple-mirror invariant — MEMORY 5577): `record_budget_event(event: BudgetEvent) -> BudgetEvent`
    (mirror `upsert_tool_call`, `%s`-only, `ON CONFLICT (budget_event_id) DO NOTHING`),
    `budget_month_to_date(tenant_id: str, budget_owner: str, since: datetime) -> float` (NET-NEW aggregate,
    no analog — `SELECT COALESCE(SUM(estimated_cost_usd),0) FROM budget_ledger WHERE tenant_id=%s AND
    budget_owner=%s AND created_at>=%s`, returns `float(row[0])`, uses idx_budget_owner_month),
    `record_gateway_event(event: GatewayEvent) -> GatewayEvent` (mirror `upsert_tool_call`),
    `list_gateway_events(task_id: str, tenant_id: str) -> list[GatewayEvent]` (mirror `list_tool_calls`,
    tenant-scoped WHERE). Add `_GATEWAY_COLS` / `_BUDGET_COLS` constants and `_row_to_gateway_event` /
    `_row_to_budget_event` helpers mirroring `_TOOL_CALL_COLS` / `_row_to_tool_call`. Rewire `budget.py`:
    `BudgetTracker.__init__(self, repo, settings)`; `month_to_date` → `repo.budget_month_to_date(tenant_id,
    budget_owner, month_start)`; `check(budget_owner, incremental_usd, *, tenant_id, task_id=None)` enforces
    `min(per_user_remaining, per_task_remaining)` using `settings.model_monthly_budget_usd` and
    `settings.model_per_task_cap`, keeping the `BudgetExceeded` raise (18-20) verbatim; `record` →
    `repo.record_budget_event(event)`. Keep the public check/record/month_to_date names (D-04).
  </action>
  <verify>
    <automated>pytest tests/test_budget_ledger.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - All 4 methods present on Repository Protocol, RepositorySQL, and InMemoryRepository (triple-mirror)
    - `budget_month_to_date` filters by tenant_id (a cross-tenant read returns 0.0 / no rows) — DUR-02
    - `BudgetTracker.check` raises `BudgetExceeded` when month-to-date + estimate exceeds the cap; per_task_cap honored
    - `BudgetTracker.record` persists a `BudgetEvent` carrying `task_id` (D-05 attribution)
    - On non-comment lines (`grep -vE '^[[:space:]]*#'`), `grep -c 'self\._spent\['` in budget.py returns 0 (the in-memory `_spent` dict is removed; a comment referencing it is allowed)
    - `pytest tests/test_budget_ledger.py -x -q` passes with no Postgres (InMemoryRepository path)
  </acceptance_criteria>
  <done>Budget enforcement is durable-ledger-backed, tenant-scoped, per-user+per-task; in-memory dict gone.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: In-process Router loader + RouterChatLiteLLM binding + real-model delegation (GW-01)</name>
  <read_first>
    - src/agent_mesh/worker/model_gateway.py (resolve_route/DEFAULT_PROFILE 41-54; get_chat_model + chokepoint 66-88; langchain_available gate 57-63)
    - src/agent_mesh/worker/graph.py (_model_credentials_present gate 66-81; planner_node real-delegation placeholder 84-92; node bodies 84-135; RF-1 write_gate 138-167)
    - config/model_gateway.config.yaml (model_list per-route api_base lines 24/34/45/54; router_settings.fallbacks 61-67; num_retries; success_callback 75)
    - .planning/phases/03-model-gateway-observability/03-RESEARCH.md (Finding 1; Pitfall 1; Assumption A3; Anti-Patterns)
    - .planning/phases/03-model-gateway-observability/03-PATTERNS.md (model_gateway.py section; graph.py section; lazy optional-dep import pattern)
  </read_first>
  <behavior>
    - build_router() loads model_list + router_settings.fallbacks + num_retries + timeout from the yaml and returns a litellm.Router
    - RouterChatLiteLLM.completion_with_retry(**kwargs) calls self._router.completion(**kwargs); acompletion_with_retry awaits self._router.acompletion(**kwargs)
    - get_chat_model(tier) returns a RouterChatLiteLLM whose _router is the (process-cached) Router and whose model= is the yaml deployment name (e.g. "high_complexity"), NOT a raw provider id
    - RouterChatLiteLLM.invoke() with a STUBBED Router records exactly one completion call on the stub (proves the override defeats the validator clobber — A3 made verifiable)
    - graph nodes still degrade to deterministic, role-distinct output when _model_credentials_present() is False (make test green, no model calls)
  </behavior>
  <action>
    In `model_gateway.py` add `build_router(config_path="config/model_gateway.config.yaml")` (lazy
    `import yaml` + `from litellm import Router` inside the function per the lazy-import invariant) loading
    `model_list`, `router_settings.fallbacks`, `num_retries` (default 2), `timeout` (default 120). Add
    `class RouterChatLiteLLM(ChatLiteLLM)` holding `_router` and overriding `completion_with_retry(self,
    run_manager=None, **kwargs)` → `self._router.completion(**kwargs)` and the async twin → `await
    self._router.acompletion(**kwargs)`. Rewrite `get_chat_model()` to construct `RouterChatLiteLLM(model=<yaml
    deployment name for tier>, max_tokens=settings.model_max_tokens)` and attach a process-cached Router;
    relocate the egress `api_base` so it lives PER-ROUTE in the Router's `model_list[*].litellm_params.api_base`
    (D-06 chokepoint relocation per RESEARCH Finding 6) — do NOT set `api_base` on the chat model. Do NOT
    pass `client=router` (silently clobbered). In `graph.py`, inside each node's existing
    `if _model_credentials_present():` branch, wire real delegation through `get_chat_model(tier)` while
    keeping the deterministic role-distinct fallback for the creds-absent path; pre-call estimate via
    `litellm.cost_per_token(prompt_tokens=token_counter(...), completion_tokens=settings.model_max_tokens)` →
    `budget.check(...)`, post-call `budget.record(...)` with `litellm.completion_cost(completion_response=...)`.
    Do NOT relax RF-1 in write_gate.
  </action>
  <verify>
    <automated>pytest tests/test_model_gateway_router.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `tests/test_model_gateway_router.py::test_router_chat_litellm_routes_through_router` asserts a `.invoke()` against a `stub_router` records exactly one completion call on the stub (NOT on bare litellm) — the load-bearing proof
    - `build_router()` returns a `litellm.Router` whose fallbacks/num_retries come from the yaml
    - `get_chat_model()` returns a `RouterChatLiteLLM`; `grep -n "api_base" src/agent_mesh/worker/model_gateway.py` shows api_base NOT set on the chat-model constructor (relocated to per-route)
    - On non-comment lines (`grep -vE '^[[:space:]]*#'`), `grep -cE 'ChatAnthropic|ChatVertexAI' src/agent_mesh/worker/graph.py` returns 0 (no direct-provider construction; comments allowed)
    - `make test` green with no creds — graph nodes take the deterministic fallback path
  </acceptance_criteria>
  <done>A real in-process Router routes via a binding subclass proven to defeat the validator clobber; budget wraps the call; stub path stays green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| worker → model provider | model call leaves the worker; must traverse get_chat_model() (D-06) |
| worker → budget_ledger (Postgres) | tenant-scoped reads/writes; cost data is per-tenant |
| yaml config → Router | model_list/fallbacks loaded; provider keys resolved by litellm from env at call time |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-03-01-01 | Tampering / cost abuse | model call bypassing the gateway | mitigate | get_chat_model() is the sole construction path; no ChatAnthropic/ChatVertexAI/raw litellm.completion in graph.py (Task 3 grep gate); full D-06 guard is 03-02 |
| T-03-01-02 | Information Disclosure | cross-tenant budget read (one tenant sees another's MTD) | mitigate | tenant-scoped WHERE on budget_month_to_date + list_gateway_events (DUR-02, Task 2) |
| T-03-01-03 | Denial of Service / cost | budget bypass — Router executes but ledger not checked | mitigate | pre-call check() raises BudgetExceeded before the call; durable ledger is the SOLE enforcer (max_budget:50 inert, D-04) |
| T-03-01-04 | Information Disclosure | provider key leaked into ledger/logs | mitigate | keys resolved by litellm from env at call time; never written to budget_ledger/gateway_events columns; keep V2 control |
| T-03-01-SC | Tampering | litellm/langfuse/otel installs | mitigate | RESEARCH Package Legitimacy Audit — all first-party-declared in pyproject, official OTel; no [ASSUMED]/[SUS] packages, no blocking checkpoint needed |
</threat_model>

<verification>
- `make test` GREEN with NO cloud deps (no provider keys, no Postgres, no Langfuse) — the master invariant.
- `pytest tests/test_model_gateway_router.py tests/test_budget_ledger.py -x -q` passes.
- The RouterChatLiteLLM `.invoke()`-routes-through-stub-Router assertion passes (the load-bearing GW-01 proof).
- No direct-provider client construction introduced (grep gate in Task 3).
- `make test-live` exists and is opt-in; default suite never requires `-m live`.
</verification>

<success_criteria>
GW-01 is locally provable: an in-process Router built from the yaml, bound via a subclass proven to
route through the held Router, with durable-ledger per-user/per-task budget enforcement that halts
cleanly — all while the default suite stays green with no cloud deps.
</success_criteria>

<output>
Create `.planning/phases/03-model-gateway-observability/03-01-SUMMARY.md` when done.
</output>
</content>
</invoke>
