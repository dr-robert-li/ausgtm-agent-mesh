---
phase: 03-model-gateway-observability
plan: 02
type: execute
wave: 2
depends_on: ["03-01"]
files_modified:
  - tests/test_d06_chokepoint.py
  - tests/test_cascade.py
  - tests/test_cascade_live.py
autonomous: true
requirements: [GW-02, GW-03]
must_haves:
  truths:
    - "A config-assertion test loads config/model_gateway.config.yaml and asserts every model_list[*].litellm_params.api_base resolves to the CF wrapper URL when CF_ENABLED is true (D-06 relocation per RESEARCH Finding 6)"
    - "A structural guard test fails if any path in src/ constructs a provider client (ChatAnthropic / ChatVertexAI / raw litellm.completion) outside get_chat_model() — agents never call providers directly (GW-02)"
    - "max_budget:50 and master_key are asserted present/well-formed in the yaml (prod-proxy config) but proven NOT executed in the in-process runtime — the durable ledger is the enforcer (D-04/D-09)"
    - "Stub-lane cascade test (make test, no creds): Router.completion(..., mock_testing_fallbacks=True) raises InternalServerError on the primary deployment → Router cascades to the configured fallback → the fallback deployment serves (GW-03 wiring proof, green CI)"
    - "Live-lane (pytest -m live) cascade: a real deterministic Vertex failure → real Anthropic fallback serves (D-01/D-03 — a real provider error is NOT a faked boundary)"
    - "Live-lane budget halt: a cents cap (MODEL_MONTHLY_BUDGET_USD=0.02) makes the pre-call estimate exceed the cap → BudgetExceeded → clean halt + a gateway_event recorded → no provider call beyond the cap (GW-03 halt half)"
  artifacts:
    - path: "tests/test_d06_chokepoint.py"
      provides: "GW-02: yaml api_base config-assertion + AST/grep direct-provider-import guard"
      contains: "litellm_params"
    - path: "tests/test_cascade.py"
      provides: "GW-03 stub lane: mock_testing_fallbacks cascade wiring proof (no creds)"
      contains: "mock_testing_fallbacks"
    - path: "tests/test_cascade_live.py"
      provides: "GW-03 live lane: real Vertex→Anthropic fallback + cents-cap clean halt (pytest -m live)"
      contains: "pytest.mark.live"
  key_links:
    - from: "tests/test_d06_chokepoint.py"
      to: "config/model_gateway.config.yaml"
      via: "load yaml, iterate model_list, assert api_base == CF wrapper when CF_ENABLED"
      pattern: "litellm_params"
    - from: "tests/test_d06_chokepoint.py"
      to: "src/agent_mesh"
      via: "AST/grep guard for forbidden direct-provider construction"
      pattern: "ChatAnthropic|ChatVertexAI"
    - from: "tests/test_cascade.py"
      to: "litellm.Router"
      via: "Router.completion(mock_testing_fallbacks=True) → fallback deployment"
      pattern: "mock_testing_fallbacks"
---

<objective>
Prove GW-02 (Cloudflare never-bypass / structural egress chokepoint) and GW-03 (model fallback +
budget-limit halt) entirely through tests, against the Router + budget machinery built in 03-01.

GW-02 is a STRUCTURAL proof, not a deployment (CF worker publish is Phase 5 / DEP-02): under the
in-process Router (D-09), the egress `api_base` lives PER-ROUTE in `model_list[*].litellm_params.api_base`
(RESEARCH Finding 6 / Pitfall 3) — NOT on the chat model. The D-06 guard therefore (a) asserts every
route's `api_base` resolves to the CF wrapper URL when CF_ENABLED, and (b) fails if any code path
constructs a provider client directly outside `get_chat_model()`. CF-disabled is a valid POC state.

