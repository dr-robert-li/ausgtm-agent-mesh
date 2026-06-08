# Phase 8: Local Inference Lane - Research

**Researched:** 2026-06-08
**Domain:** Local LLM serving (vLLM / Ollama) behind a LiteLLM Router; YAML profile authoring; Makefile + RUNBOOK + config-validation test (zero `src/` change)
**Confidence:** HIGH (the two correctness traps — `hosted_vllm` `/v1` path and offline `build_router` — are settled against installed litellm 1.83.7 source + an empirical probe, not training data)

## Summary

Phase 8 is a **config + Makefile + docs + test** phase. The model-gateway seam (`src/agent_mesh/worker/model_gateway.py`) is frozen and already does everything required: `build_router(config_path)` loads a `model_list` + `router_settings.fallbacks` from any YAML path and constructs an in-process `litellm.Router` **without any network call** (empirically verified this session). So the entire phase is: author two mirror-of-cloud YAML profiles that point all three existing deployment names at a loopback local backend, add best-effort `make` run/swap targets, write a RUNBOOK section, and add one config-validation test that mirrors `tests/test_d06_chokepoint.py` but inverts its api_base assertion (loopback, not the CF env-indirection).

The real constraint is **not transport** (LiteLLM speaks both backends with a one-line `litellm_params.model` prefix change) — it is **tool-calling correctness**, which has two independent failure surfaces: (1) the served model must be a tool-call-capable *instruct* model with the matching **vLLM `--tool-call-parser`**, and (2) the LiteLLM `api_base` must hit the right path. The second is a runtime-only trap the LOCAL-04 test **cannot** catch (offline build succeeds with any api_base string), so its correctness lives entirely in the config value + RUNBOOK.

