# Phase 10: Full-Stack Local Compose - Research

**Researched:** 2026-06-10
**Domain:** docker-compose assembly (single-file, profile-gated) of an already-built Python agent mesh + self-hosted Langfuse v3 + local model backend
**Confidence:** HIGH (all compose behaviors + the D-02 identical-path DooD bind empirically verified on docker 27.5.1 / Docker Desktop macOS; Langfuse v3 service set fetched from upstream `main`; D-02 CLI-not-SDK verdict source-backed). Three functional gaps found, all with verified config-only fixes (no `src/` change): Finding #1 model api_base, Finding #2 DooD sandbox path, Pitfall 5 in-stack migrations.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **L1 — Dockerfile permitted** this milestone (packaging/config, not `src/`).
- **L2 — "One command" via make + `--profile`:** `make compose-up` passes `--profile` flags; raw `docker compose up` stays lean (core only). COMPOSE-03 "required services" = the always-on (non-profiled) core set; profile-gated services asserted by naming the profile in `docker compose config`.
- **L3 — GUI entrypoint** is `src/agent_mesh/gui/admin_app.py` (Makefile `run-gui`-confirmed). `admin_console.py` is a supporting module, NOT the entry.
- **D-01 (one shared Dockerfile, command-parameterized):** ONE real root `Dockerfile` builds ONE image; api/worker/gui are three services differing only by `command:` (`uvicorn agent_mesh.api.app:app --port 8080` / `python -m agent_mesh.worker.main` / `streamlit run src/agent_mesh/gui/admin_app.py`). Deploy-fidelity rationale (mirrors `agent-mesh-api`/`-worker` image names).
- **D-02 (worker mounts `/var/run/docker.sock`):** so the real P2 sandbox runs in-stack (dev-only). RUNBOOK MUST disclose the privileged mount as dev-only.
- **D-03 (full Langfuse v3 inlined behind `--profile langfuse`):** ~6 containers (web + worker + its own postgres + clickhouse + redis + minio) declared inline but `profiles: [langfuse]`. Rejected: always-on inline; `include:` upstream compose.
- **D-03a (UI-minted keys):** tracing loud-skips on first bring-up until a human mints keys in the Langfuse UI and sets `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`.
- **D-04 (vLLM default, Ollama `--profile cpu`):** vLLM is the composed default (GPU, `profiles: [vllm]`); Ollama is CPU fallback (`profiles: [cpu]`). Composed model service consumes the matching Phase-8 profile via mount.
- **D-05 (single `make compose-up`, env-selected backend):** reads `MODEL_PROFILE ?= vllm` (values `vllm` | `cpu`) and passes `--profile $(MODEL_PROFILE) --profile langfuse`. No separate `compose-up-cpu` target.
- **D-06 (in-process Router; NO standalone litellm service):** "LiteLLM" is the embedded `litellm.Router` in api/worker. No standalone `litellm` proxy container. COMPOSE-03's required-services list omits a litellm container by design.

### Claude's Discretion
- Per-service **healthchecks** — COMPOSE-03 asserts healthchecks *present*; which services carry them + exact probes is the planner's call.
- **Inter-service env/DNS wiring** — service names for DSN/host resolution; must reuse Phase-9 pinned defaults (DSN creds/port, `LANGFUSE_HOST`).
- **`make compose-down` scope** — bring down all profiles so a profiled-up stack tears down cleanly.
- Exact `docker compose config` assertion shape in the COMPOSE-03 test.

