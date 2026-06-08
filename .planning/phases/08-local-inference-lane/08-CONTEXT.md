# Phase 8: Local Inference Lane - Context

**Gathered:** 2026-06-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Add local-model profiles so the agent mesh runs inference fully on-box behind the
**existing** LiteLLM Router — **vLLM** (GPU) and **Ollama** (CPU/dev) — without touching
agent or gateway code. Deliverables: `config/model_gateway.vllm.yaml` +
`config/model_gateway.ollama.yaml` profiles (3 tiers each), `make` run/swap targets, a
RUNBOOK "Local inference lane" section, and a config-validation test that builds each
profile via `build_router` with no network call. Requirements: **LOCAL-01..04**.

**Hard guardrail (whole milestone):** config / Makefile / docs / tests **ONLY**. **Zero
`src/` production code change.** Deployment names (`low/medium/high-complexity`) stay
constant so the LiteLLM Router seam + agent code are untouched. Offline enforcement
(Phase 11) is test-asserted over config, never a runtime `src/` guard.

</domain>

<decisions>
## Implementation Decisions

### A — Profile selection mechanism (LOCAL-03)
- **D-01 (file-swap, make-managed):** `build_router` loads a **hardcoded**
  `DEFAULT_CONFIG_PATH = "config/model_gateway.config.yaml"` (`model_gateway.py:35`,
  consumed at `:87`/`:167`). There is **no env-driven config-path seam, and adding one is a
  forbidden `src/` change.** Therefore runtime profile selection = **file swap**: `make`
  targets copy the chosen profile onto `config/model_gateway.config.yaml`. Selection is
  make-managed and **reversible**.
