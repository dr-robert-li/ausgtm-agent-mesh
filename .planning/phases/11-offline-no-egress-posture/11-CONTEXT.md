# Phase 11: Offline / No-Egress Posture - Context

**Gathered:** 2026-06-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Make **"runs offline with no cloud-hosted LLM egress"** an *asserted* property, not a hope —
an OFFLINE config/.env posture plus tests that fail if any local model profile, the assembled
compose stack, or the default creds-free lane can reach a **cloud LLM provider or model
gateway**. Boundary fixed by OFFLINE-01/02/03. Config / .env / docs / tests only — **zero
`src/` change** (assert `git diff <phase-base>..HEAD -- src/` empty).

**CRITICAL SCOPE (user clarification 2026-06-10):** "Offline" means **no cloud-hosted LLM
inference** — Vertex AI, Anthropic-direct, and the Cloudflare AI Gateway model path. It does
**NOT** mean blocking all outbound network. Local Postgres, self-hosted Langfuse, service-DNS
model backends (`vllm:8000`, `ollama:11434`), and SaaS tool-pack adapters reaching their own
APIs are all **legitimate** and out of scope for restriction. Every assertion targets the
**model/gateway egress path only**, via a cloud-LLM-marker deny-list — never a blanket socket
or network block.

</domain>

<decisions>
## Implementation Decisions

### A — Egress-assertion scope (OFFLINE-02)
- **D-01 (whole-file cloud-LLM sweep across all 4 local profiles):** Extend the assertion
  beyond `api_base` to a **whole-file** cloud-LLM-marker sweep over **all four** local profiles:
  `config/model_gateway.vllm.yaml` + `model_gateway.ollama.yaml` (loopback) and the P10
  compose variants `model_gateway.vllm.compose.yaml` + `model_gateway.cpu.compose.yaml`
  (service-DNS). **Allowlist** local targets — loopback (`http://localhost`, `http://127.0.0.1`)
  and in-stack service-DNS (`vllm:8000`, `ollama:11434`). **Deny** cloud-LLM markers anywhere
  in the file: `CF_AIG_WRAPPER_URL`, `vertex_ai`, `googleapis.com`, `anthropic`, `anthropic.com`,
  `sk-`. Catches a stray Vertex/Anthropic/CF reference that sits *outside* `api_base`, which the
  current api_base-only guard would miss. **Service-DNS is treated as egress-free in-stack**, not
  required to be loopback.

### B — Default-lane no-model-egress enforcement (OFFLINE-03)
- **D-02 (model-host deny-guard, connect-level, correctly scoped):** Enforce "the default
  creds-free lane makes no outbound to a real LLM provider/gateway" with a **model-host
  deny-guard** — an autouse test fixture patching the connect/transport seam to **raise only
  on known cloud-LLM hosts** (`anthropic.com`, `*.googleapis.com` Vertex, the CF AI Gateway
  host, and `MODEL_GATEWAY_BASE_URL` when it resolves cloud). **Every other host is allowed**
  (Postgres, Langfuse, SaaS adapters) — this is NOT a `pytest-socket disable_socket`-style
  global block (rejected: over-reaches into legitimate local/SaaS traffic and mischaracterizes
  the scope). The guard runs over the default creds-free lane, which today makes no model call
  (`build_router` is lazy — Pitfall 6, verified litellm 1.83.7), so it should pass clean,
  PROVING the posture; anything that trips it is a real finding. Test-only, **zero new `src/`**.
  *(Planner: the deny-guard needs at least one test that actually exercises a representative
  default-lane path under the fixture so the proof is non-vacuous.)*

### C — OFFLINE posture expression (OFFLINE-01)
- **D-03 (`.env.offline.example` concrete artifact):** Ship a concrete **`.env.offline.example`**
  expressing the posture: `CF_AIG_WRAPPER_URL=` blank, `ANTHROPIC_API_KEY=` blank, `VERTEX_*`
  blank, `MODEL_GATEWAY_BASE_URL` local, local model `api_base` via the `use-vllm`/`use-ollama`
  profile swap. **SaaS/tool-pack creds are left as normal** — offline zeroes only the
  cloud-LLM/gateway creds. Plus a RUNBOOK "Offline / no-egress posture" section. Chosen over
  documented-posture-only because a concrete artifact is testable (OFFLINE-02's sweep can run
  over it) and copy-pasteable. **No new runtime OFFLINE env-guard** — zero-`src/` forbids reading
  a new env var at runtime; OFFLINE is asserted-over-config + documented, not a runtime switch.

### D — Assertion reach into the assembled stack (OFFLINE-02, roadmap "across the assembled local stack")
- **D-04 (profiles + `docker-compose.yml` env sweep):** The no-cloud-LLM sweep also covers the
  `docker-compose.yml` `api`/`worker` env blocks — assert **no cloud-LLM `api_base`** and **no
  VALUED cloud-LLM key** (Vertex/Anthropic/CF) in the composed stack. Local Postgres, self-hosted
  Langfuse, and service-DNS references stay legitimate and must NOT trip the sweep. Honors the
  roadmap "across the assembled local stack" wording rather than the narrower
  success-criterion-2 "model profiles" reading.

### Carried forward (locked — do NOT re-litigate)
- **Zero `src/` change** — config/.env/Makefile/docs/tests only; a [BLOCKING] invariant asserts
  `git diff <phase-base>..HEAD -- src/` is empty (mirrors P8/P9/P10). *(See P10 Audit Note 1:
  P10 enforced this as a one-shot bash gate, not durable CI — Phase 11 should consider a durable
  test-level assertion since it also carries the guardrail.)*
- **make + RUNBOOK + loud-skip-test** delivery; operator run/swap targets are best-effort, never
  wired into `make test`/CI. Canonical test interpreter is `.venv/bin/python` (bare PATH python
  3.14 lacks deps).
