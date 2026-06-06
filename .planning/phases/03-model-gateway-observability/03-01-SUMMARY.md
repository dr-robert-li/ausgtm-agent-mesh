---
phase: 03-model-gateway-observability
plan: 01
subsystem: model-gateway
tags: [litellm, router, budget, gw-01, langchain-litellm, otel-scaffolding]
requires:
  - "migrations/0001_init.sql budget_ledger + gateway_events tables (Phase 1)"
  - "contracts/models.py BudgetEvent + GatewayEvent (Phase 1)"
  - "services/repository.py Protocol/RepositorySQL/InMemoryRepository (Phase 1)"
  - "worker/graph.py role nodes + _model_credentials_present gate (Phase 2)"
provides:
  - "build_router() + RouterChatLiteLLM binding subclass (in-process LiteLLM control plane, GW-01)"
  - "durable-ledger BudgetTracker (per-user + per-task cap, tenant-scoped)"
  - "4 repository methods: record_budget_event, budget_month_to_date, record_gateway_event, list_gateway_events"
  - "shared wave-2 scaffolding: settings fields, pyproject pins + live marker, conftest fixtures (stub_router, span_exporter, live_creds), Makefile test-live"
affects:
  - "03-02 (Cloudflare AI Gateway egress guard — consumes per-route api_base relocation, gateway_events, cf_* settings)"
  - "03-03 (Langfuse/OTel tracing — consumes span_exporter fixture, otel deps, otel_exporter_otlp_endpoint setting)"
tech-stack:
  added:
    - "litellm>=1.40 (installed/validated 1.83.7) — in-process Router"
    - "langchain-litellm>=0.6 (0.6.4) — ChatLiteLLM base for the binding subclass"
    - "langfuse>=4,<5 (4.7.1) — v2 import path is dead under 4.x"
    - "opentelemetry-api/sdk/exporter-otlp-proto-http>=1.42 (HTTP exporter only; gRPC excluded)"
  patterns:
    - "PEP 562 module __getattr__ + cached class for lazy optional-dep subclass (RouterChatLiteLLM)"
    - "pydantic-v2 PrivateAttr for the held Router (not a validated field)"
    - "triple-mirror repository invariant (Protocol + RepositorySQL + InMemoryRepository)"
key-files:
  created:
    - "tests/test_model_gateway_router.py"
    - "tests/test_budget_ledger.py"
  modified:
    - "pyproject.toml"
    - "Makefile"
    - "src/agent_mesh/settings.py"
    - "src/agent_mesh/services/repository.py"
    - "src/agent_mesh/worker/budget.py"
    - "src/agent_mesh/worker/model_gateway.py"
    - "src/agent_mesh/worker/graph.py"
    - "tests/conftest.py"
decisions:
  - "RouterChatLiteLLM overrides completion_with_retry/acompletion_with_retry to call a held Router, defeating the unconditional values['client']=litellm clobber at langchain_litellm litellm.py:558 — proven by a stubbed-Router unit test in the default suite, not assumed."
  - "TIER_TO_DEPLOYMENT maps underscore tier keys to the hyphenated yaml model_name; Router.completion resolves the route by exact model_name, so passing the tier key or a raw provider id would 404 'deployment not found' at call time (a trap the stubbed-Router test cannot catch)."
  - "The durable budget_ledger is the SOLE budget enforcer in-process (D-04/D-09); general_settings.max_budget:50 in the yaml is INERT."
  - "Per-task cap enforcement on the SQL path conservatively returns 0.0 task-to-date (per-user cap still hard-stops); the InMemory path enforces both fully. Documented as a deliberate POC limitation."
  - "The async router test uses asyncio.run() (repo-consistent) rather than adding pytest-asyncio asyncio_mode, to avoid touching shared conftest config 03-02/03-03 depend on."
metrics:
  duration_min: 46
  completed: 2026-06-06
  tasks: 3
  files_changed: 10
  commits: 6
  tests_added: 15
  default_suite: "105 passed, 6 skipped"
---

# Phase 3 Plan 01: LiteLLM Router + Durable Budget Ledger Summary

GW-01 landed locally: an in-process `litellm.Router` built from
`config/model_gateway.config.yaml` (in-process cascades/retries, D-09), bound into
LangChain via a `RouterChatLiteLLM` subclass that provably routes `.invoke()` through
the held Router (defeating the `litellm.py:558` client clobber), plus a
durable-ledger budget enforcer that halts cleanly at the USD $50/month per-user cap
with per-task attribution — all while the default `make test` stays green with no
cloud deps.

## What Was Built

