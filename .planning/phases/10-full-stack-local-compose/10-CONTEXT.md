# Phase 10: Full-Stack Local Compose - Context

**Gathered:** 2026-06-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Assemble the entire mesh as a **one-command local docker-compose stack** — api +
worker + gui + Postgres(pgvector) + Langfuse + LiteLLM + a local model backend —
composing the Phase 8 (local inference profiles) and Phase 9 (local data/telemetry)
pieces. Requirements: **COMPOSE-01/02/03**.

**In scope:** a `docker-compose.yml` that brings up the required services; a real
project `Dockerfile` for the app services; `make compose-up` / `make compose-down`
wrappers; a RUNBOOK one-command-bring-up section; and a compose-validation test/lint
(`docker compose config` parses + required services/healthchecks/pgvector image
present), loud-skipping when docker is absent.

**Hard guardrail (whole v1.1 milestone):** config / docker-compose / docs / tests
**ONLY**. **Zero `src/` production code change.** Deployment names
(`low/medium/high-complexity`) stay constant; the LiteLLM Router seam + agent code are
untouched. Offline enforcement is Phase 11's job (test-asserted over config), not here.

**Out of scope (Phase 11 owns):** the OFFLINE / no-egress posture + the egress-absence
assertions over the assembled stack.
</domain>

<decisions>
## Implementation Decisions

### L — Locked assumptions (confirmed, not re-litigated)
- **L1 — Dockerfile permitted:** A `Dockerfile` is in-scope this milestone. It is
  packaging/config, not `src/`; docker-compose is explicitly named in the guardrail. No
  `src/` edit accompanies it.
- **L2 — "One command" via make + `--profile`:** COMPOSE-01's "one command" is honored
  by `make compose-up` passing docker-compose `--profile` flags. Raw `docker compose up`
  stays lean (core only); the make target activates the heavier profiles. COMPOSE-03's
  "required services" = the always-on (non-profiled) core set; profile-gated services are
  asserted by naming the profile in `docker compose config`.
- **L3 — GUI entrypoint:** the Streamlit entry is `src/agent_mesh/gui/admin_app.py`
  (Makefile `run-gui`-confirmed). `admin_console.py` is a supporting module, NOT the entry.

### A — App-image strategy (COMPOSE-01)
- **D-01 (one shared Dockerfile, command-parameterized):** A single real project
  `Dockerfile` builds one image; api/worker/gui are three compose services differing only
  by `command:` (`uvicorn agent_mesh.api.app:app --port 8080` / `python -m
  agent_mesh.worker.main` / `streamlit run src/agent_mesh/gui/admin_app.py`). Chosen for
  **deploy-fidelity** — the compose proves the same artifact GCP Cloud Run would run. (P7
  deploy scripts already name `agent-mesh-api` / `agent-mesh-worker` images;
  command-parameterizing one image is the lean way to mirror that topology.) Rejected:
  base-python + bind-mount (no real artifact, diverges from deploy); per-service
  Dockerfiles (boilerplate for one shared codebase).
- **D-02 (worker mounts the Docker socket):** The worker service bind-mounts
  `/var/run/docker.sock` so the **real P2 hardened prompt-to-code sandbox** (which spawns
  sibling containers) actually runs inside the composed stack — not stubbed out. Chosen
  for real in-stack validation of the sandbox path. **RUNBOOK MUST disclose** the
  privileged docker-socket mount as **dev-only** (security wrinkle; not a production
  posture). Researcher: confirm the app image carries whatever the worker needs to reach
  the socket (python docker SDK / docker CLI) — without a `src/` change.

### B — Langfuse depth (COMPOSE-01)
- **D-03 (full v3 inlined behind `--profile langfuse`):** The full self-hosted Langfuse
  v3 service set (~6 containers: web + worker + its own postgres + clickhouse + redis +
  minio) is declared in OUR `docker-compose.yml` but **profile-gated** as
  `profiles: [langfuse]`. Raw `docker compose up` = lean core; `make compose-up` adds
  `--profile langfuse` for the full one-command bring-up (L2). Rejected: always-on inline
  (every dev pays clickhouse+minio+redis even when not tracing); `include:` upstream
  compose (pins an external file/version, complicates the single-file COMPOSE-03
  `docker compose config` assertion).
- **D-03a (UI-minted-keys caveat carries forward):** Langfuse public/secret keys are
  **UI-generated per-project**, so even with the langfuse profile up, mesh **tracing
  loud-skips on first bring-up** until a human mints keys in the Langfuse UI and sets
  `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`. RUNBOOK must state this so "one command"
  isn't oversold (carried from Phase 9 D-02).

### C — Local model backend (COMPOSE-01)
- **D-04 (vLLM default, Ollama `--profile cpu`):** vLLM is the **composed default** model
  service (GPU, OpenAI-compatible, stronger tool-calling throughput — the real-serving
  choice). Ollama is the CPU fallback behind `--profile cpu`. The composed model service
  consumes the matching Phase-8 profile (`config/model_gateway.vllm.yaml` /
  `.ollama.yaml`) via mount.