GW-03 is a TWO-LANE proof (D-01 + D-02): the stub lane uses `Router.completion(...,
mock_testing_fallbacks=True)` (verified hook, raises InternalServerError → cascade) so the default
suite proves the fallback WIRING with no creds; the live lane induces a REAL deterministic Vertex
failure so a genuine error propagates and REAL Anthropic serves — a real provider error is NOT a faked
boundary (D-01). The budget-halt half reuses 03-01's durable-ledger check with a cents cap.

Purpose: GW-02 + GW-03 — agents never call providers directly; fallback and clean budget halt behave correctly.
Output: three test modules (one default-lane guard, one default-lane cascade, one live-lane cascade+halt).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@CLAUDE.md
@.planning/phases/03-model-gateway-observability/03-CONTEXT.md
@.planning/phases/03-model-gateway-observability/03-RESEARCH.md
@.planning/phases/03-model-gateway-observability/03-PATTERNS.md
@.planning/phases/03-model-gateway-observability/03-01-litellm-router-budget-PLAN.md

<interfaces>
<!-- Built in 03-01 (this plan TESTS them, never edits the src) -->
model_gateway.build_router() -> litellm.Router ; model_gateway.get_chat_model(tier) -> RouterChatLiteLLM
budget.BudgetTracker.check(budget_owner, incremental_usd, *, tenant_id, task_id=None) -> raises BudgetExceeded
repo.list_gateway_events(task_id, tenant_id) -> list[GatewayEvent]   (tenant-scoped)
conftest fixtures (from 03-01): stub_router, live-marker skip fixture
config/model_gateway.config.yaml: model_list[*].litellm_params.api_base = os.environ/CF_AIG_WRAPPER_URL (24/34/45/54);
  router_settings.fallbacks (61-67); general_settings.max_budget:50 (84); master_key (81)
litellm.Router.completion(..., mock_testing_fallbacks=True)  # VERIFIED router.py:5624, raises InternalServerError
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: D-06 chokepoint guard — yaml api_base assertion + direct-provider-import guard (GW-02)</name>
  <read_first>
    - config/model_gateway.config.yaml (model_list per-route api_base 24/34/45/54; router_settings.fallbacks 61-67; success_callback 75; master_key 81; general_settings.max_budget 84)
    - src/agent_mesh/worker/model_gateway.py (build_router + get_chat_model + RouterChatLiteLLM — built in 03-01)
    - .planning/phases/03-model-gateway-observability/03-RESEARCH.md (Finding 6; Pitfall 3; Pitfall 6; Security Domain "Budget bypass via direct provider call")
    - .planning/phases/03-model-gateway-observability/03-PATTERNS.md (No Analog Found: AST/grep direct-provider-import guard; yaml config-assertion test)
  </read_first>
  <action>
    Create `tests/test_d06_chokepoint.py`. Config-assertion test: `yaml.safe_load` the
    `config/model_gateway.config.yaml`, iterate `model_list`, and with `CF_ENABLED=true` +
    `CF_AIG_WRAPPER_URL` set, assert every route's `litellm_params.api_base` resolves to the CF wrapper URL
    (resolve the `os.environ/CF_AIG_WRAPPER_URL` reference shape). Structural guard test: walk `src/agent_mesh`
    with `ast` (or a grep over `.py` files filtered to non-comment lines via `grep -v '^[[:space:]]*#'`) and
    assert NO module imports/constructs `ChatAnthropic`, `ChatVertexAI`, or calls `litellm.completion(`
    directly — only `get_chat_model()` / `build_router()` may reach providers. Treat the Router as "the
    client" (RESEARCH Finding 6). Inert-config test: assert `general_settings.max_budget` and `master_key`
    are PRESENT and well-formed in the yaml (prod-proxy config, D-09) AND assert they are never read by the
    in-process runtime path (e.g. `get_chat_model`/`build_router` do not reference `max_budget`/`master_key`)
    — the durable ledger is the enforcer (Pitfall 6).
  </action>
  <verify>
    <automated>CF_ENABLED=true CF_AIG_WRAPPER_URL=https://gw.example/v1 pytest tests/test_d06_chokepoint.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - With CF_ENABLED, every `model_list[*].litellm_params.api_base` asserts to the CF wrapper URL
    - The guard fails (test would fail) if `ChatAnthropic`/`ChatVertexAI`/`litellm.completion(` appears anywhere under src/agent_mesh outside the gateway — non-comment lines only (filtered grep, no bare ==0 on raw file)
    - `max_budget` + `master_key` asserted present in yaml but proven not consumed by the in-process runtime
    - Test passes against the 03-01 src; runs in the default suite with no creds
  </acceptance_criteria>
  <done>D-06 is enforced structurally: CF api_base per-route + no direct-provider construction + inert prod-proxy fields.</done>