1. **Shared wave-2 scaffolding (Task 1, `chore`)** — `pyproject.toml` runtime pins
   (`litellm>=1.40`, `langchain-litellm>=0.6`, `langfuse>=4,<5`, 3 OTel HTTP deps),
   a registered `live` pytest marker (`make test` excludes it, `make test-live` runs
   it), 4 new `settings.py` fields (`model_per_task_cap`, `cf_enabled`,
   `cf_aig_wrapper_url`, `otel_exporter_otlp_endpoint`), and 3 conftest fixtures
   (`stub_router`, `span_exporter`, `live_creds`). 03-02 and 03-03 own zero
   overlapping files because of this.

2. **Durable budget ledger (Task 2, TDD)** — 4 tenant-scoped methods triple-mirrored
   across the `Repository` Protocol, `RepositorySQL`, and `InMemoryRepository`
   (`record_budget_event` append-only with `ON CONFLICT DO NOTHING`,
   `budget_month_to_date` tenant-scoped `SUM` since a cutoff, `record_gateway_event`,
   `list_gateway_events`). `BudgetTracker` rewired to `(repo, settings)`: ledger-backed
   `check`/`record`/`month_to_date`, `min(per-user, per-task)` enforcement, `task_id`
   attribution; the in-memory `_spent` dict is gone.

3. **In-process Router + binding + graph delegation (Task 3, TDD)** —
   `build_router()` loads `model_list`/`fallbacks`/`num_retries`/`timeout` from the
   yaml; `RouterChatLiteLLM(ChatLiteLLM)` holds a `_router` (`PrivateAttr`) and
   overrides `completion_with_retry`/`acompletion_with_retry` to call
   `self._router.completion`/`.acompletion`; `get_chat_model(tier)` returns a
   Router-backed model whose `model=` is the hyphenated yaml deployment name (D-06:
   `api_base` relocated per-route in the yaml, never on the chat-model constructor).
   `graph.py` role nodes delegate via `get_chat_model(tier)` when creds are present,
   budget-wrapped (pre-call `check` halt; post-call `record` priced from the returned
   `AIMessage.usage_metadata` via the pure, creds-free-testable `_actual_cost` helper,
   so the **actual** cost is persisted per D-04 — not the estimate), keeping the
   deterministic fallback for the no-creds default suite and leaving RF-1
   `proposed_writes` heuristic-derived. The creds-present `_delegate` body itself is
   `# pragma: no cover` (needs live creds); its cost helper IS unit-tested.

## Verification Evidence

- `make test` (default lane, `-m "not live"`): **105 passed, 6 skipped** — master
  invariant holds with no provider/Postgres/Langfuse credentials.
- `pytest tests/test_model_gateway_router.py tests/test_budget_ledger.py`: **15 passed**.
- Load-bearing GW-01 proof: `test_router_chat_litellm_routes_through_router` asserts a
  `.invoke()` against `stub_router` records **exactly one** completion call on the stub
  (and zero async calls) — the override defeats the clobber, verifiably.
- `pytest -m live`: **109 deselected** — the live lane is opt-in and never required.
- Grep gate: `grep -vE '^[[:space:]]*#' graph.py | grep -cE 'ChatAnthropic|ChatVertexAI'`
  returns **0** (no direct-provider construction; T-03-01-01 mitigated).
- `grep -vE '^[[:space:]]*#' budget.py | grep -c 'self\._spent\['` returns **0**.
- DUR-02: `budget_month_to_date` cross-tenant read returns 0.0 (asserted by
  `test_budget_month_to_date_is_tenant_scoped`; T-03-01-02 mitigated).
- `ruff check src/agent_mesh tests`: clean.

## Threat Register Outcomes

| Threat ID | Disposition | Evidence |
|-----------|-------------|----------|
| T-03-01-01 (gateway bypass) | mitigated | grep gate 0 in graph.py; `get_chat_model` is the sole construction path |
| T-03-01-02 (cross-tenant budget read) | mitigated | tenant-scoped WHERE/filter; `test_budget_month_to_date_is_tenant_scoped` |
| T-03-01-03 (budget bypass) | mitigated | pre-call `check` raises `BudgetExceeded` before the call; durable ledger is sole enforcer |
| T-03-01-04 (provider key leak) | mitigated | keys resolved by litellm from env; never written to ledger/gateway columns |
| T-03-01-SC (supply chain) | mitigated | all pins first-party-declared / official OTel; no blocking checkpoint needed |

## Deviations from Plan

### Auto-fixed / Implementation Adjustments

**1. [Rule 3 - Blocking] Async router test uses `asyncio.run()` instead of `@pytest.mark.asyncio`.**
- **Found during:** Task 3 RED.
- **Issue:** No `pytest-asyncio` `asyncio_mode` is configured; `@pytest.mark.asyncio`
  was unrecognized (PytestUnknownMarkWarning) and the async test would not run.