- **D-05 (single `make compose-up`, env-selected backend):** One `make compose-up` reads
  `MODEL_PROFILE ?= vllm` (values `vllm` | `cpu`) and passes `--profile $(MODEL_PROFILE)`
  (+ `--profile langfuse`). vLLM-default needs a GPU; non-GPU operators run
  `MODEL_PROFILE=cpu make compose-up`. RUNBOOK documents vLLM as default/real path and the
  CPU override. (No separate `compose-up-cpu` target — the env var is the switch.)

### D — "LiteLLM" service shape (COMPOSE-01) — verified
- **D-06 (in-process Router; NO standalone litellm service):** "LiteLLM" in COMPOSE-01 is
  satisfied by the **in-process `litellm.Router`** already embedded in api/worker — they
  ARE the LiteLLM control plane. **No standalone `litellm` proxy container.**
  **Verification (this discussion):**
  - Real completions route through `get_chat_model`/`get_router_chat_model` → in-process
    `RouterChatLiteLLM` reading per-route `api_base` from the yaml `model_list` (D-06
    chokepoint). Consumers: `worker/graph.py:149`, `eval/judges.py:351`.
  - `settings.model_gateway_base_url` (env `MODEL_GATEWAY_BASE_URL`, default `:4000`) is
    read by **exactly one** site — `gui/admin_console.py:49`, a status-panel display
    string. It drives **zero** provider calls. Vestigial/display-only.
  - Deploy scripts define images `agent-mesh-api/-worker/-code-executor` only — **no
    `litellm` Cloud Run service exists.** A local proxy container would invent a topology
    absent from deploy, breaking the deploy↔local fidelity locked in D-01, and routing
    agents through it would require a forbidden `src/` rewire off the GW-02 structural
    chokepoint (`get_chat_model`) that tests assert.
  - **RUNBOOK + a manifest/doc note** must state "LiteLLM runs embedded in api/worker, not
    as a proxy — mirrors deploy (no litellm image)" so COMPOSE-01's wording is not read as
    a missing required service. COMPOSE-03's required-services list omits a litellm
    container by design.

### Claude's Discretion (planner/researcher to finalize)
- Per-service **healthchecks** — COMPOSE-03 asserts healthchecks are *present*; which
  services carry them and the exact probes are the planner's call (pgvector readiness,
  api `/health`, langfuse-web, model backend).
- **Inter-service env/DNS wiring** — service names for DSN/host resolution (e.g.
  `postgres`, `langfuse-web`, the vllm/ollama service) and which env each app service
  receives. Must reuse Phase-9 pinned defaults (DSN creds/port, `LANGFUSE_HOST`).
- **`make compose-down` scope** — bringing down all profiles (e.g. `--profile "*"` or
  enumerated) so a profiled-up stack tears down cleanly.
- Exact `docker compose config` assertion shape in the COMPOSE-03 test (which services /
  healthcheck keys / the `pgvector/pgvector:pg16` image string to assert), and whether
  profiled services are asserted by passing the profile name(s).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` § "Phase 10: Full-Stack Local Compose" — goal + 3 success
  criteria; and the v1.1 milestone guardrail block (config/compose/docs/tests ONLY,
  deployment names unchanged, zero `src/` change).
- `.planning/REQUIREMENTS.md` § "Full-Stack Compose (Phase 10)" — COMPOSE-01/02/03
  (lines ~133-137; traceability ~220-222).

### Carry-forward context (the pieces being composed)
- `.planning/phases/08-local-inference-lane/08-CONTEXT.md` — local model profiles
  (`config/model_gateway.vllm.yaml` / `.ollama.yaml`, 3 nominal tiers, one shared model),
  the file-swap selection mechanism, and best-effort/loud-skip/honest-disclosure pattern.
- `.planning/phases/09-local-data-telemetry-plane/09-CONTEXT.md` — pinned local DSN
  (`postgresql://postgres:postgres@localhost:5432/agent_mesh`), pgvector image
  `pgvector/pgvector:pg16`, `LANGFUSE_HOST=http://localhost:3000`, Langfuse UI-minted-keys
  loud-skip, migrations 0001-0004 applied by the conftest fixture.

### Service entrypoints (the commands the shared image runs)
- `src/agent_mesh/api/app.py` — FastAPI app (`uvicorn agent_mesh.api.app:app`).
- `src/agent_mesh/worker/main.py` — worker entry (`python -m agent_mesh.worker.main`).
- `src/agent_mesh/gui/admin_app.py` — Streamlit entry (L3). **Reference only — no edit.**

### Model gateway seam — DO NOT modify `src/` (verifies D-06)
- `src/agent_mesh/worker/model_gateway.py` — `build_router(config_path)` (`:87`),
  `get_chat_model`/`get_router_chat_model` (the real in-process completion path),
  per-route `api_base` relocation (`:180`-197, D-06). The GW-02 structural chokepoint.