</task>

<task type="auto">
  <name>Task 2: GW-03 stub-lane cascade — mock_testing_fallbacks fallback wiring (default suite)</name>
  <read_first>
    - config/model_gateway.config.yaml (router_settings.fallbacks 61-67 — the cascade map)
    - src/agent_mesh/worker/model_gateway.py (build_router — built in 03-01)
    - .planning/phases/03-model-gateway-observability/03-RESEARCH.md (Finding 4; Don't Hand-Roll "Forcing a fallback in tests")
    - .planning/phases/03-model-gateway-observability/03-PATTERNS.md (No Analog Found: mock_testing_fallbacks stub-lane cascade test)
  </read_first>
  <action>
    Create `tests/test_cascade.py` (default lane, no creds). Build the Router via `build_router()`, call
    `router.completion(model=<primary deployment name>, messages=[...], mock_testing_fallbacks=True)` and
    assert the call SUCCEEDS by being served from the configured FALLBACK deployment (not the primary) —
    proving `router_settings.fallbacks` was loaded and honored in-process (D-09). Inspect the returned
    ModelResponse / Router result to assert the fallback deployment served (e.g. the response model field or
    Router-recorded deployment differs from the primary). This proves the cascade WIRING with zero provider
    calls. Do NOT monkeypatch Router internals — use the verified `mock_testing_fallbacks` hook only.
  </action>
  <verify>
    <automated>pytest tests/test_cascade.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `router.completion(..., mock_testing_fallbacks=True)` raises InternalServerError on the primary and the Router cascades to the configured fallback deployment
    - The test asserts the FALLBACK deployment served (not the primary)
    - No provider creds required; runs in `make test`; no Router-internal monkeypatching
  </acceptance_criteria>
  <done>GW-03 fallback wiring is proven deterministically in the green default suite.</done>
</task>

<task type="auto">
  <name>Task 3: GW-03 live-lane — real Vertex→Anthropic fallback + cents-cap clean halt (pytest -m live)</name>
  <read_first>
    - src/agent_mesh/worker/budget.py (BudgetTracker.check/record — built in 03-01)
    - src/agent_mesh/services/repository.py (list_gateway_events / record_gateway_event — built in 03-01)
    - config/model_gateway.config.yaml (router_settings.fallbacks; model_list deployment names)
    - .planning/phases/03-model-gateway-observability/03-RESEARCH.md (Finding 2 clean-halt proof; Finding 4 live-lane inducer + Assumption A2; Open Question 2; D-02/D-03)
    - tests/conftest.py (live-marker skip fixture from 03-01)
  </read_first>
  <action>
    Create `tests/test_cascade_live.py`, every test decorated `@pytest.mark.live` and gated on the live-creds
    skip fixture (skip when ANTHROPIC_API_KEY / Vertex creds unset — D-02). Fallback test (D-03): configure a
    dedicated live-lane test route pairing a deterministically-broken Vertex primary with a real Anthropic
    fallback (LIVE-LANE RUNTIME DECISION — pick ONE inducer at execution time and document it in the SUMMARY:
    nonexistent vertex model id, OR invalid vertex_location, OR empty vertex_project; per RESEARCH A2 confirm
    it triggers the GENERAL fallbacks list, not a hard 4xx — if it hard-fails, switch to a 5xx-class inducer).
    Assert the real Anthropic deployment served (real Router → real Vertex failure → real Anthropic — NOT a
    faked boundary, D-01). Halt test: set `MODEL_MONTHLY_BUDGET_USD=0.02`; the first call's pre-call estimate
    exceeds the cap → `BudgetExceeded` → assert the run reaches a terminal halted state, a `gateway_event` is
    recorded via `list_gateway_events(task_id, tenant_id)` (note=budget_halt, provider_status=None), and NO
    provider call was made beyond the cap. Keep the exact Langfuse OTLP endpoint and Vertex inducer as
    live-lane runtime decisions — do NOT hardcode A1/A2 guesses into the default suite.
  </action>
  <verify>
    <automated>pytest tests/test_cascade_live.py -m live -q || echo "SKIPPED-WITHOUT-CREDS (expected in default CI)"</automated>
  </verify>
  <acceptance_criteria>
    - All tests carry `@pytest.mark.live` and SKIP cleanly when provider creds are unset (default CI green)
    - With creds: a real Vertex failure cascades to a REAL Anthropic response (D-01/D-03)
    - With creds + cents cap: pre-call estimate > cap → `BudgetExceeded` → clean halt + a `gateway_event` recorded; no spend beyond the cap
    - The chosen Vertex-failure inducer is documented in the SUMMARY (live-lane runtime decision, not hardcoded into the default suite)
  </acceptance_criteria>
  <done>GW-03 is proven against real providers in the opt-in live lane without faking the boundary; default CI skips cleanly.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| worker → CF edge → provider | when CF_ENABLED, all model traffic must traverse the CF wrapper api_base |
| any src module → provider SDK | only get_chat_model()/build_router() may reach a provider |
| live-lane creds → real providers | opt-in only; default suite must never require them |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-03-02-01 | Tampering / cost abuse | direct provider call bypassing CF + budget | mitigate | Task 1 AST/grep guard fails on any direct ChatAnthropic/ChatVertexAI/litellm.completion outside the gateway |
| T-03-02-02 | Spoofing / governance bypass | route api_base not pointing at CF when enabled | mitigate | Task 1 config assertion: every model_list api_base == CF wrapper when CF_ENABLED |
| T-03-02-03 | Information Disclosure | live-lane provider keys leaking into CI logs | mitigate | live tests skip when creds unset; cents cap bounds spend; keys from env only, never asserted/logged |
| T-03-02-04 | Denial of Service / cost | budget halt fails to stop a near-cap run | mitigate | Task 3 asserts BudgetExceeded clean halt + gateway_event + no spend beyond cap (durable ledger from 03-01) |
| T-03-02-05 | Tampering | forged/replayed gateway_event | accept | gateway_events are append-only durable rows; halt is run-control, not an approval (no SEC weakening) |
</threat_model>

<verification>
- `make test` GREEN with NO cloud deps: `test_d06_chokepoint.py` + `test_cascade.py` pass; `test_cascade_live.py` SKIPS.
- `pytest tests/test_d06_chokepoint.py tests/test_cascade.py -x -q` passes against the 03-01 src.
- `make test-live` runs the live cascade + halt with user creds (opt-in); default suite never requires `-m live`.
- The direct-provider-import guard would fail if a future change reaches a provider outside the gateway.
</verification>

<success_criteria>
GW-02 and GW-03 are locally provable: structural CF-never-bypass enforcement, deterministic stub-lane
fallback, real-provider live-lane fallback, and a clean cents-cap budget halt — default suite green, live lane opt-in.
</success_criteria>

<output>
Create `.planning/phases/03-model-gateway-observability/03-02-SUMMARY.md` when done.
</output>