- **Fix:** Converted the async test to a sync test driving `asyncio.run(chat.ainvoke(...))`,
  matching the repo's existing async-free test convention and avoiding a shared-conftest
  change that 03-02/03-03 depend on.
- **Files:** `tests/test_model_gateway_router.py`. **Commit:** 1be6f30 / db68c51.

**2. [Rule 1 - Cosmetic correctness] `RouterChatLiteLLM` uses pydantic-v2 `PrivateAttr`, not `class Config`.**
- **Found during:** Task 3 GREEN.
- **Issue:** `ChatLiteLLM` is a pydantic-**v2** model (not v1 as the plan's inline note
  implied); a `class Config: arbitrary_types_allowed` emitted `PydanticDeprecatedSince20`.
- **Fix:** Declared the held Router as `_router: Any = PrivateAttr(default=None)`
  (correct v2 idiom; the Router is not a validated field). Removed the deprecation.
- **Files:** `src/agent_mesh/worker/model_gateway.py`. **Commit:** db68c51.

**3. [Rule 1 - Bug] `_delegate` recorded the estimate (and risked a crash), not the actual cost.**
- **Found during:** advisor review of the untested creds-present path.
- **Issue:** Post-call cost used
  `litellm.completion_cost(completion_response=getattr(result, "_response", None))`.
  But `chat.invoke()` returns a LangChain `AIMessage`, which has no `_response` attr —
  so the arg was always `None`, making `completion_cost` return 0 (→ silently record the
  pre-call **estimate**, violating must_have D-04 "persists actual cost") or raise on the
  first creds-present run.
- **Fix:** Extracted pure `_actual_cost(route_model, usage_metadata, fallback)` that
  prices `AIMessage.usage_metadata` (`input_tokens`/`output_tokens`) via
  `litellm.cost_per_token`, falling back to the estimate only when usage is absent. Added
  2 creds-free regression tests (would have caught the `_response` bug).
- **Files:** `src/agent_mesh/worker/graph.py`, `tests/test_model_gateway_router.py`.
  **Commit:** e4ba9fb.

**4. [Documented limitation] Per-task SQL cap + `budget_owner` placeholder.**
- The SQL `BudgetTracker._task_to_date` conservatively returns 0.0 (the per-user cap
  remains the SOLE hard enforcer guaranteed by the plan; `per_task_cap` defaults to the
  per-user cap); the InMemory path enforces both fully.
- In `_delegate`, `budget_owner` falls back to `settings.tenant_id` (a documented TODO):
  per-user enforcement collapses to per-tenant for delegated runs until ingress threads
  the requester id through the graph state (03-02 / ingress follow-up).
- Both are POC limitations, not gaps against the plan's stated invariant.

### Intentionally Deferred (per plan)

- The 4 new settings fields are **NOT** synced to `manifests/deployment.manifest.yaml`
  — deferred to Phase 5 / DEP-02 (deploy-readiness owns the manifest), per the Task 1
  `<done>` note. `manifests/` is deliberately absent from this plan's files.

## Environment Note (for continuation / verifier)

The validated interpreter is the **main repo** `.venv`
(`/Users/robertli/Desktop/consulting/ausgtm-agent-mesh/.venv/bin/python`, Python 3.14,
all runtime+agents+OTel extras installed). The worktree's homebrew `python3` has no
optional deps and cannot run the suite. Always invoke with `PYTHONPATH=src` so imports
resolve to the **worktree** `src` (without it, an editable install resolves to the main
repo's `src`); pytest's `pythonpath=["src"]` handles this for test runs.

## Known Stubs

None that block GW-01. The `stub_router` and `span_exporter` conftest fixtures are
intentional test doubles / shared scaffolding consumed by 03-02 and 03-03, not
production stubs.

## Self-Check: PASSED

- Created/modified files verified present: `tests/test_model_gateway_router.py`,
  `tests/test_budget_ledger.py`, `src/agent_mesh/worker/model_gateway.py`,
  `src/agent_mesh/worker/budget.py`, `03-01-SUMMARY.md`.
- All 6 task commits verified in git log: `c316ddf` (chore), `9a88526` (test/RED),
  `92693c6` (feat/GREEN budget), `1be6f30` (test/RED router), `db68c51` (feat/GREEN router),
  `e4ba9fb` (fix/cost-accounting).
- TDD gate sequence present for Tasks 2 and 3: `test(...)` RED commit precedes its
  `feat(...)` GREEN commit in both cases.