**Primary recommendation:** Mirror `config/model_gateway.config.yaml` into `config/model_gateway.vllm.yaml` and `config/model_gateway.ollama.yaml`, keeping `model_name: low-complexity / medium-complexity / high-complexity` **exactly**; set each route's `litellm_params.model` to `hosted_vllm/Qwen/Qwen2.5-7B-Instruct` (vLLM) / `ollama_chat/qwen2.5:7b-instruct` (Ollama); set `api_base` to the literal loopback `http://localhost:8000/v1` (vLLM — **`/v1` REQUIRED**) / `http://localhost:11434` (Ollama — **no `/v1`**); drop the cloud `high-complexity-vertex` route and keep fallbacks within the three local names. Mirror `tests/test_d06_chokepoint.py` for LOCAL-04.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Profile selection (which YAML is active) | Build/Make tooling (file-swap) | — | D-01: no env-driven config-path seam exists in `src/`; adding one is forbidden. Selection = `make` copying a profile onto `config/model_gateway.config.yaml`. |
| Route resolution (deployment-name → model) | Gateway seam (`src/`, FROZEN) | — | `TIER_TO_DEPLOYMENT` + Router resolve by exact `model_name`. Phase contributes config only. |
| Local inference serving | Local backend process (vLLM/Ollama) | — | `make run-vllm` / `make run-ollama` start it; best-effort, operator-run, never CI. |
| Tool-calling correctness | Model + vLLM `--tool-call-parser` (vLLM); model capability (Ollama) | RUNBOOK caveat | Real local constraint. Parser is model-specific. |
| Egress confinement | Config (loopback `api_base`) | Phase 11 test | Loopback URLs mean `build_router` constructs with no egress; Phase 11 asserts no cloud api_base. |

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01 (file-swap, make-managed):** `build_router` loads a hardcoded `DEFAULT_CONFIG_PATH = "config/model_gateway.config.yaml"`. There is **no env-driven config-path seam, and adding one is a forbidden `src/` change.** Runtime profile selection = file swap: `make` targets copy the chosen profile onto `config/model_gateway.config.yaml`. Make-managed and reversible.
- **D-02 (restore path):** Preserve the current cloud default as a pristine `config/model_gateway.cloud.yaml` (copy of today's `config/model_gateway.config.yaml`). Targets: `make use-vllm` / `make use-ollama` (swap in local profile) and `make use-cloud` (restore cloud). RUNBOOK documents the swap **honestly** — an active local profile leaves `config/model_gateway.config.yaml` showing as modified in git (inherent, documented, reversible via `use-cloud`).
- **D-03 (test independence):** LOCAL-04's test calls `build_router("config/model_gateway.vllm.yaml")` / `.ollama.yaml` **directly on the profile files** — NOT via the swap. The existing `config_path` arg is the entry point; no new seam.
- **D-04 (one shared model, 3 nominal tiers):** All three deployment names route to the **same** local served model. Tiering is nominal locally. LOCAL-04 only asserts the 3 names exist with a local `api_base`.
- **D-05 (tool-call-capable instruct models):** Shared model MUST be a tool-calling-capable **instruct** model. Default: **Qwen2.5-Instruct**; documented alternative: **Llama-3.1-Instruct**. Research pins exact model-id strings + matching vLLM tool-call-parser.
- **D-06 (self-contained 3-deployment chain):** Local profiles **drop** the cloud `high-complexity-vertex` 4th route. `router_settings.fallbacks` stays **within the three local deployment names**. No cloud-named routes for the Phase 11 no-egress assertion to trip over.
- **D-07 (real best-effort run targets):** `make run-vllm` / `make run-ollama` **actually run** the backend (`vllm serve …` and `ollama pull <model> && ollama serve` / equivalent) — best-effort, local-only, **never wired into CI / `make test`**; may fail on a box without GPU / Ollama (acceptable, documented).
- **D-08 (baked tool-parser flags):** `make run-vllm` bakes the recommended tool-call-parser flags into the serve command. The weak-local-tool-calling **caveat + flags also live in RUNBOOK** (LOCAL-03).
- **D-09 (creds-free + no-network default lane):** LOCAL-04 runs in the default lane — creds-free, no network. Local `api_base` values are loopback, so `build_router` constructs without egress. `make run-vllm/run-ollama` are the operator-run real path, never CI.

### Claude's Discretion
- Exact fallback edges within the 3 local deployment names (D-06 shape fixed; edges to finalise). **Research recommendation below.**
- Exact local `api_base` ports/paths. **Research pins below.**
- Whether `make use-cloud` restores via `cp config/model_gateway.cloud.yaml …` or `git checkout`. **Research recommendation: `cp` (see Pitfall 5).**
- LiteLLM route prefixes (`hosted_vllm/` for vLLM; `ollama/` vs `ollama_chat/` for Ollama). **Research pins below: `hosted_vllm/` and `ollama_chat/`.**

### Deferred Ideas (OUT OF SCOPE)
- **Distinct-model-per-tier topology** — heavier VRAM; D-04 chose one shared model.
- **Env-driven config-path seam** (`MODEL_GATEWAY_CONFIG_PATH`) — a `src/` change, out of scope for the zero-src-change guardrail.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LOCAL-01 | `config/model_gateway.vllm.yaml` routes all three tiers to a local vLLM OpenAI-compatible endpoint behind LiteLLM (`hosted_vllm/*` + local `api_base`); `make run-vllm` starts the server | Pinned model id + `api_base http://localhost:8000/v1` (**`/v1` REQUIRED**, Pitfall 1); `vllm serve` command with parser flags (D-08, Code Examples). |
| LOCAL-02 | `config/model_gateway.ollama.yaml` routes all three tiers to a local Ollama endpoint behind LiteLLM; `make run-ollama` starts/pulls it | Pinned `ollama_chat/<tag>` prefix (tool-calling-correct, Pitfall 2) + `api_base http://localhost:11434` (no `/v1`); `ollama pull && ollama serve` command. |
| LOCAL-03 | RUNBOOK "Local inference lane" section: how to run each backend, how the Router selects a profile (config path / env), and the tool-calling model-capability caveat | RUNBOOK section spec below (Architecture Patterns), placed after "Local Smoke Checks" (RUNBOOK.md:41). Honest swap/git-dirty disclosure + parser caveat. |
| LOCAL-04 | A config-validation test asserts each local profile defines all three deployment names with a local `api_base` and builds via `build_router` with no network | Mirror `tests/test_d06_chokepoint.py`; invert api_base assertion to loopback. `build_router` offline construction **[VERIFIED]** this session (Pitfall 6 / Code Examples). |
</phase_requirements>

---

## Standard Stack

### Core
| Library / Tool | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| LiteLLM (`litellm.Router`) | **1.83.7** (installed in `.venv`) `[VERIFIED: importlib.metadata]` | Provider abstraction + in-process cascade routing. The seam already uses it. | Already the project's model control plane; speaks both vLLM (`hosted_vllm/`) and Ollama (`ollama_chat/`) with a prefix change. |
| vLLM | **≥ 0.6.0** assumed floor (hermes/llama3_json parsers + `--enable-auto-tool-choice` stable since the 0.6 line) `[ASSUMED]` `[CITED: docs.vllm.ai/.../tool_calling]` | GPU local OpenAI-compatible server. | D-07 GPU lane. Native OpenAI `/v1/chat/completions` + tool-call parsing. |
| Ollama | recent (any version with `/api/chat` tool-calling; Llama-3.1/Qwen2.5 supported) `[CITED: litellm ollama docs]` | CPU/dev local backend, native `/api/chat`. | D-07 CPU/dev lane. LiteLLM `ollama_chat/` targets `/api/chat`. |

### Pinned model ids (D-05 — copy-pasteable)

| Backend | `litellm_params.model` | vLLM `--model` HF id / Ollama tag | Notes |
|---------|------------------------|------------------------------------|-------|
| vLLM (default) | `hosted_vllm/Qwen/Qwen2.5-7B-Instruct` | `Qwen/Qwen2.5-7B-Instruct` | **Text** instruct model — NOT the `-VL-` vision variant that appears in search results. `[CITED: huggingface.co/Qwen/Qwen2.5-7B-Instruct]` |
| Ollama (default) | `ollama_chat/qwen2.5:7b-instruct` | `qwen2.5:7b-instruct` | Ollama library tag for the same family. `[CITED: ollama.com/library/qwen2.5]` `[ASSUMED exact tag string — verify with `ollama pull qwen2.5:7b-instruct`]` |
| vLLM (documented alt) | `hosted_vllm/meta-llama/Llama-3.1-8B-Instruct` | `meta-llama/Llama-3.1-8B-Instruct` | Gated HF repo (license acceptance). Parser differs — see D-08. `[CITED: docs.vllm.ai tool_calling]` |
| Ollama (documented alt) | `ollama_chat/llama3.1:8b-instruct` | `llama3.1:8b-instruct` | `[ASSUMED exact tag — verify with `ollama pull`]` |

**VRAM / footprint realism (single local box):** a 7B/8B instruct model at fp16 ≈ **14–16 GB VRAM** (weights ~15 GB + KV cache), so it needs a ≥16 GB GPU (24 GB comfortable). Quantized (AWQ/GPTQ/Q4) ≈ 5–6 GB and runs on smaller GPUs — but **quantization can degrade tool-calling reliability**, so for the default-quality vLLM lane, document fp16 on a 16–24 GB GPU. Ollama (CPU/dev) defaults to a quantized GGUF (`qwen2.5:7b-instruct` ≈ ~4.7 GB) and runs on CPU/RAM — slow but no GPU required, which is the point of the dev lane. `[ASSUMED — footprint figures are standard-knowledge estimates; flag A2]`

### vLLM tool-call-parser pins (D-08 — exact flags)

| Model | `--tool-call-parser` | Required companion flags | Source |
|-------|----------------------|--------------------------|--------|
| **Qwen2.5-Instruct** (default) | `hermes` | `--enable-auto-tool-choice` | Qwen2.5's `tokenizer_config.json` chat template already includes Hermes-style tool use; no custom chat-template file needed. `[CITED: qwen.readthedocs.io/.../function_call; docs.vllm.ai/.../tool_calling]` |
| **Llama-3.1-Instruct** (alt) | `llama3_json` | `--enable-auto-tool-choice` (+ vLLM ships a `tool_chat_template_llama3.1_json.jinja`; pass `--chat-template <that file>` if your vLLM build does not auto-select it) | `[CITED: docs.vllm.ai/.../tool_calling]` |

> **Do NOT carry `hermes` to the Llama alternative.** The parser is model-family-specific (`hermes` for Qwen2.5, `llama3_json` for Llama-3.1). Mismatched parser → empty/garbled `tool_calls`.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `hosted_vllm/` for vLLM | generic `openai/` (OpenAI-compatible) prefix | `hosted_vllm/` is the LiteLLM-blessed prefix for vLLM and adds vLLM-specific param handling (`reasoning_effort`, `thinking`). Use `hosted_vllm/`. |
| `ollama_chat/` for Ollama | `ollama/` (generate endpoint) | `ollama/` hits `/api/generate` (completion); tool-calling examples in LiteLLM docs use **only** `ollama_chat/` (`/api/chat`). Use `ollama_chat/` — see Pitfall 2. |
| Qwen2.5-7B | Llama-3.1-8B | Llama repo is HF-gated (license click-through); different parser. Qwen2.5 is ungated + Hermes template baked in → lower-friction default. |

**Installation:** No new Python packages for the phase (config/Make/docs/test only). vLLM/Ollama are operator-installed local tooling, never project deps:
```bash
# Operator box only — NOT a project dependency, NOT in requirements/*.txt
pip install vllm            # GPU box
# Ollama: install via https://ollama.com/download (brew install ollama on macOS)
```

**Version verification performed this session:**
```text
litellm 1.83.7   [VERIFIED: .venv/bin/python -m importlib.metadata]
```

## Package Legitimacy Audit

> No external **Python** packages are installed by this phase (config/Makefile/docs/tests only — D-09 guardrail). vLLM and Ollama are operator-installed local runtimes invoked by best-effort `make` targets, never added to `requirements/*.txt` or `pyproject.toml`. slopcheck not run — **no install surface to audit**.

| Package | Registry | Disposition |
|---------|----------|-------------|
| (none — phase adds no Python deps) | — | N/A |

**Operator-side runtimes (informational, not project deps):** `vllm` (PyPI, vllm-project, millions of downloads, github.com/vllm-project/vllm), `ollama` (standalone binary, github.com/ollama/ollama). Both are well-established, high-trust projects; they are invoked by `make run-*`, never imported or pinned by the mesh. `[CITED: pypi.org/project/vllm, github.com/ollama/ollama]`

## Architecture Patterns

### System Architecture Diagram

```
                       LOCAL-04 test (default lane, no network)
                                  │ build_router("config/model_gateway.vllm.yaml")
                                  ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │   model_gateway.py  (FROZEN — reference only, zero src/ change)    │
  │   build_router(path) → litellm.Router(model_list, fallbacks…)     │
  │   TIER_TO_DEPLOYMENT: low_complexity → "low-complexity" (exact)    │
  └──────────────────────────────────────────────────────────────────┘
            ▲ loads model_list + router_settings.fallbacks
            │
  ┌─────────┴──────────┐   make use-vllm / use-ollama (cp)   ┌───────────────────────┐
  │ config/model_      │ ◀───────── file swap ───────────────│ config/model_gateway. │
  │ gateway.config.yaml│   make use-cloud restores            │ {vllm,ollama,cloud}.  │
  │  (ACTIVE profile)  │                                      │ yaml  (the profiles)  │
  └─────────┬──────────┘                                      └───────────────────────┘
            │ per-route litellm_params.model + api_base (loopback, literal)
            ▼
  ┌──────────────────────────────┐        ┌───────────────────────────────┐
  │ hosted_vllm/Qwen2.5-7B-Instr.│        │ ollama_chat/qwen2.5:7b-instruct│
  │ api_base http://localhost:   │        │ api_base http://localhost:11434│
  │            8000/v1  ← /v1 !! │        │            (NO /v1)            │
  └──────────────┬───────────────┘        └───────────────┬───────────────┘
   make run-vllm │ (best-effort, operator)  make run-ollama│ (best-effort, operator)
                 ▼                                          ▼
  ┌──────────────────────────────┐        ┌───────────────────────────────┐
  │ vLLM OpenAI server :8000      │        │ Ollama :11434  /api/chat      │
  │ --enable-auto-tool-choice     │        │ (native tool-calling per      │
  │ --tool-call-parser hermes     │        │  model capability)            │
  └──────────────────────────────┘        └───────────────────────────────┘
```

### Component Responsibilities

| File | Responsibility | New / Existing |
|------|----------------|----------------|
| `config/model_gateway.vllm.yaml` | 3-tier vLLM local profile (LOCAL-01) | NEW |
| `config/model_gateway.ollama.yaml` | 3-tier Ollama local profile (LOCAL-02) | NEW |
| `config/model_gateway.cloud.yaml` | Pristine copy of today's cloud config; restore source (D-02) | NEW (copy) |
| `Makefile` | `run-vllm`, `run-ollama`, `use-vllm`, `use-ollama`, `use-cloud` targets | EXTEND |
| `RUNBOOK.md` | "Local inference lane" section (LOCAL-03), after line 41 | EXTEND |
| `tests/test_local_profiles.py` (suggested name) | LOCAL-04 config-validation test, mirrors `test_d06_chokepoint.py` | NEW |
| `config/model_gateway.config.yaml` | Active profile target of the swap (gets overwritten; reversible) | TOUCHED at runtime by `make use-*`, not edited in-repo |
| `src/agent_mesh/worker/model_gateway.py` | **FROZEN** — do not touch | UNCHANGED |

### Pattern 1: Mirror the cloud profile, swap two fields per route
**What:** Each local profile is structurally identical to `config/model_gateway.config.yaml` — same `model_name` values (exact), same `router_settings`/`litellm_settings`/`general_settings` shape — but with per-route `litellm_params.model` and `api_base` pointed locally, and the `high-complexity-vertex` route + its fallback reference dropped (D-06).
**When to use:** Both LOCAL-01 and LOCAL-02.
**Example (vLLM profile, abbreviated):**
```yaml
# config/model_gateway.vllm.yaml  — local vLLM lane (LOCAL-01)
model_list:
  - model_name: low-complexity          # EXACT — TIER_TO_DEPLOYMENT resolves by this
    litellm_params:
      model: hosted_vllm/Qwen/Qwen2.5-7B-Instruct
      api_base: http://localhost:8000/v1   # /v1 REQUIRED for hosted_vllm (Pitfall 1)
  - model_name: medium-complexity
    litellm_params:
      model: hosted_vllm/Qwen/Qwen2.5-7B-Instruct
      api_base: http://localhost:8000/v1
  - model_name: high-complexity
    litellm_params:
      model: hosted_vllm/Qwen/Qwen2.5-7B-Instruct
      api_base: http://localhost:8000/v1
router_settings:
  fallbacks:
    - low-complexity: ["medium-complexity"]
    - medium-complexity: ["high-complexity"]
    - high-complexity: ["medium-complexity"]   # self-contained loop; NO cloud route
  num_retries: 2
  timeout: 120
litellm_settings:
  drop_params: true
  max_tokens: 4096
  # success_callback/failure_callback: keep Langfuse/otel telemetry inert-but-harmless
  # locally (token cost ≈ 0 for local models). Mirror cloud or trim — planner's call;
  # NOT load-bearing for LOCAL-04.
general_settings:
  master_key: os.environ/MODEL_GATEWAY_MASTER_KEY   # inert prod-proxy field (D-09)
  max_budget: 50
  budget_duration: 30d
```
> **Ollama profile** is identical structure with `model: ollama_chat/qwen2.5:7b-instruct` and `api_base: http://localhost:11434` (no `/v1`).

### Pattern 2: Recommended local fallback edges (D-06)
**What:** A self-contained chain within the three local names only.
**Recommended edges (Claude's Discretion, finalised here):**
```yaml
- low-complexity:    ["medium-complexity"]
- medium-complexity: ["high-complexity"]
- high-complexity:   ["medium-complexity"]
```
**Why these:** `low → medium → high` mirrors the cloud escalation direction; `high → medium` closes the loop (no dangling cloud `high-complexity-vertex`) and avoids `high → high` self-reference. Because D-04 routes all three names to the *same* served model, fallback is nominal (escalation has no model-quality effect locally) — the point is **leaving no cloud-named route** for Phase 11's OFFLINE-02 assertion and keeping every referenced name resolvable.

### Pattern 3: Make swap = `cp`, restore = `cp` from the pristine cloud copy
**What:** `use-vllm`/`use-ollama` copy a profile onto the active path; `use-cloud` copies the pristine `cloud.yaml` back.
**Why `cp` over `git checkout`:** `cp config/model_gateway.cloud.yaml config/model_gateway.config.yaml` is mechanism-agnostic (works on a dirty tree, in CI, in a tarball export) and never touches git state. `git checkout config/model_gateway.config.yaml` only works if the file is committed-clean and silently does the wrong thing if someone has *real* uncommitted edits. Use `cp` (see Pitfall 5).

### RUNBOOK "Local inference lane" section spec (LOCAL-03)
Place after `## Local Smoke Checks` (RUNBOOK.md:41). Must cover:
1. **How to run each backend** — `make run-vllm` (GPU; `vllm serve …` with the baked parser flags) and `make run-ollama` (CPU/dev; `ollama pull … && ollama serve`). State they are best-effort and may fail without GPU/Ollama (D-07).
2. **How the Router selects a profile** — file-swap via `make use-vllm` / `make use-ollama` / `make use-cloud` (D-01/D-02). **Honestly disclose** that an active local profile leaves `config/model_gateway.config.yaml` showing as modified in git, and that `make use-cloud` reverts it (D-02).
3. **Tool-calling model-capability caveat** (D-08) — local instruct models are weaker at tool-calling than frontier cloud models; vLLM **requires** `--enable-auto-tool-choice --tool-call-parser <hermes|llama3_json>` matched to the model, or `tool_calls` come back empty. Restate the recommended flags so they survive a hand-run backend.
4. **api_base path gotcha** — vLLM `api_base` ends in `/v1`; Ollama does **not** (Pitfall 1/2).

### Anti-Patterns to Avoid
- **Renaming deployment names locally** (e.g. `local-low`) — 404s the Router. Names are FROZEN.
- **Adding `MODEL_GATEWAY_CONFIG_PATH` env handling** — a `src/` change, explicitly deferred.
- **Wiring `run-vllm`/`run-ollama` into `make test` or CI** — D-07: these are operator-only.
- **Carrying the `hermes` parser to the Llama alternative** — parser is model-specific.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| vLLM tool-call extraction | A custom regex/parser over model output | vLLM's built-in `--tool-call-parser hermes` / `llama3_json` | vLLM owns chat-template + parser pairing; hand-rolling re-introduces the exact bugs the parser fixes. |
| OpenAI-path URL assembly | Manually building `/v1/chat/completions` strings | LiteLLM `hosted_vllm/` + `api_base` (just supply `/v1`) | LiteLLM's `get_complete_url` appends `chat/completions`; you only supply the base+`/v1`. |
| Profile selection seam | A new env-var config-path reader in `src/` | `make` file-swap (D-01) | Zero-src-change guardrail; the swap is reversible and CI-safe. |
| Offline-build assertion | Mocking the network / monkeypatching sockets | Just call `build_router(profile)` — it already constructs offline | Verified: construction makes no network call (Code Examples). |

**Key insight:** Every "hard" part of this phase is already solved by an existing tool — LiteLLM for transport, vLLM for parsing, the frozen seam for routing. The phase's only original work is **correct config values + honest docs + one mirror test**.

## Common Pitfalls

### Pitfall 1: vLLM `hosted_vllm` `api_base` MUST include `/v1` (the public LiteLLM doc is wrong)
**What goes wrong:** The official LiteLLM vLLM doc and search snippets show `api_base="http://localhost:8000"` (no `/v1`). Following them yields a **404** because the request lands on `http://localhost:8000/chat/completions`, but vLLM serves at `/v1/chat/completions`.
**Why it happens:** In installed **litellm 1.83.7**, `HostedVLLMChatConfig` extends `OpenAIGPTConfig`, whose `get_complete_url` (`litellm/llms/openai/chat/gpt_transformation.py:665`) only appends `chat/completions` — it does **not** insert `/v1`. `[VERIFIED: read installed source this session]`
**How to avoid:** Set `api_base: http://localhost:8000/v1` in `config/model_gateway.vllm.yaml`. With `/v1` present, the URL resolves to exactly `…/v1/chat/completions` (the `endpoint in api_base` check prevents double-append). Ollama uses its **native** API (`ollama_chat/` → `/api/chat`), so its `api_base` is `http://localhost:11434` with **no** `/v1`.
**Warning signs:** Operator sees `NotFoundError: 404` / `OpenAIException 404` when `make run-vllm` is up. LOCAL-04 will **pass regardless** (offline build) — this is config+RUNBOOK-only correctness, flagged to the planner.

### Pitfall 2: Ollama `ollama/` vs `ollama_chat/` — wrong prefix breaks tool-calling
**What goes wrong:** Using `ollama/<model>` routes to `/api/generate` (completion), where LiteLLM's tool-calling support is weaker; tool calls silently degrade.
**How to avoid:** Use `ollama_chat/<model>` (routes to `/api/chat`). LiteLLM's tool-calling examples use `ollama_chat/` exclusively. `[CITED: docs.litellm.ai/docs/providers/ollama]`
**Warning signs:** Model "answers in prose" instead of emitting `tool_calls`.

### Pitfall 3: Deployment-name drift 404s the Router and the test can't catch it
**What goes wrong:** Any `model_name` other than the exact `low-complexity`/`medium-complexity`/`high-complexity` makes `Router.completion(model="high-complexity")` 404 ("deployment not found") at call time. The stubbed-Router unit test accepts any kwargs and won't catch it.
**How to avoid:** LOCAL-04 must explicitly assert all three exact names exist in each profile's `model_list`. (Mirror `test_model_gateway_router.py:29-30`.)
**Warning signs:** Live routing 404 only; never a build-time error.

### Pitfall 4: Wrong / mismatched vLLM tool-call-parser → empty `tool_calls`
**What goes wrong:** `--tool-call-parser hermes` on a Llama-3.1 model (or omitting `--enable-auto-tool-choice`) yields no parsed tool calls; the mesh's tool-delegation stalls.
**How to avoid:** Pair `hermes`↔Qwen2.5, `llama3_json`↔Llama-3.1, always with `--enable-auto-tool-choice`. Bake the correct pair into `make run-vllm` (D-08) and restate in RUNBOOK.

### Pitfall 5: `make use-cloud` via `git checkout` corrupts on a dirty tree
**What goes wrong:** Restoring with `git checkout config/model_gateway.config.yaml` fails or does the wrong thing if the tree has genuine edits, and won't work in a non-git export.
**How to avoid:** Restore with `cp config/model_gateway.cloud.yaml config/model_gateway.config.yaml` (Pattern 3).

### Pitfall 6: Assuming `build_router` egresses at construction (it does NOT)
**What goes wrong:** A planner might guard LOCAL-04 with network mocks "to be safe," adding complexity.
**Why it's a non-issue:** `litellm.Router(...)` construction is lazy — it loads `model_list` into memory and makes no provider call. **Verified this session** by constructing a real Router from the cloud config offline (and the existing default-lane `test_build_router_loads_yaml_fallbacks_and_retries` already does exactly this in `make test`). `[VERIFIED: venv probe + existing passing test]`
**Defensive note (cold box):** On a machine with no internet, litellm may attempt to fetch its model-cost map at import for *cost lookups* (not routing). Setting `LITELLM_LOCAL_MODEL_COST_MAP=True` forces the bundled map. Not needed for LOCAL-04 (construction doesn't price), but worth a one-line RUNBOOK mention for fully-offline operators. `[CITED: litellm docs — local cost map]`

## Code Examples

### LOCAL-04 test skeleton (mirror `tests/test_d06_chokepoint.py`, invert api_base assertion)
```python
# tests/test_local_profiles.py  — default lane, creds-free, NO network (D-09)
from pathlib import Path
import pytest, yaml

_REPO = Path(__file__).resolve().parents[1]
_PROFILES = {
    "vllm":   _REPO / "config" / "model_gateway.vllm.yaml",
    "ollama": _REPO / "config" / "model_gateway.ollama.yaml",
}
_NAMES = {"low-complexity", "medium-complexity", "high-complexity"}
_LOOPBACK = ("http://localhost", "http://127.0.0.1")
_CLOUD_MARKERS = ("os.environ/CF_AIG_WRAPPER_URL", "vertex_ai", "anthropic",
                  "googleapis.com", "anthropic.com")  # Phase-11-friendly negative guard

@pytest.mark.parametrize("name", list(_PROFILES))
def test_profile_has_three_exact_deployment_names(name):
    cfg = yaml.safe_load(_PROFILES[name].read_text())
    got = {r["model_name"] for r in cfg["model_list"]}
    assert _NAMES <= got, f"{name}: missing exact deployment names; has {got}"

@pytest.mark.parametrize("name", list(_PROFILES))
def test_every_route_api_base_is_loopback(name):
    cfg = yaml.safe_load(_PROFILES[name].read_text())
    for r in cfg["model_list"]:
        ab = r["litellm_params"]["api_base"]
        assert ab.startswith(_LOOPBACK), f"{name}/{r['model_name']}: api_base {ab!r} not loopback"
        assert not any(m in ab for m in _CLOUD_MARKERS), f"{name}: cloud marker in api_base {ab!r}"

@pytest.mark.parametrize("name", list(_PROFILES))
def test_no_cloud_named_route(name):   # D-06: no high-complexity-vertex
    cfg = yaml.safe_load(_PROFILES[name].read_text())
    got = {r["model_name"] for r in cfg["model_list"]}
    assert "high-complexity-vertex" not in got, f"{name}: cloud route leaked into local profile"

@pytest.mark.parametrize("name", list(_PROFILES))
def test_build_router_constructs_with_no_network(name):
    from litellm import Router
    from agent_mesh.worker.model_gateway import build_router
    router = build_router(str(_PROFILES[name]))     # constructs offline (Pitfall 6)
    assert isinstance(router, Router)
    assert {d["model_name"] for d in router.model_list} >= _NAMES
```
> Needs `litellm` importable (already a default-lane dep — `test_model_gateway_router.py` relies on it). Add a `pytest.importorskip("litellm")` only if the planner wants to match any existing loud-skip convention; the existing router test does **not** skip, so matching it (no skip) keeps the lane consistent.

### `make run-vllm` target (D-07/D-08 — baked parser flags)
```makefile
# Best-effort, operator-only, NEVER in `make test` / CI (D-07).
VLLM_MODEL ?= Qwen/Qwen2.5-7B-Instruct
run-vllm:
	vllm serve $(VLLM_MODEL) \
		--port 8000 \
		--enable-auto-tool-choice \
		--tool-call-parser hermes      # hermes == Qwen2.5; use llama3_json for Llama-3.1

OLLAMA_MODEL ?= qwen2.5:7b-instruct
run-ollama:
	ollama pull $(OLLAMA_MODEL) && ollama serve

use-vllm:
	cp config/model_gateway.vllm.yaml config/model_gateway.config.yaml
use-ollama:
	cp config/model_gateway.ollama.yaml config/model_gateway.config.yaml
use-cloud:
	cp config/model_gateway.cloud.yaml config/model_gateway.config.yaml
```
> Add the new targets to `.PHONY` and the `help:` block to match Makefile conventions (Makefile:1, :6-19).

### Operator `vllm serve` (verified flag shape) `[CITED: docs.vllm.ai/.../tool_calling]`
```bash
vllm serve Qwen/Qwen2.5-7B-Instruct --enable-auto-tool-choice --tool-call-parser hermes
# Llama alt: vllm serve meta-llama/Llama-3.1-8B-Instruct --enable-auto-tool-choice \
#            --tool-call-parser llama3_json
```

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| "LiteLLM auto-handles vLLM api_base" (per public doc, no `/v1`) | Must append `/v1` for `hosted_vllm` chat (per installed 1.83.7 source) | The marketing doc is internally inconsistent; trust the installed source. Pitfall 1. |
| Ollama `ollama/` for everything | `ollama_chat/` for tool-calling (`/api/chat`) | Tool-calling correctness. Pitfall 2. |

**Deprecated/outdated:** Nothing project-internal. Cloud profile's `high-complexity-vertex` route is intentionally **dropped** in local profiles (D-06), not deprecated globally.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Exact Ollama tags `qwen2.5:7b-instruct` / `llama3.1:8b-instruct` | Standard Stack | Operator `ollama pull` fails with a "model not found"; trivially fixed by `ollama list` / picking the right tag. Verify with `ollama pull qwen2.5:7b-instruct`. Does NOT affect LOCAL-04 (offline build). |
| A2 | VRAM figures (7B fp16 ≈ 14–16 GB; Q4 ≈ ~5 GB) | Standard Stack | Operator may under/over-provision GPU; guidance only, no code impact. |
| A3 | vLLM ≥ 0.6.0 floor for hermes/llama3_json parsers | Standard Stack | Older vLLM may not have the parser; operator upgrades vLLM. Document "recent vLLM" in RUNBOOK. |
| A4 | `LITELLM_LOCAL_MODEL_COST_MAP` is the offline cost-map guard env name | Pitfall 6 | Only matters for a fully-offline cold box; not load-bearing for LOCAL-04. |

## Open Questions

1. **Exact Ollama tag strings (A1).**
   - What we know: family + size are right (`qwen2.5`, 7b instruct); Ollama publishes these.
   - What's unclear: the precise tag suffix (`:7b-instruct` vs `:7b` vs `:7b-instruct-q4_K_M`).
   - Recommendation: the planner pins one and the RUNBOOK tells the operator to `ollama list` / adjust `OLLAMA_MODEL`. Non-blocking for LOCAL-04.

2. **Keep or trim `litellm_settings.success_callback: ["langfuse","otel"]` in local profiles?**
   - What we know: locally these callbacks are inert/harmless (free tokens; Langfuse may be absent).
   - Recommendation: mirror the cloud config (keep them) for structural parity — they don't trigger egress at `build_router` construction. Planner's call; not asserted by LOCAL-04.

## Environment Availability

| Dependency | Required By | Available (this box) | Version | Fallback |
|------------|------------|----------------------|---------|----------|
| `litellm` (Python) | LOCAL-04 build_router test | ✓ (in `.venv`) | 1.83.7 | — (it's a default-lane dep already) |
| `vllm` | `make run-vllm` (operator) | ✗ (not probed; GPU box only) | — | Use `make run-ollama` (CPU/dev) — D-07 accepts run-vllm failing on a non-GPU box |
| `ollama` | `make run-ollama` (operator) | ✗ (not installed here) | — | Document install; D-07 accepts failure on a box without it |
| `pyyaml` | profile parsing + test | ✓ (build_router lazy-imports `yaml`) | — | — |

**Missing dependencies with no fallback:** none that block the phase. LOCAL-01..04 are **authoring + test** deliverables; `make run-*` are best-effort operator targets whose absence is explicitly acceptable (D-07). The only CI-relevant dep (`litellm`) is present.

## Sources

### Primary (HIGH confidence)
- **Installed litellm 1.83.7 source** — `litellm/llms/openai/chat/gpt_transformation.py:665` (`get_complete_url` appends only `chat/completions`, no `/v1`) and `litellm/llms/hosted_vllm/chat/transformation.py` (`HostedVLLMChatConfig(OpenAIGPTConfig)`). Authoritative for Pitfall 1.
- **Empirical probe (this session)** — `build_router("config/model_gateway.config.yaml")` constructs a real `litellm.Router` offline; existing default-lane `tests/test_model_gateway_router.py::test_build_router_loads_yaml_fallbacks_and_retries` corroborates. Pitfall 6.
- `src/agent_mesh/worker/model_gateway.py` — seam (`build_router`, `TIER_TO_DEPLOYMENT`, D-06 relocation note).
- `tests/test_d06_chokepoint.py` — the mirror template for LOCAL-04.
- `config/model_gateway.config.yaml` — the profile structure to mirror.

### Secondary (MEDIUM confidence)
- docs.vllm.ai `/features/tool_calling` — `--enable-auto-tool-choice`, `--tool-call-parser hermes|llama3_json`.
- qwen.readthedocs.io `/framework/function_call` — Qwen2.5 ships Hermes chat template.
- docs.litellm.ai `/docs/providers/ollama` — `ollama_chat/` for tool-calling, `http://localhost:11434`, no `/v1`.

### Tertiary (LOW confidence — flagged in Assumptions Log)
- Exact Ollama tag strings (A1), VRAM figures (A2), vLLM version floor (A3) — verify operationally; none block LOCAL-04.

## Metadata

**Confidence breakdown:**
- Standard stack / pins: HIGH (parsers + prefixes cited; litellm version verified) — exact Ollama tags LOW (A1).
- Architecture / patterns: HIGH (mirrors existing frozen seam + existing test template).
- Pitfalls: HIGH — Pitfall 1 and Pitfall 6 settled against **installed source + empirical probe**, not training data.

**Research date:** 2026-06-08
**Valid until:** ~2026-07-08 (stable; re-check only if litellm is upgraded past 1.83.x, which could change `get_complete_url` path handling — re-verify Pitfall 1 on any litellm bump).