- **P8 D-06** already dropped cloud-named routes (`high-complexity-vertex`) from local profiles;
  fallbacks stay within the 3 local deployment names — no cloud route exists for the sweep to trip.

### Claude's Discretion
- Exact connect/transport seam for the deny-guard (e.g. `socket.getaddrinfo` /
  `socket.create_connection` vs an httpx/litellm transport hook) — researcher/planner picks the
  cleanest host-level interception that needs no `src/` change. Decision captured = deny only
  cloud-LLM hosts at connect level; mechanism is open.
- Exact cloud-LLM marker/host list finalization (the D-01/D-02 lists are the floor; planner may
  add e.g. `openai`/`sk-ant-` if justified) — keep it cloud-LLM-scoped, not generic-online.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` — Phase 11 goal, depends-on (8/9/10), 3 success criteria
- `.planning/REQUIREMENTS.md` — OFFLINE-01, OFFLINE-02, OFFLINE-03 (lines ~141-143)

### The seam being extended (MOST important — Phase 11 builds on these)
- `tests/test_local_profiles.py` — the existing LOCAL-04 guard (loopback api_base +
  `_CLOUD_MARKERS` no-cloud sweep, 3-name + no-cloud-named-route). Its own docstring states the
  whole-file no-cloud-env-ref sweep is "Phase 11's job." **Extend this, don't duplicate.**
- `tests/test_d06_chokepoint.py` — the P3 CF-chokepoint test that asserts every route egresses
  through the CF wrapper; `test_local_profiles.py` INVERTS it. Mirror its config-load pattern.

### Artifacts the sweep/posture operate on
- `config/model_gateway.vllm.yaml`, `config/model_gateway.ollama.yaml` (loopback profiles)
- `config/model_gateway.vllm.compose.yaml`, `config/model_gateway.cpu.compose.yaml` (P10 service-DNS profiles)
- `config/model_gateway.config.yaml` / `config/model_gateway.cloud.yaml` (active-swap + pristine cloud)
- `docker-compose.yml` — api/worker env blocks (D-04 sweep target)
- `.env.example` — existing cloud-LLM key block (lines ~51-56: `CF_AIG_WRAPPER_URL`,
  `ANTHROPIC_API_KEY`, `VERTEX_PROJECT_ID`, `VERTEX_LOCATION`) — basis for `.env.offline.example`
- `RUNBOOK.md` — add the "Offline / no-egress posture" section near the P8/P9/P10 local sections

### Prior decisions that constrain this phase
- `.planning/phases/08-local-inference-lane/08-CONTEXT.md` — D-06 (no cloud-named routes),
  D-01/D-02 (file-swap profile selection, `use-*` targets)
- `.planning/phases/10-full-stack-local-compose/10-SECURITY.md` — Audit Note 1 (zero-src invariant
  is a one-shot bash gate in P10, not durable CI — consider durable assertion here)
- `tests/conftest.py` — autouse-fixture + loud-skip patterns to mirror for the deny-guard
- `Makefile` — `use-vllm`/`use-ollama`/`use-cloud` swap targets; `test` / `test-pg` lanes
- `docs/production-readiness-caveats.md` — offline/egress posture caveats (deploy-ready-only scope)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tests/test_local_profiles.py`: `_CLOUD_MARKERS` tuple, `_LOOPBACK` allowlist, `_NAMES`,
  parametrized per-profile sweep — the direct extension point for D-01 (add the 2 compose
  profiles + service-DNS allowlist + whole-file sweep).
- `tests/test_d06_chokepoint.py`: config-load + per-route assertion pattern to mirror/invert.
- `tests/conftest.py`: autouse fixture + `TEST_DATABASE_URL` loud-skip patterns — template for
  the D-02 model-host deny-guard fixture.
- `Makefile`: `use-vllm`/`use-ollama`/`use-cloud` swaps; best-effort operator targets kept out of CI.

### Established Patterns
- Config-validation tests load YAML and assert over it (no live model call); the default lane is
  creds-free and makes no provider call (`build_router` lazy, Pitfall 6) — D-02's guard should
  pass clean on it.
- Cloud markers are LLM-provider-specific (`CF_AIG_WRAPPER_URL`, `vertex_ai`, `anthropic`,
  `googleapis.com`) — reuse, do not invent a generic "any cloud" list.

### Integration Points
- New tests slot into the default `make test -m "not live"` lane (the only CI-wired Phase-11
  artifacts, like P10's `test_compose_config.py`). The `.env.offline.example` + RUNBOOK section
  are operator-facing docs/config. No `src/` connection — assertions read config/compose/env files.

</code_context>

<specifics>
## Specific Ideas

- "Offline = no cloud-hosted LLMs, not restricting every online service" (user, 2026-06-10) — the
  load-bearing scope constraint for the whole phase. Deny-list is cloud-LLM hosts/markers only.
- Service-DNS (`vllm:8000`, `ollama:11434`) is egress-free in-stack and must be allowlisted, not
  flagged as non-loopback.

</specifics>

<deferred>
## Deferred Ideas

- **Runtime OFFLINE enforcement guard** (an env-gated `OFFLINE=1` that hard-blocks cloud-LLM
  routes at runtime) — requires reading a new env var in `src/`, forbidden by the zero-`src/`
  milestone guardrail. Defer to a future src-touching milestone; Phase 11 is assert-over-config +
  documented-posture only.
- **Distinct-model-per-tier** locally — already deferred in Phase 8 (D-04, one shared model, 3
  nominal tiers). Not reopened here.
- **Blanket no-network test posture** (block ALL outbound) — explicitly rejected this phase as
  out-of-scope over-reach; offline is cloud-LLM-scoped only.

</deferred>