### Deferred Ideas (OUT OF SCOPE)
- Standalone LiteLLM proxy container (rejected — breaks deploy↔local fidelity + needs forbidden `src/` rewire).
- OFFLINE / no-egress assertions over the assembled stack → **Phase 11**.
- Actual `compose up` smoke in CI (vs static `docker compose config`) → out of scope; COMPOSE-03 is static + loud-skip by design.
- Distinct-model-per-tier in the composed backend → inherited P8 deferral.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| COMPOSE-01 | A `docker-compose.yml` brings up api + worker + gui + Postgres(pgvector) + Langfuse + LiteLLM + a local model backend (vLLM or Ollama) with one command | Service-set reference blocks below (app/Dockerfile, pgvector, Langfuse v3 ×6, vLLM/Ollama); D-06 makes "LiteLLM" the in-process Router (no container); inter-service wiring table; the compose-profile model-config-mount fix (Finding #1) closes the SC-1 "actually works" gap |
| COMPOSE-02 | `make compose-up` / `make compose-down` wrap the stack; RUNBOOK documents one-command bring-up | `make compose-up` recipe (`--profile $(MODEL_PROFILE) --profile langfuse`); `compose-down` profile-scope recommendation; RUNBOOK section outline incl. dev-only docker-socket + UI-minted-keys + GPU disclosures |
| COMPOSE-03 | A test/lint validates the compose file (`docker compose config` parses; required services + healthchecks + the pgvector image present), loud-skip when docker is absent | Empirically-verified static-validation recipe: daemon-free `docker compose config`, profile-resolution behavior, image-string grep, `shutil.which("docker")` loud-skip mirroring `pg_dsn` |
</phase_requirements>

## Summary

Phase 10 is a **pure-assembly** phase: every runtime component already exists (Phase 1–9). The work is one root `Dockerfile`, one `docker-compose.yml`, two `make` targets, a RUNBOOK section, and one CI-wired static-validation test. All external unknowns are now pinned: the Langfuse v3 self-host service set (6 containers, exact tags + secrets), the vLLM/Ollama compose service shapes (images, GPU reservation syntax, healthchecks), and the exact `docker compose config` behaviors that let COMPOSE-03 be the lone CI-wired piece while bring-up stays operator-only.

**Two load-bearing wiring problems were found and both have config-only fixes (no `src/` change):**

1. **The model `api_base` is NOT env-driven** (unlike `DATABASE_URL`/`LANGFUSE_HOST`). The Phase-8 yaml bakes `http://localhost:8000/v1`, and `build_router` loads a hardcoded path. Inside compose, `localhost` is the api/worker container itself — completions break, making COMPOSE-01's SC-1 "one command brings it up" hollow even though COMPOSE-03 passes. **Fix:** mount a compose-specific profile (`config/model_gateway.<profile>.compose.yaml` with `api_base: http://vllm:8000/v1`) onto the container's `config/model_gateway.config.yaml`, with the volume *source* interpolated by `${MODEL_PROFILE}`. Verified: compose interpolates env in volume source paths.

2. **D-02 is a Docker-out-of-Docker (DooD) path-translation problem, not just CLI-vs-SDK.** The shared image needs the **docker CLI binary** (the executor uses `subprocess.run(["docker", ...])` + `shutil.which("docker")`; the python docker SDK is absent and not needed). The executor also does `-v {snippet_dir}:/snippet:ro` where `snippet_dir` is a tempdir *inside the worker container* — with the socket mounted, the **host** daemon resolves that path on the host FS. **Fix (VERIFIED empirically):** bind a host dir at an **identical absolute path** (source==target) into the worker + redirect the executor's tempdir via `TMPDIR` (executor passes no `dir=`, `tempfile` honors `TMPDIR` — both verified). A mismatched bind (`./.sbxwork:/sbxwork`) fails loudly with "Mounts denied" — proven below. Zero `src/` change.

**A third functional gap (not a wiring bug) was also found:** nothing applies the mesh-postgres migrations inside the composed stack — Phase 9 wired migrations only into the test path, so a fresh `make compose-up` brings api/worker up against a schema-less DB and the first durable call fails. Config-only fix: a one-shot `migrate` compose service (Pitfall 5). Blocks SC-1-as-functional, not SC-3.

**Primary recommendation:** Build the single-file `docker-compose.yml` with non-profiled core (api, worker, gui, postgres) + `profiles: [langfuse]` (×6) + `profiles: [vllm]` / `profiles: [cpu]`. Mount a NEW compose-variant model profile (Finding #1). Wire the worker socket mount + identical-path host bind + `TMPDIR` redirect (Finding #2 — VERIFIED empirically). Add a one-shot `migrate` service (Pitfall 5). Make COMPOSE-03 a daemon-free `docker compose config` assertion that loud-skips on absent docker, mirroring `pg_dsn`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| One-command bring-up | `make` + `docker compose --profile` | docker-compose.yml | L2: make activates heavy profiles; raw compose stays lean |
| App artifact build | Root `Dockerfile` (one image) | docker-compose `command:` per service | D-01 deploy-fidelity (one image, command-parameterized) |
| Inference serving | `vllm`/`ollama` compose service | mounted model profile | D-04: backend service + Phase-8 profile via mount |
| Model routing/budgets | In-process `litellm.Router` (api/worker) | — | D-06: NO container; embedded control plane |
| Durable persistence | `postgres` (pgvector) compose service | migrations applied by conftest, not compose | Phase-9 parity (`pgvector/pgvector:pg16`) |
| Observability backend | Langfuse v3 (6 containers, `--profile langfuse`) | its OWN postgres/clickhouse/redis/minio | D-03: full self-host inline, profile-gated |
| Sandbox execution | worker via `/var/run/docker.sock` (DooD) | host bind + `TMPDIR` redirect | D-02: real sandbox in-stack, dev-only |
| Static validation | `docker compose config` test (CI-wired) | `shutil.which` loud-skip | COMPOSE-03; the ONLY CI piece |

## Standard Stack

### Core (verified images)
| Image | Tag | Purpose | Source |
|-------|-----|---------|--------|
| `pgvector/pgvector` | `pg16` | mesh durable store (pgvector) | [VERIFIED: codebase] — pinned in Makefile `run-pg`, `.env.example`, conftest note |
| `langfuse/langfuse` | `3` | Langfuse web (UI/API) | [VERIFIED: upstream langfuse `main` docker-compose.yml] |
| `langfuse/langfuse-worker` | `3` | Langfuse async worker | [VERIFIED: upstream] |
| `clickhouse/clickhouse-server` | (upstream pins latest) | Langfuse analytics store | [VERIFIED: upstream] |
| `redis` | `7` | Langfuse queue | [VERIFIED: upstream] |
| `cgr.dev/chainguard/minio` | (upstream) | Langfuse S3/blob store | [VERIFIED: upstream] |
| `postgres` | `${POSTGRES_VERSION:-17}` | Langfuse's OWN metadata DB (separate from mesh pg) | [VERIFIED: upstream] |
| `vllm/vllm-openai` | `latest` (pin a digest/version in-plan) | local GPU OpenAI-compatible server | [CITED: docs.vllm.ai/en/stable/deployment/docker] |
| `ollama/ollama` | `latest` (pin in-plan) | local CPU model server | [CITED: ollama docker docs] |

### App image (the shared D-01 image)
The root `Dockerfile` must install the extras the three services need. From `pyproject.toml`:
- **api**: `fastapi`/`uvicorn[standard]` (core deps) + `runtime` extra (litellm, langchain-litellm, langfuse, psycopg, mcp, slack-bolt, otel) + `agents` extra (langgraph/deepagents).
- **worker**: same as api + the **docker CLI binary** (D-02 — see Finding #2) + `agents`.
- **gui**: core + `gui` extra (streamlit) + `runtime` (admin_console reads settings/repository).
- Pragmatic: install `.[runtime,agents,gui]` in the one shared image so any `command:` works (D-01 = one image). [ASSUMED — exact extra set the planner finalizes; A2]

**Installation (compose):** no `pip install` by operators — `docker compose build` builds from the root `Dockerfile`.

## Package Legitimacy Audit

> No NEW Python/npm packages are introduced by this phase. All app dependencies are already pinned/vetted in `pyproject.toml` (Phases 1–6). The only new "packages" are **container images**, audited below against their official registries.

| Image | Registry | Provenance | Disposition |
|-------|----------|-----------|-------------|
| `pgvector/pgvector:pg16` | Docker Hub | Already in use Phase 9 (`make run-pg`) | Approved (carry-forward) |
| `langfuse/langfuse:3`, `langfuse/langfuse-worker:3` | Docker Hub (`docker.io/langfuse/*`) | Official Langfuse images, named in upstream self-host compose | Approved [VERIFIED: upstream compose] |
| `clickhouse/clickhouse-server`, `redis:7`, `postgres:17` | Docker Hub official | Standard official images referenced by upstream | Approved |
| `cgr.dev/chainguard/minio` | Chainguard registry | Upstream Langfuse compose pins the Chainguard MinIO (not `minio/minio`) | Approved — keep the upstream registry path verbatim (do NOT substitute `minio/minio`; envs differ) |
| `vllm/vllm-openai:latest` | Docker Hub | Official vLLM image per docs.vllm.ai | Approved — **pin a concrete tag/digest in-plan** (`:latest` drifts) |
| `ollama/ollama:latest` | Docker Hub | Official Ollama image | Approved — **pin a concrete tag in-plan** |

**slopcheck:** N/A (no Python/npm package installs in this phase). **Recommendation:** the planner pins concrete tags for vLLM/Ollama (replace `:latest`) and may pin the Langfuse backing-service tags (clickhouse/postgres) to match the upstream-tested set; `langfuse:3` (major) is the upstream convention and is acceptable.

## Architecture Patterns

### System Architecture Diagram

```
                          make compose-up  (MODEL_PROFILE ?= vllm)
                                  │  docker compose --profile $(MODEL_PROFILE) --profile langfuse up -d
                                  ▼
  ┌─────────────────────────── docker-compose.yml (single file) ───────────────────────────┐
  │                                                                                          │
  │  CORE (always-on, no profile):                                                           │
  │     ┌────────┐   ┌──────────┐   ┌────────┐        ┌─────────────────────┐                │
  │     │  api   │   │  worker  │   │  gui   │  ─────▶ │ postgres (pgvector) │  mesh store    │
  │     │uvicorn │   │worker.main│  │streamlit│        │ pgvector/pgvector:16│                │
  │     └───┬────┘   └────┬─────┘   └────────┘        └─────────────────────┘                │
  │         │             │  (in-process litellm.Router — D-06, NO container)                │
  │         │             │  volume: /var/run/docker.sock  (DooD, dev-only — D-02)           │
  │         │             │  bind:   ./.sbxwork → /sbxwork  + TMPDIR=/sbxwork (Finding #2)    │
  │         ▼             ▼                                                                   │
  │     api_base http://vllm:8000/v1   (compose-variant model profile — Finding #1)          │
  │         │                                                                                 │
  │   ┌─────┴──────── profile: vllm ───┐   ┌──── profile: cpu ────┐                           │
  │   │  vllm (vllm/vllm-openai)       │   │ ollama (ollama/ollama)│   local model backend    │
  │   │  GPU reservation, :8000 /health│   │ CPU, :11434           │                          │
  │   └────────────────────────────────┘   └──────────────────────┘                          │
  │                                                                                           │
  │   ── profile: langfuse ── (Langfuse v3 self-host, 6 containers, its OWN backing stores) ──│
  │     langfuse-web(:3000) ─ langfuse-worker ─ lf-postgres ─ clickhouse ─ redis ─ minio      │
  │       ▲ depends_on: service_healthy (postgres, clickhouse, redis, minio)                  │
  │       │  LANGFUSE_HOST=http://langfuse-web:3000 (in-stack)                                 │
  │   api/worker telemetry ──▶ (loud-skips until UI-minted keys set — D-03a)                  │
  └──────────────────────────────────────────────────────────────────────────────────────────┘
```

### Recommended file additions (no `src/` change)
```
Dockerfile                                       # NEW — root, one shared image (D-01)
docker-compose.yml                               # NEW — single file, profile-gated
.dockerignore                                    # NEW — keep build context lean (exclude .venv, .git, tests artifacts)
config/model_gateway.vllm.compose.yaml           # NEW — api_base: http://vllm:8000/v1 (Finding #1)
config/model_gateway.cpu.compose.yaml            # NEW — api_base: http://ollama:11434 (Finding #1; name follows MODEL_PROFILE value `cpu` — A5)
tests/test_compose_config.py                     # NEW — COMPOSE-03 static validation (CI-wired, loud-skip)
Makefile                                         # EDIT — add compose-up / compose-down
RUNBOOK.md                                        # EDIT — add full-stack compose section
.env.example                                     # EDIT (if needed) — note in-stack host overrides; see wiring table
```

### Pattern 1: Compose-variant model profile mount (Finding #1 fix)
**What:** The container's active `config/model_gateway.config.yaml` is supplied by a compose-only profile whose `api_base` uses the compose service DNS name, not `localhost`.
**Why:** `build_router` loads a HARDCODED `config/model_gateway.config.yaml` (Phase-8 D-01); `api_base` is baked literal in the yaml (NOT env-driven). Inside compose `localhost` = the api/worker container itself. Keeping the Phase-8 `*.yaml` files frozen preserves host `make use-vllm`/`run-vllm` (localhost) AND Phase-11's localhost-api_base assertion.
**Example (api + worker services):**
```yaml
# Source: empirically verified — compose interpolates ${VAR} in volume SOURCE paths
volumes:
  - ./config/model_gateway.${MODEL_PROFILE:-vllm}.compose.yaml:/app/config/model_gateway.config.yaml:ro
```
```yaml
# config/model_gateway.vllm.compose.yaml — identical to model_gateway.vllm.yaml EXCEPT api_base
model_list:
  - model_name: low-complexity
    litellm_params:
      model: hosted_vllm/Qwen/Qwen2.5-7B-Instruct
      api_base: http://vllm:8000/v1        # service DNS, not localhost
  # … medium/high identical …
```
**CRITICAL filename reconciliation (verified gotcha):** `MODEL_PROFILE` values are `vllm | cpu` (D-05), but the natural file names are `vllm | ollama`. The empirical test showed `MODEL_PROFILE=cpu` resolves the source to `…model_gateway.cpu.compose.yaml`. The planner MUST resolve this mismatch, e.g.:
- (a) name the CPU compose-variant file `config/model_gateway.cpu.compose.yaml` (file name follows the profile *value*), OR
- (b) introduce a separate `MODEL_PROFILE_FILE` interpolation. **Recommend (a)** — simplest, one fewer var; the file is new this phase so no Phase-8 name is broken.

### Pattern 2: DooD sandbox via socket + identical-path bind + TMPDIR redirect (Finding #2 fix) — VERIFIED
**What:** Worker mounts the docker socket AND a host dir bound at an **identical absolute path** (source == target), with `TMPDIR` pointing the executor's tempdir into that path.
**Why:** `subprocess.run(["docker","run", "-v", f"{snippet_dir}:/snippet:ro", ...])` — with the socket mounted (DooD), the **host** daemon resolves `snippet_dir` on the host FS, NOT inside the worker container. So the executor's tempdir string must be a path that is simultaneously valid host-side with the same content. `tempfile.TemporaryDirectory(prefix=…)` passes **no `dir=`** (executor.py:137) and honors `TMPDIR` (both verified) → redirect with zero `src/` change.
**CRITICAL — the bind source and target MUST be the identical absolute string.** Empirically verified (docker 27.5.1, Docker Desktop macOS):
- Identical-path form (`-v /tmp/agent-mesh-sbx:/tmp/agent-mesh-sbx`, `TMPDIR=/tmp/agent-mesh-sbx`) → sibling container reads `snippet.py` correctly (printed `hi`).
- Mismatched form (`-v ./.sbxwork:/sbxwork`, `TMPDIR=/sbxwork`) → **FAILS LOUDLY**: `docker: Error response from daemon: Mounts denied: The path /sbxwork/foo is not shared from the host`. The executor builds `/sbxwork/agent-mesh-sbx-XXX` (a container path) and hands it to the host daemon, which has no such host path → mount denied / empty mount. This is exactly the silent-empty-mount D-02 must avoid.
**Example (worker service):**
```yaml
worker:
  command: ["python", "-m", "agent_mesh.worker.main"]
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock                              # DooD — DEV-ONLY, disclosed in RUNBOOK
    - ${MESH_SBX_DIR:-/tmp/agent-mesh-sbx}:${MESH_SBX_DIR:-/tmp/agent-mesh-sbx}  # source==target (identical path)
  environment:
    TMPDIR: ${MESH_SBX_DIR:-/tmp/agent-mesh-sbx}                              # executor tempdir lands on the shared path
  group_add:
    - "${DOCKER_GID:-999}"                                                    # non-root worker needs the socket gid (dev-only)
```
**macOS note (Docker Desktop):** the shared dir MUST sit under a Docker-Desktop file-sharing path (`/tmp`, `/private`, `/Users/...`) or the VM daemon cannot see it — another reason `/tmp/agent-mesh-sbx` is a safe default over a project-relative `./.sbxwork`.
[ASSUMED — A1: the exact `group_add`/uid for socket access is host-dependent (macOS Docker Desktop vs Linux). On Docker Desktop for Mac the socket is commonly world-accessible inside the VM; on Linux it is gid `docker`. Document both; flag as dev-only.]

### Anti-Patterns to Avoid
- **Editing the Phase-8 `model_gateway.vllm.yaml`/`.ollama.yaml` `api_base` to a service name** — breaks host `make use-vllm`/`run-vllm` (which run on localhost) AND Phase-11's localhost assertion. Use NEW `.compose.yaml` variants instead.
- **Naming a mesh-`postgres` and a Langfuse-`postgres` service identically** — see Pitfall 1. Langfuse needs its OWN postgres; collision corrupts the mesh DB or fails the bring-up.
- **A standalone `litellm` container** — explicitly rejected (D-06); would invent a topology absent from deploy.
- **Bringing the stack UP in the COMPOSE-03 test** — out of scope; the test is static `docker compose config` only.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Langfuse v3 standup | A bespoke trimmed Langfuse compose | Lift the upstream service set verbatim (6 containers, exact env) into our file under `profiles: [langfuse]` | Langfuse v3 has hard inter-service deps (clickhouse migrations, minio buckets, redis queues); a trimmed set silently breaks ingestion |
| Compose file validation | A custom YAML parser/schema | `docker compose config` (daemon-free) | It is the canonical validator; resolves interpolation, profiles, merges; verified daemon-free |
| Model routing inside compose | A litellm proxy container | The in-process `litellm.Router` already in api/worker (D-06) | A proxy diverges from deploy + needs a forbidden `src/` rewire |
| Sandbox isolation | Re-implementing the sandbox for compose | Mount the host socket + `TMPDIR` redirect; the real P2 executor runs unmodified | D-02 — the existing hardened executor is the artifact under test |

**Key insight:** This phase composes finished parts. Every temptation to "build" is actually a temptation to *re-implement* something Phases 1–9 already shipped. The only genuinely new authored artifacts are the Dockerfile, the compose file, two `.compose.yaml` model variants, two make targets, and one test.

## Runtime State Inventory

> Phase 10 authors new config/compose/docs/tests; it does not rename or migrate existing runtime state. Included for completeness.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | mesh `postgres` uses a named volume (Phase-9 `agent_mesh_pgdata` pattern); Langfuse needs its OWN volumes (lf-postgres, clickhouse, minio) | Declare distinct named volumes per store; do not share the mesh pg volume with Langfuse's pg |
| Live service config | None — no external service registration | None |
| OS-registered state | None | None |
| Secrets/env vars | NO new keys expected (`.env.example` already carries `DATABASE_URL`, `LANGFUSE_*`, `MODEL_PROVIDER_MODE`). Langfuse SERVER secrets (`NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY`, clickhouse/redis/minio creds) are NEW but dev-defaultable inline in compose, NOT mesh `.env` keys | Add Langfuse server secrets as compose-inline dev defaults (with `# CHANGEME` notes); keep mesh `LANGFUSE_PUBLIC_KEY`/`SECRET_KEY` UI-minted (D-03a) |
| Build artifacts | NEW: the shared image (`docker compose build`); the `.sbxwork` host bind dir (gitignore it) | Add `.sbxwork/` + the active `model_gateway.config.yaml` swap state to `.gitignore`/`.dockerignore` awareness |

**Nothing found** in OS-registered state or live-service-config categories — verified by inspection (no scheduler/launchd/registry touch in this phase).

## Common Pitfalls

### Pitfall 1: Langfuse's postgres vs the mesh's postgres (name + volume collision)
**What goes wrong:** Langfuse v3's upstream compose defines a `postgres` service for its OWN metadata. The mesh also needs a pgvector `postgres`. If both are named `postgres`, they collide — one definition wins, Langfuse writes to the pgvector DB (or vice-versa), corrupting state or failing migrations.
**Why it happens:** Lifting the upstream Langfuse compose verbatim brings a `postgres` service that clashes with the mesh store.
**How to avoid:** Name them distinctly — mesh store `postgres` (pgvector/pgvector:pg16, the one `DATABASE_URL` points at), Langfuse's as `langfuse-postgres` (postgres:17). Rewire Langfuse's `DATABASE_URL` env to `langfuse-postgres:5432` and give each its own named volume. The mesh DSN must point at the pgvector service ONLY.
**Warning signs:** Langfuse boot errors about missing tables; pgvector `CREATE EXTENSION vector` failing (means Langfuse's plain postgres got the mesh DSN).

### Pitfall 2: vLLM/Ollama images ship without curl → healthcheck false-fails
**What goes wrong:** A healthcheck `test: curl -f http://localhost:8000/health` fails because the image has no `curl`, marking a healthy backend `unhealthy` and blocking `depends_on: service_healthy`.
**Why it happens:** Minimal base images omit curl.
**How to avoid:** For Ollama use `["CMD-SHELL", "ollama list || exit 1"]` (ships in-image). For vLLM use a python probe (vLLM image has python): `["CMD-SHELL", "python -c \"import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)\""]`, or `wget` if present. Set `start_period: 60s`+ (model load is slow). [CITED: ollama/vllm docker docs]

### Pitfall 3: `docker compose config` does NOT validate bind-mount source existence
**What goes wrong:** COMPOSE-03 passes (file parses, services present) even when the model `api_base` points at the wrong host or the mounted profile path is wrong — because `config` is a static parse, not a runtime check.
**Why it happens:** `config` resolves interpolation/merges/profiles but does not touch the daemon or the FS for bind sources (verified).
**How to avoid:** This is BY DESIGN and consistent with scope (COMPOSE-03 is static; bring-up is operator-only). The Finding #1 fix (correct `api_base`) is what makes SC-1 actually work; COMPOSE-03 cannot and should not catch a wrong `api_base`. Document the boundary so SC-1 (works) and SC-3 (parses) are not conflated.

### Pitfall 4: `make compose-down` leaves profiled containers orphaned
**What goes wrong:** `docker compose down` without the profiles that were `up` leaves langfuse/vllm containers running.
**Why it happens:** compose down only acts on services in the active profile set.
**How to avoid:** `make compose-down` should pass `--profile "*"` (compose v2 supports the wildcard) OR enumerate all profiles: `docker compose --profile vllm --profile cpu --profile langfuse down -v`. **Recommend** the enumerated form for determinism (the wildcard's behavior across compose versions is less stable). Add `-v` only if the operator wants volumes gone (document the data-loss).

### Pitfall 5: Nobody applies the mesh-postgres migrations in the composed stack — SC-1 comes up non-functional
**What goes wrong:** `make compose-up` starts api/worker against a FRESH `postgres` service with no schema. The repo NEVER self-applies migrations (Phase-9 D-03: `_apply_migrations` is a test-only conftest fixture, `migrations/*.sql` are applied externally). The first durable-repo call (task insert) fails with "relation does not exist". COMPOSE-03 (static parse) does NOT catch this — same parses-≠-works class as Finding #1.
**Why it happens:** Phase 9 wired migrations only into the test path; the compose stack has no equivalent applier.
**How to avoid (config-only — no `src/` change):** add a one-shot `migrate` compose service that applies `migrations/0001..0004` over the mesh `postgres` and exits, with api/worker `depends_on: migrate (condition: service_completed_successfully)`. Options: (a) a tiny `pgvector/pgvector:pg16`-based service running `psql -f` over each ordered file; (b) a documented `make compose-migrate` step the RUNBOOK puts before first use. **Recommend (a)** so "one command" (SC-1) stays honest. The DDL is plain comment-free statements split on `;` (Phase-9 conftest invariant) — `psql -v ON_ERROR_STOP=1 -f` per file in lexical order works. The planner MUST add this as an explicit task; it blocks SC-1-as-functional (not SC-3).

## Code Examples

### Langfuse v3 self-host service set (lift into docker-compose.yml under `profiles: [langfuse]`)
```yaml
# Source: VERIFIED — github.com/langfuse/langfuse/blob/main/docker-compose.yml (fetched 2026-06-10)
# All six services carry `profiles: [langfuse]` so raw `docker compose up` stays lean.
  langfuse-web:
    image: docker.io/langfuse/langfuse:3
    profiles: [langfuse]
    depends_on:
      langfuse-postgres: { condition: service_healthy }
      clickhouse: { condition: service_healthy }
      redis: { condition: service_healthy }
      minio: { condition: service_healthy }
    ports: ["3000:3000"]
    environment:
      DATABASE_URL: postgresql://postgres:postgres@langfuse-postgres:5432/postgres   # CHANGEME
      NEXTAUTH_URL: http://localhost:3000
      NEXTAUTH_SECRET: mysecret                 # CHANGEME (openssl rand -hex 32)
      SALT: mysalt                              # CHANGEME
      ENCRYPTION_KEY: "0000...0000"             # 64 hex chars — openssl rand -hex 32 — CHANGEME
      CLICKHOUSE_URL: http://clickhouse:8123
      CLICKHOUSE_USER: clickhouse               # CHANGEME
      CLICKHOUSE_PASSWORD: clickhouse           # CHANGEME
      REDIS_HOST: redis
      REDIS_PORT: "6379"
      REDIS_AUTH: myredissecret                 # CHANGEME
      LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY: miniosecret   # CHANGEME
      LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY: miniosecret   # CHANGEME
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:3000/api/public/health || exit 1"]
  langfuse-worker:
    image: docker.io/langfuse/langfuse-worker:3
    profiles: [langfuse]
    depends_on: { langfuse-postgres: {condition: service_healthy}, clickhouse: {condition: service_healthy}, redis: {condition: service_healthy}, minio: {condition: service_healthy} }
    # same DATABASE_URL/CLICKHOUSE/REDIS/S3 env as langfuse-web
  langfuse-postgres:                            # RENAMED from upstream `postgres` (Pitfall 1)
    image: docker.io/postgres:17
    profiles: [langfuse]
    environment: { POSTGRES_USER: postgres, POSTGRES_PASSWORD: postgres, POSTGRES_DB: postgres }
    volumes: ["langfuse_pgdata:/var/lib/postgresql/data"]
    healthcheck: { test: ["CMD-SHELL","pg_isready -U postgres"], interval: 10s, timeout: 5s, retries: 5 }
  clickhouse:
    image: docker.io/clickhouse/clickhouse-server
    profiles: [langfuse]
    environment: { CLICKHOUSE_USER: clickhouse, CLICKHOUSE_PASSWORD: clickhouse }   # CHANGEME
    volumes: ["clickhouse_data:/var/lib/clickhouse"]
    healthcheck: { test: ["CMD-SHELL","wget -qO- http://localhost:8123/ping || exit 1"], interval: 10s, timeout: 5s, retries: 10, start_period: 30s }
  redis:
    image: docker.io/redis:7
    profiles: [langfuse]
    command: --requirepass myredissecret        # CHANGEME
    healthcheck: { test: ["CMD","redis-cli","ping"], interval: 10s, timeout: 3s, retries: 10 }
  minio:
    image: cgr.dev/chainguard/minio              # keep upstream registry verbatim
    profiles: [langfuse]
    environment: { MINIO_ROOT_USER: minio, MINIO_ROOT_PASSWORD: miniosecret }   # CHANGEME
    volumes: ["minio_data:/data"]
    healthcheck: { test: ["CMD-SHELL","mc ready local || exit 1"], interval: 10s, timeout: 5s, retries: 10 }
volumes:
  langfuse_pgdata: {}
  clickhouse_data: {}
  minio_data: {}
```
> NOTE: re-verify the exact env keys + minio/clickhouse bootstrap against the upstream `main` compose at plan time — Langfuse iterates the self-host compose. The service SET (6 containers) and the secret list (NEXTAUTH_SECRET/SALT/ENCRYPTION_KEY/clickhouse/redis/minio) are stable; individual env key spellings can drift.

### vLLM / Ollama compose service (under their profiles)
```yaml
# Source: CITED docs.vllm.ai/en/stable/deployment/docker + verified GPU-reservation syntax
  vllm:
    image: vllm/vllm-openai:latest             # pin a concrete tag in-plan
    profiles: [vllm]
    command: ["--model","Qwen/Qwen2.5-7B-Instruct","--enable-auto-tool-choice","--tool-call-parser","hermes"]
    ports: ["8000:8000"]
    ipc: host                                   # OR shm_size: "8gb" — PyTorch shared-mem (docs.vllm.ai)
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all                        # or device_ids: ['0'] — count & device_ids are mutually exclusive
              capabilities: [gpu]
    healthcheck:
      test: ["CMD-SHELL","python -c \"import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)\""]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s                        # model load is slow
  ollama:
    image: ollama/ollama:latest                 # pin a concrete tag in-plan
    profiles: [cpu]
    ports: ["11434:11434"]
    volumes: ["ollama_data:/root/.ollama"]
    healthcheck:
      test: ["CMD-SHELL","ollama list || exit 1"]   # image ships no curl (Pitfall 2)
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
```
**api_base ↔ service-DNS mapping:** the mounted compose-variant profile sets `api_base: http://vllm:8000/v1` (vLLM — MUST keep `/v1` suffix per Phase-8 comment) / `http://ollama:11434` (Ollama — no `/v1`). The Phase-8 host files keep `localhost`.
> NOTE: the Phase-8 `make run-vllm` does NOT pass `--model` as a flag the same way (`vllm serve $MODEL`). For the compose service, `--model <id>` is the first arg to the `vllm/vllm-openai` ENTRYPOINT. The `--enable-auto-tool-choice --tool-call-parser hermes` flags carry forward from Phase-8 D-08 (Qwen2.5 + hermes parser).

### COMPOSE-03 static-validation test (CI-wired, loud-skip — mirrors `pg_dsn`)
```python
# Source: empirically verified behaviors (docker 27.5.1 / compose v2.32.4)
# tests/test_compose_config.py — default lane (collected under `make test`), loud-skips when docker absent.
import shutil
import subprocess
import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("docker") is None,
    reason="docker binary absent; compose-config validation requires the docker CLI",
)

def _config(*profiles: str) -> str:
    args = ["docker", "compose"]
    for p in profiles:
        args += ["--profile", p]
    args += ["config"]
    # daemon-free: `docker compose config` is a pure client-side parse (verified)
    return subprocess.run(args, capture_output=True, text=True, check=True, cwd=".").stdout

def test_compose_parses_and_core_services_present():
    out = _config()                                   # bare: only non-profiled core
    services = subprocess.run(["docker","compose","config","--services"],
                              capture_output=True, text=True, check=True).stdout.split()
    assert {"api", "worker", "gui", "postgres"} <= set(services)
    # D-06: NO standalone litellm container by design
    assert "litellm" not in services

def test_pgvector_image_present():
    assert "pgvector/pgvector:pg16" in _config()

def test_profiled_services_appear_when_profile_named():
    # profiled services appear in `config --services` ONLY when --profile passed (verified)
    svc = subprocess.run(["docker","compose","--profile","vllm","--profile","langfuse",
                          "config","--services"], capture_output=True, text=True, check=True).stdout.split()
    assert {"vllm", "langfuse-web"} <= set(svc)

def test_required_healthchecks_present():
    out = _config("vllm", "langfuse", "cpu")
    # assert healthcheck blocks exist for the services that must carry them
    assert out.count("healthcheck:") >= 4          # postgres, api, langfuse-web, model backend (planner sets exact set)
```
**Why this shape:** `pytestmark skipif(which("docker") is None)` is the loud-skip (mirrors `pg_dsn`'s `pytest.skip`); `docker compose config` is daemon-free so it is safe to CI-wire; profiled-service assertions pass the profile name (L2); the `pgvector/pgvector:pg16` string-grep is the image assertion (verified greppable in rendered config).

> **Daemon-free with `build:` services:** the empirical verification used `image:` stub services, but the real file uses `build: .` for api/worker/gui. `docker compose config` does NOT build images (it only resolves/merges/interpolates and prints), so it stays daemon-free even with `build:` services — the "CI-wired" claim holds. It also does NOT validate that bind-mount source paths exist (Pitfall 3), so a wrong `api_base` or missing mounted profile won't be caught — consistent with COMPOSE-03's static scope.

## Inter-service DNS / env wiring table

| Setting | Host-operator value (Phase 9) | In-stack (compose) value | Mechanism | Notes |
|---------|-------------------------------|--------------------------|-----------|-------|
| `DATABASE_URL` (mesh) | `postgresql://postgres:postgres@localhost:5432/agent_mesh` | `postgresql://postgres:postgres@postgres:5432/agent_mesh` | compose `environment:` override (env-driven via settings.py) | creds/port/db IDENTICAL — only host `localhost`→`postgres` |
| `LANGFUSE_HOST` (mesh) | `http://localhost:3000` | `http://langfuse-web:3000` | compose `environment:` override (env-driven) | port identical; host→service name |
| `LANGFUSE_PUBLIC_KEY` / `SECRET_KEY` | blank (UI-minted) | blank until UI-minted (D-03a) | operator sets in `.env` after first boot | tracing loud-skips until set |
| model `api_base` | `http://localhost:8000/v1` (vLLM) / `http://localhost:11434` (Ollama) | `http://vllm:8000/v1` / `http://ollama:11434` | **NOT env-driven** — mounted `.compose.yaml` profile variant (Finding #1) | the ONE non-env-override row |
| Langfuse server `DATABASE_URL` | n/a (no Langfuse in P9) | `postgresql://postgres:postgres@langfuse-postgres:5432/postgres` | compose-inline (Langfuse's OWN pg) | distinct from mesh DSN (Pitfall 1) |
| `TMPDIR` (worker) | unset (host tempdir) | `/sbxwork` (shared host bind) | compose `environment:` + bind (Finding #2) | enables DooD sandbox path-match |

## State of the Art

| Old Approach | Current Approach | When | Impact |
|--------------|------------------|------|--------|
| Langfuse v2 single-container self-host | Langfuse **v3** multi-container (web+worker+clickhouse+redis+minio+postgres) | v3 GA (2024–2025) | D-03 correctly targets v3; a single-container assumption would be wrong. **v3 is current** as of 2026-06; no v4 self-host migration observed — if the planner sees a `langfuse:4` tag at plan time, re-verify but do not re-litigate the locked v3 decision without surfacing it. |
| Compose `--gpus all` (CLI) | `deploy.resources.reservations.devices` (compose file) | compose v2 | vLLM GPU reservation must use the file syntax, not the CLI flag |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Worker socket access uses `group_add: ${DOCKER_GID}`; exact gid/uid is host-dependent (Docker Desktop Mac vs Linux) | Pattern 2 | Sandbox `docker run` permission-denied at runtime; dev-only, documented — not a CI failure |
| A2 | The shared image installs `.[runtime,agents,gui]` so any `command:` works | Standard Stack | If an import path needs an extra not installed, that service fails to boot; planner finalizes the exact extra set against actual imports |
| A3 | vLLM `/health` returns 200 when ready (used in healthcheck) | Code Examples | A wrong probe false-fails the healthcheck; `/v1/models` is the documented fallback |
| A4 | Exact Langfuse env-key spellings (e.g. `LANGFUSE_S3_*`) match the current upstream compose | Langfuse block | Langfuse boots misconfigured; mitigated by the "re-verify at plan time" note — service SET + secret list are stable |
| A5 | The CPU compose-variant file is named `model_gateway.cpu.compose.yaml` (follows `MODEL_PROFILE` value `cpu`, not `ollama`) | Pattern 1 | If named `.ollama.compose.yaml`, the `${MODEL_PROFILE}` interpolation resolves to a non-existent file → mount fails; **planner MUST pick one convention** |

## Open Questions (RESOLVED)

1. **Exact set of services carrying healthchecks (discretion item).**
   - What we know: COMPOSE-03 asserts healthchecks are *present*; pragmatic probes exist for postgres (`pg_isready`), api (`/health` — FastAPI app exposes it per E2E tests), langfuse-web (`/api/public/health`), model backend (vLLM `/health`, Ollama `ollama list`).
   - What's unclear: whether gui/worker also carry healthchecks.
   - Recommendation: healthcheck postgres + api + langfuse-web + the model backend (4); the COMPOSE-03 test asserts `>= 4` healthcheck blocks. Worker/gui optional.

2. **`make compose-down` profile scope (discretion item).**
   - Recommendation: enumerate `--profile vllm --profile cpu --profile langfuse down` (deterministic across compose versions; avoid `--profile "*"` instability). Leave volumes by default; document `-v` for a clean wipe.

3. **Exact COMPOSE-03 assertion shape (discretion item).**
   - Recommendation: assert (a) bare config parses; (b) core `{api,worker,gui,postgres}` present + `litellm` absent; (c) `pgvector/pgvector:pg16` string present; (d) `>=4` healthchecks; (e) profiled `{vllm,langfuse-web}` appear with profiles named. Loud-skip on absent docker. (Recipe above.)

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| docker CLI | COMPOSE-03 test, bring-up | ✓ | 27.5.1 | test loud-skips when absent |
| docker compose v2 | bring-up, `docker compose config` | ✓ | v2.32.4 | none (the validator) |
| NVIDIA GPU + runtime | vLLM default profile | ✗ (this dev box) | — | `MODEL_PROFILE=cpu` → Ollama (D-05 documents this) |
| `tempfile` TMPDIR honoring | Finding #2 DooD fix | ✓ (verified) | — | none needed |

**Missing dependencies with fallback:** GPU absent → CPU/Ollama via `MODEL_PROFILE=cpu` (locked D-05). No blocking absences.

## Validation Architecture

> nyquist_validation not explicitly false → section included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x (`pyproject.toml` `[tool.pytest.ini_options]`, pythonpath=`src`) |
| Config file | `pyproject.toml` |
| Quick run command | `make test` (`pytest -q -m "not live"`) |
| Full suite command | `make test` (+ `make test-pg` for the DSN lane) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| COMPOSE-01 | compose file declares the required service set | static (covered by COMPOSE-03) | `pytest tests/test_compose_config.py` | ❌ Wave 0 |
| COMPOSE-02 | make targets exist / RUNBOOK documents bring-up | doc/lint (no automated assert beyond presence) | manual + `make -n compose-up` | n/a |
| COMPOSE-03 | `docker compose config` parses; services + healthchecks + pgvector image present; loud-skip | unit (CI-wired, default lane) | `pytest tests/test_compose_config.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `make test` (includes the new compose-config test; loud-skips if docker absent)
- **Per wave merge:** `make test`
- **Phase gate:** `make test` green + (operator) one real `make compose-up` bring-up sanity before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_compose_config.py` — covers COMPOSE-03 (the only CI-wired artifact). No new conftest fixture needed (reuses `shutil.which` loud-skip pattern inline).
- [ ] **One-shot `migrate` compose service** (Pitfall 5) — applies `migrations/0001..0004` over the mesh `postgres` before api/worker start; without it SC-1 comes up schema-less. NOT a test file — a compose service the planner must add as an explicit task.

## Security Domain

> The milestone guardrail is config/compose/docs/tests-only; this phase introduces no new code paths. Security notes are about the compose posture.

### Applicable controls
| Concern | Applies | Control |
|---------|---------|---------|
| Privileged docker-socket mount (D-02) | yes | RUNBOOK MUST disclose `/var/run/docker.sock` as DEV-ONLY (grants the worker effective host-root). Not a production posture; production uses Cloud Run Jobs. |
| Dev-default Langfuse secrets | yes | `NEXTAUTH_SECRET`/`SALT`/`ENCRYPTION_KEY`/clickhouse/minio creds are `# CHANGEME` dev defaults inline; RUNBOOK notes they are local-only and must be replaced for any non-local use |
| Egress posture | deferred | Phase 11 (OFFLINE) asserts no cloud `api_base`/keys — Finding #1's `.compose.yaml` variants stay loopback-service-only (no cloud URL), keeping that assertion clean |

### Known threat patterns
| Pattern | STRIDE | Mitigation |
|---------|--------|------------|
| Socket mount = host-root escalation | Elevation of Privilege | dev-only disclosure; never in the deploy path (Cloud Run Job sandbox is the prod equivalent) |
| Default secrets shipped in compose | Information Disclosure | `# CHANGEME` markers + RUNBOOK "dev-only local creds" disclosure (mirrors Phase-9 DSN handling) |

## BLOCKERS

**None.** Both load-bearing risks have verified config-only fixes:
- Finding #1 (model `api_base` not env-driven) → NEW `.compose.yaml` profile variants mounted via `${MODEL_PROFILE}` interpolation (verified). No `src/` change.
- Finding #2 (DooD sandbox path translation) → host bind + `TMPDIR` redirect; executor passes no `dir=` and honors `TMPDIR` (both verified). No `src/` change.

If the planner concludes Finding #1's mounted-variant approach is undesirable, the ONLY alternative reaching a working SC-1 would be an env-driven config-path seam in `build_router` — which is a **forbidden `src/` change** (explicitly deferred in Phase-8 Deferred Ideas). Surface as a blocker rather than make that edit.

**Migration gap (Pitfall 5) is planned work, NOT a blocker:** it has a config-only fix (a one-shot `migrate` compose service). It blocks SC-1-as-functional but not SC-3 (`docker compose config` won't notice). The planner must add it as an explicit task so it is not a bring-up surprise.

## Open discretion items + recommended defaults

| Item | Recommended default |
|------|---------------------|
| Healthchecked services | postgres (`pg_isready`), api (`/health`), langfuse-web (`/api/public/health`), model backend (vLLM `/health` python-probe; Ollama `ollama list`) — 4 total |
| `compose-down` scope | enumerated `--profile vllm --profile cpu --profile langfuse down` (no `-v` by default) |
| COMPOSE-03 assertions | parse + core-services-present + `litellm`-absent + `pgvector/pgvector:pg16`-string + `>=4` healthchecks + profiled-services-when-named; loud-skip on absent docker |
| CPU compose-variant filename | `config/model_gateway.cpu.compose.yaml` (follow `MODEL_PROFILE` value `cpu`, not `ollama`) — A5 |
| Shared-image extras | `.[runtime,agents,gui]` (planner confirms against imports) — A2 |
| vLLM/Ollama tags | pin concrete tags (replace `:latest`) at plan time |
| mesh-DB migration applier | one-shot `migrate` compose service (psql `-v ON_ERROR_STOP=1 -f` over ordered `migrations/*.sql`), api/worker `depends_on: service_completed_successfully` (Pitfall 5) |
| sandbox shared dir | `${MESH_SBX_DIR:-/tmp/agent-mesh-sbx}` bound source==target + `TMPDIR` (Finding #2); `/tmp` is Docker-Desktop-shared on macOS |

## Sources

### Primary (HIGH confidence)
- **Codebase (VERIFIED):** `src/agent_mesh/sandbox/executor.py` (D-02 evidence: `subprocess.run(["docker",...])`, `shutil.which("docker")`, `-v {snippet_dir}:/snippet:ro`, no `dir=` at L137), `config/model_gateway.vllm.yaml`/`.ollama.yaml` (api_base shapes), `Makefile` (P8/P9 patterns), `tests/conftest.py` (`pg_dsn` loud-skip), `tests/test_local_data_plane.py` (DSN-gated test pattern), `pyproject.toml` (extras; no `import docker`), `scripts/gcp_deploy_core.sh` (image-name parity), `.env.example`/RUNBOOK (Phase-9 wiring).
- **Empirical (VERIFIED on docker 27.5.1 / compose v2.32.4):** `docker compose config` is daemon-free; `${MODEL_PROFILE}` interpolates in volume SOURCE paths; profiled services appear in `config --services` only when `--profile` passed; `pgvector/pgvector:pg16` greppable in rendered config; `MODEL_PROFILE=cpu` resolves to `…cpu.compose.yaml` (filename gotcha); `tempfile.TemporaryDirectory` honors `TMPDIR`.
- **Langfuse upstream (VERIFIED):** github.com/langfuse/langfuse `main` `docker-compose.yml` — 6-service set + image tags + secret list.

### Secondary (MEDIUM confidence)
- [CITED: docs.vllm.ai/en/stable/deployment/docker] — vLLM image `vllm/vllm-openai:latest`, port 8000, `--ipc=host`/`--shm-size` requirement.
- [docs.vllm.ai GPU] — `deploy.resources.reservations.devices` (nvidia driver, count/device_ids mutually exclusive, capabilities [gpu]).
- Ollama docker docs (WebSearch, multiple sources agree) — image `ollama/ollama`, port 11434, `ollama list` healthcheck (no curl in image), `start_period: 60s`.

### Tertiary (LOW confidence — flagged for plan-time re-verify)
- Exact Langfuse env-key spellings (`LANGFUSE_S3_*`, clickhouse bootstrap) — re-verify against upstream `main` at plan time (A4).
- vLLM `/health` 200-on-ready (A3) — confirm against the pinned vLLM tag.

## Metadata

**Confidence breakdown:**
- Compose behaviors (parse/profile/interpolation/image-grep): HIGH — empirically verified locally.
- D-02 verdict (docker CLI not SDK; DooD identical-path + TMPDIR fix): HIGH — source + empirical (identical-path proven, mismatched-path proven to fail).
- In-stack migration gap (Pitfall 5) + one-shot migrate-service fix: HIGH — Phase-9 D-03 confirms repo never self-applies; fix is standard psql-over-DDL.
- Finding #1 (model api_base mount fix): HIGH — verified interpolation + source-confirmed hardcoded path.
- Langfuse v3 service set: HIGH (set/secrets) / MEDIUM (exact env spellings — re-verify).
- vLLM/Ollama service shapes: MEDIUM — official docs + multi-source agreement; tags need pinning.

**Research date:** 2026-06-10
**Valid until:** 2026-07-10 (compose/docker behavior stable; Langfuse self-host compose iterates — re-verify the Langfuse block if planning slips past ~2 weeks)

## RESEARCH COMPLETE