- `src/agent_mesh/settings.py:47` — `model_gateway_base_url` (display-only; not a
  completion path). `src/agent_mesh/gui/admin_console.py:49` — its sole reader.

### Deploy topology to mirror (D-01) — reference only
- `scripts/gcp_deploy_core.sh:16-18` — `agent-mesh-api` / `-worker` / `-code-executor`
  image names (no gui image, no litellm image — informs D-01/D-06).
- `manifests/deployment.manifest.yaml` — `artifact_registry_repo`, `model_routes`,
  `provider_mode` (deployment-name source of truth; do not break name parity).

### Targets/docs to extend (mirror existing style)
- `Makefile` — `run-api` (`:63`), `run-worker` (`:66`), `run-gui` (`:69`),
  `test`/`test-pg`/`smoke`, and the P8/P9 `run-*`/`use-*`/`run-pg` best-effort pattern.
  Add `compose-up` / `compose-down` mirroring these conventions.
- `RUNBOOK.md` — existing "Local inference lane" (P8) + "Local data/telemetry plane" (P9,
  incl. the Langfuse self-host doc-only section at ~L219) sections. Add the one-command
  full-stack-compose section after them; reconcile with the P9 Langfuse note.
- `.env.example` — already carries `DATABASE_URL`, `LANGFUSE_*`, `MODEL_GATEWAY_BASE_URL`,
  `MODEL_PROVIDER_MODE`; compose env wiring reuses these (no new keys expected).

No new external specs/ADRs — decisions fully captured above.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Existing `make run-api/run-worker/run-gui` commands are the **exact `command:` strings**
  the three compose services run on the shared image (D-01).
- Phase-8 `config/model_gateway.{vllm,ollama}.yaml` profiles + Phase-9 `pgvector/pgvector:pg16`
  + DSN defaults are consumed directly — no new config authored, only mounted/wired.
- `build_router(config_path)` / `get_chat_model` already drive completions in-process →
  no litellm proxy needed (D-06).

### Established Patterns
- **Best-effort operator targets, out of CI, loud-skip on missing docker/env** (P8/P9):
  `compose-up`/`compose-down` follow this; the COMPOSE-03 validation test is the only
  CI-wired piece and it stays static (`docker compose config`, no bring-up) + loud-skips
  when docker is absent.
- **Honest disclosure in RUNBOOK** (P8/P9): docker-socket mount = dev-only;
  Langfuse keys UI-minted → tracing loud-skips; vLLM-default needs GPU; LiteLLM embedded.
- **Zero `src/` change** — assert `git diff <base>..HEAD -- src/` empty (same invariant
  as P8/P9).

### Integration Points
- `make compose-up` `MODEL_PROFILE` ↔ the mounted model profile ↔ the model backend
  service (vllm/ollama) must agree (D-04/D-05).
- Composed Postgres creds/port MUST match the Phase-9 pinned `DATABASE_URL` default.
- Worker `/var/run/docker.sock` mount ↔ the P2 sandbox container path (D-02).
- Phase 11 (no-egress) asserts the assembled stack's profiles carry no cloud `api_base` /
  cloud-key env — D-04's local-only profiles + D-06's no-proxy keep that assertion clean.
</code_context>

<specifics>
## Specific Ideas

- One shared `Dockerfile` at repo root; three services `build: .` differing by `command:`.
- `make compose-up` → `docker compose --profile $(MODEL_PROFILE) --profile langfuse up -d`
  with `MODEL_PROFILE ?= vllm` (override `MODEL_PROFILE=cpu` for non-GPU boxes).
- Langfuse v3 services declared with `profiles: [langfuse]`; model backends with
  `profiles: [vllm]` / `profiles: [cpu]`.
- Worker service: `volumes: [/var/run/docker.sock:/var/run/docker.sock]` (dev-only,
  documented).
- pgvector pinned `pgvector/pgvector:pg16`; DSN
  `postgresql://postgres:postgres@localhost:5432/agent_mesh` (Phase-9 parity, service-DNS
  host inside compose, e.g. `@postgres:5432`).
</specifics>

<deferred>
## Deferred Ideas

- **Standalone LiteLLM proxy container** — rejected this phase (breaks deploy↔local
  fidelity + needs forbidden `src/` rewire, D-06). Would only make sense if the platform
  itself ever migrates to a proxy-based gateway (a future architecture change, not v1.1).
- **OFFLINE / no-egress assertions over the assembled stack** → **Phase 11** (OFFLINE-01/02/03).
- **Actual `compose up` smoke in CI** (vs the static `docker compose config` validation)
  → out of scope; COMPOSE-03 is static + loud-skip by design (heavy bring-up stays an
  operator/best-effort action).
- **Distinct-model-per-tier in the composed model backend** → inherited P8 deferral
  (one shared model, 3 nominal tiers).

None of the above is in Phase 10 scope; discussion stayed within the compose-assembly boundary.
</deferred>

---

*Phase: 10-full-stack-local-compose*
*Context gathered: 2026-06-10*