- **D-02 (restore path):** Preserve the current cloud default as a pristine
  `config/model_gateway.cloud.yaml` (copy of today's `config/model_gateway.config.yaml`).
  Targets: `make use-vllm` / `make use-ollama` (swap in the local profile) and
  `make use-cloud` (restore the cloud profile). RUNBOOK documents the swap **honestly** —
  including that an active local profile leaves `config/model_gateway.config.yaml` showing
  as modified in git (inherent, documented, reversible via `use-cloud`).
- **D-03 (test independence):** LOCAL-04's validation test calls
  `build_router("config/model_gateway.vllm.yaml")` / `.ollama.yaml` **directly on the
  profile files** — it does NOT depend on the swap. No new seam needed; the existing
  `config_path` arg is the test entry point.

### B — Local model topology (LOCAL-01/02)
- **D-04 (one shared model, 3 nominal tiers):** On one local box, all three deployment
  names (`low-complexity`, `medium-complexity`, `high-complexity`) route to the **same**
  local served model. Tiering is **nominal locally** — realistic for a single GPU/CPU box,
  keeps fallbacks resolvable, and the LOCAL-04 test only asserts the 3 names exist with a
  local `api_base`. (Distinct-model-per-tier deferred — see Deferred Ideas.)
- **D-05 (tool-call-capable instruct models):** The shared model MUST be a tool-calling-
  capable **instruct** model, because the mesh delegates via tool-calls — tool-calling
  quality (not transport) is the real local constraint. Candidate defaults to record/pin in
  research: **Qwen2.5-Instruct** (default) with **Llama-3.1-Instruct** as the documented
  alternative. Researcher pins exact model id strings + the matching vLLM tool-call-parser.

### C — Local fallback chain shape (LOCAL-01/02/04)
- **D-06 (self-contained 3-deployment chain):** Local profiles **drop** the cloud config's
  4th route `high-complexity-vertex`. `router_settings.fallbacks` stays **within the three
  local deployment names** (e.g. `low-complexity → [medium-complexity]`,
  `medium-complexity → [high-complexity]`, `high-complexity → [medium-complexity]`; exact
  edges finalised in-plan). Rationale: keeps the profile self-consistent and leaves **no
  cloud-named routes** for the Phase 11 no-egress assertion to trip over.

### D — make-target ambition + tool-calling caveat (LOCAL-01/02/03)
- **D-07 (real best-effort run targets):** `make run-vllm` / `make run-ollama` **actually
  run** the backend — `vllm serve …` and `ollama pull <model> && ollama serve` (or
  equivalent) — **best-effort and local-only (never wired into CI / `make test`)**; they may
  fail on a box without a GPU / without Ollama, which is acceptable and documented.
- **D-08 (baked tool-parser flags):** `make run-vllm` bakes the **recommended tool-call-
  parser flags** into the serve command (e.g. `--enable-auto-tool-choice --tool-call-parser
  <parser>`; exact parser name pinned by research to match the chosen model). The
  weak-local-tool-calling **caveat + recommended flags also live in RUNBOOK** (LOCAL-03), so
  the guidance survives even when a user runs the backend by hand.

### Cross-cutting (carried forward from Phases 1–7)
- **D-09 (creds-free + no-network default lane):** The LOCAL-04 config-validation test runs
  in the **default lane** — creds-free, **no network call** — matching the established
  Phases 1–6 pattern (real backends exercised only in opt-in / loud-skip lanes; `make
  run-vllm/run-ollama` are the operator-run real path, never CI). Local `api_base` values
  are loopback (`http://localhost:<port>/…`), so `build_router` constructs the Router
  without egress.

### Claude's Discretion
- Exact fallback edges within the 3 local deployment names (D-06 shape is fixed; edges are
  the planner's to finalise).
- Exact local `api_base` ports/paths (vLLM OpenAI server vs Ollama endpoint) — pin in
  research/plan.
- Whether `make use-cloud` restores via `cp config/model_gateway.cloud.yaml …` or
  `git checkout` — planner picks the cleaner reversible mechanism (D-02 intent is fixed).
- LiteLLM route prefixes (`hosted_vllm/<model>` for vLLM; `ollama/<model>` vs
  `ollama_chat/<model>` for Ollama) — researcher confirms the tool-calling-correct prefix.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Model gateway seam (the thing local profiles plug into — DO NOT modify `src/`)
- `src/agent_mesh/worker/model_gateway.py` — `build_router(config_path=DEFAULT_CONFIG_PATH)`
  (`:87`) loads `model_list` + `router_settings.fallbacks/num_retries/timeout`;
  `DEFAULT_CONFIG_PATH` (`:35`); `_get_cached_router` (`:167`); `TIER_TO_DEPLOYMENT` (`:62`,
  underscore tier → hyphenated `model_name`, resolved by **exact** `model_name`); D-06
  per-route `api_base` relocation note (`:180`–`197`). **Frozen — reference only.**
- `config/model_gateway.config.yaml` — the **cloud default profile to mirror**: `model_list`
  entry shape (`model_name` + `litellm_params.model` + per-route `api_base` + `extra_headers`),
  `router_settings.fallbacks` (currently references the 4th `high-complexity-vertex`),
  `litellm_settings`, `general_settings`. Local profiles mirror this structure with local
  routes.

### Requirements & milestone scope
- `.planning/REQUIREMENTS.md` § "Local Inference (Phase 8)" — LOCAL-01/02/03/04 (the
  checkable acceptance items).
- `.planning/ROADMAP.md` § "Phase 8: Local Inference Lane" + the v1.1 milestone guardrail
  block (config/compose/docs/tests ONLY; deployment names unchanged).

### Targets to extend (mirror existing style)
- `Makefile` — existing `test` (`:32`), `test-live` (`:35`), `test-pg` (`:42`), `smoke`
  (`:53`), `run-api/run-worker/run-gui` (`:56`–`62`) targets. New run/swap targets mirror
  these conventions.
- `RUNBOOK.md` — add the "Local inference lane" section (LOCAL-03). (Prior investigation S896
  already sketched a `make run-vllm` + config-swap RUNBOOK section — reconcile with it.)
- `manifests/deployment.manifest.yaml` — `model_routes` reference (deployment-name source of
  truth; do not break name parity).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `build_router(config_path)` already takes a path arg → **LOCAL-04 test entry point** with
  zero new seam: `build_router("config/model_gateway.vllm.yaml")` builds a Router straight
  from the profile file.
- `TIER_TO_DEPLOYMENT` (low_complexity→`low-complexity`, …) is the single source of truth for
  the names the Router resolves by. Profiles MUST use `model_name: low-complexity /
  medium-complexity / high-complexity` exactly, or `Router.completion(model=…)` 404s
  ("deployment not found") — the stubbed-Router test cannot catch this.

### Established Patterns
- **D-06 api_base relocation:** `api_base` lives **per-route** in
  `model_list[*].litellm_params.api_base`, never on the chat model. Local profiles set each
  route's `api_base` to a loopback URL (vLLM OpenAI server / Ollama endpoint).
- **Default lane = creds-free + no-network + loud-skip; real = opt-in operator lane.** LOCAL-04
  belongs in the default lane (constructs Router, asserts structure, no egress). `make
  run-vllm/run-ollama` are the real opt-in path, never CI.
- LiteLLM provider-prefix routing: `hosted_vllm/<model>` (vLLM OpenAI-compatible), Ollama via
  its LiteLLM provider prefix — both with a local `api_base`. Zero provider code: only yaml
  `litellm_params` change (confirmed by S896 investigation — the swap is a zero-code-change op).

### Integration Points
- Phase 10 (compose) consumes these profiles + run targets to stand up a local model backend
  service. Phase 11 (no-egress) asserts these local profiles contain **no cloud `api_base`**
  (no Vertex/Anthropic/CF wrapper URL) and no cloud-key env refs — D-06's self-contained
  3-deployment chain keeps that assertion clean.

</code_context>

<specifics>
## Specific Ideas

- Prior investigation **S896** (claude-mem) already mapped: vLLM swap is a zero-code-change op
  (yaml `model_list` edit only); LiteLLM speaks vLLM via `hosted_vllm/<model>` + `api_base`;
  tool-calling quality (model choice + vLLM tool-call parser) is the real constraint, not
  transport; budget telemetry goes inert locally (free tokens). The planner/researcher should
  reconcile with S896 rather than re-derive it.
- Naming: local profiles `config/model_gateway.vllm.yaml` and
  `config/model_gateway.ollama.yaml`; pristine cloud copy `config/model_gateway.cloud.yaml`.

</specifics>

<deferred>
## Deferred Ideas

- **Distinct-model-per-tier topology** (low/medium/high each a different local model) — heavier
  VRAM/footprint; revisit if local tiering ever needs to be real. (D-04 chose one shared model
  for this phase.)
- An **env-driven config-path seam** (`build_router` honouring a `MODEL_GATEWAY_CONFIG_PATH`
  env) would make selection cleaner than file-swap, but it is a `src/` change — **out of scope
  for this milestone's zero-src-change guardrail.** Candidate for a future hardening milestone.

None of the above is in Phase 8 scope.

</deferred>

---

*Phase: 08-local-inference-lane*
*Context gathered: 2026-06-08*
</content>
</invoke>
