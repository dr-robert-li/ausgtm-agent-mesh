# Phase 10: Full-Stack Local Compose - Pattern Map

**Mapped:** 2026-06-10
**Files analyzed:** 9 authored artifacts (7 NEW, 2 MODIFY) + 1 in-file `migrate` service
**Analogs found:** 7 with a real repo analog / 9 (Dockerfile, .dockerignore, and the Langfuse v3 block are net-new — no repo analog)

> **Guardrail (whole v1.1 milestone):** config / docker-compose / docs / tests **ONLY**.
> **Zero `src/` production-code change.** Every `src/` path below is a READ-ONLY
> reference/analog — never a modification target. Assert `git diff <base>..HEAD -- src/`
> empty as a phase invariant (same as P8/P9).

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `Dockerfile` (NEW) | config / build artifact | batch (image build) | none (net-new) — informed by `pyproject.toml` extras + `scripts/gcp_deploy_core.sh:16-18` image names | no-analog |
| `.dockerignore` (NEW) | config | n/a | none (net-new) — informed by `.gitignore` exclusions | no-analog |
| `docker-compose.yml` (NEW) | config / orchestration | event-driven (service graph) | piece-by-piece: `postgres`→`Makefile run-pg:112-116`; model svcs→RESEARCH vLLM/Ollama blocks; Langfuse block→RESEARCH upstream lift | composite (see below) |
| `config/model_gateway.vllm.compose.yaml` (NEW) | config | request-response (routing profile) | `config/model_gateway.vllm.yaml` (identical EXCEPT `api_base` host) | exact |
| `config/model_gateway.cpu.compose.yaml` (NEW) | config | request-response (routing profile) | `config/model_gateway.ollama.yaml` (identical EXCEPT `api_base` host; **renamed** `ollama`→`cpu` per A5) | exact |
| `migrate` service (inside `docker-compose.yml`, NEW) | config / one-shot job | batch (DDL apply) | `tests/conftest.py:_apply_migrations` (file list + 0001→0004 order) — **mechanism is NEW** (`psql -f`, not psycopg) | role-match (mechanism differs) |
| `tests/test_compose_config.py` (NEW) | test | transform (static parse assertions) | `tests/conftest.py:75-88` (`pg_dsn` loud-skip principle) + `tests/test_local_data_plane.py` (DSN-gated test file shape) | role-match (skip shape differs — see note) |
| `Makefile` (MODIFY) | config / operator targets | request-response | `run-api:63-64`/`run-worker:66-67`/`run-gui:69-70` (command strings) + `run-pg:112-116`/`use-*:92-97` (best-effort loud-skip style) | exact |
| `RUNBOOK.md` (MODIFY) | docs | n/a | `## Local inference lane` (P8, ~L96) + `## Local data & telemetry plane` (P9, ~L184), incl. the Langfuse doc-only block (~L219-245) | exact |
| `.env.example` (MODIFY-or-confirm) | config | n/a | existing `DATABASE_URL`/`LANGFUSE_*`/`MODEL_GATEWAY_BASE_URL`/`MODEL_PROVIDER_MODE` keys | confirm-no-change |

---

## Pattern Assignments

### `Makefile` — `compose-up` / `compose-down` targets (MODIFY)

**Analog (command strings — the three services run the SAME commands as the make run-* targets):** `Makefile:63-70`
```makefile
run-api:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m uvicorn agent_mesh.api.app:app --reload --port 8080
run-worker:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m agent_mesh.worker.main
run-gui:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m streamlit run src/agent_mesh/gui/admin_app.py
```
→ In-compose `command:` strings (D-01, no `--reload`, container port 8080):
`uvicorn agent_mesh.api.app:app --port 8080` / `python -m agent_mesh.worker.main` /
`streamlit run src/agent_mesh/gui/admin_app.py`. **L3:** entry is `admin_app.py`, NOT `admin_console.py`.

**Analog (best-effort, env-switched, operator-only target style — the P8/P9 pattern to mirror):** `Makefile:80-97, 109-116`
```makefile
VLLM_MODEL ?= Qwen/Qwen2.5-7B-Instruct     # env-default override pattern (use for MODEL_PROFILE ?= vllm)
...
PG_IMAGE     ?= pgvector/pgvector:pg16      # pinned image as a make var
use-vllm:
	cp config/model_gateway.vllm.yaml config/model_gateway.config.yaml   # one-line operator action
```

**Target shape to author (D-05, discretion items resolved by RESEARCH defaults):**
```makefile
MODEL_PROFILE ?= vllm                        # values: vllm | cpu  (D-05; cpu => Ollama)
compose-up:
	docker compose --profile $(MODEL_PROFILE) --profile langfuse up -d --build
compose-down:
	docker compose --profile vllm --profile cpu --profile langfuse down   # enumerated (Pitfall 4); no -v by default
```
- Add both to `.PHONY` (line 1) and the `help:` block (lines 6-25), mirroring every existing target's help line.
- **Best-effort / never-CI:** like `run-pg`/`run-vllm`, these require docker and may fail on a bare box — acceptable, documented in RUNBOOK. They are NOT wired into `make test`. The ONLY CI-wired Phase-10 piece is `tests/test_compose_config.py`.

---

### `tests/test_compose_config.py` (NEW — the ONLY CI-wired artifact, COMPOSE-03)

**Analog (loud-skip-when-dep-absent PRINCIPLE):** `tests/conftest.py:75-88`
```python
@pytest.fixture
def pg_dsn() -> str:
    dsn = os.getenv("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL unset; SQL-backed tests require a local Postgres")
    ...
```

**Analog (DSN-gated test FILE shape — collects under `make test`, skips cleanly):** `tests/test_local_data_plane.py:1-25` (module docstring states "collects under plain `make test` and skips cleanly there"; imports the heavy dep — `psycopg` — INSIDE the test body, not at module scope).

**CRITICAL — the skip SHAPE differs from `pg_dsn` (do not copy verbatim):**
The COMPOSE-03 test gates on the **docker binary**, not a DSN env var, and does it at **module level** so the whole file skips before any `docker compose` subprocess runs:
```python
import shutil, subprocess, pytest
pytestmark = pytest.mark.skipif(
    shutil.which("docker") is None,
    reason="docker binary absent; compose-config validation requires the docker CLI",
)
```
Same loud-skip principle as `pg_dsn`; different mechanism (`pytest.mark.skipif` module-level vs fixture-internal `pytest.skip`). The `shutil.which("docker")` probe mirrors the executor's own gate (`src/agent_mesh/sandbox/executor.py:131`).

**Assertions to author (RESEARCH §"COMPOSE-03 static-validation test" + Open-Q defaults):**
1. bare `docker compose config` parses (daemon-free even with `build:` services).
2. `docker compose config --services` ⊇ `{api, worker, gui, postgres}` AND `"litellm" not in services` (D-06).
3. `"pgvector/pgvector:pg16"` string present in rendered config.
4. `>= 4` `healthcheck:` blocks (postgres, api, langfuse-web, model backend — the 4 healthchecked services).
5. profiled `{vllm, langfuse-web}` appear ONLY when `--profile vllm --profile langfuse` named (L2).

**Scope boundary (Pitfall 3):** `docker compose config` does NOT validate bind-source existence or `api_base` correctness — by design. COMPOSE-03 proves the file *parses + declares the set*; it does NOT prove the stack *works*. The Finding #1/#2 fixes (Shared Patterns) are what make SC-1 actually work; the test cannot and must not catch a wrong `api_base`.

---

### `config/model_gateway.vllm.compose.yaml` (NEW, Finding #1)

**Analog:** `config/model_gateway.vllm.yaml` (whole file). The compose-variant is **byte-identical EXCEPT the three `api_base` values**: `http://localhost:8000/v1` → `http://vllm:8000/v1` (service DNS). Keep the `/v1` suffix (file comment lines 8-11 explain why: LiteLLM `hosted_vllm` appends only `chat/completions`). Keep the frozen deployment names `low/medium/high-complexity`, the fallbacks, `litellm_settings`, and the inert `general_settings` verbatim.

```yaml
  - model_name: low-complexity
    litellm_params:
      model: hosted_vllm/Qwen/Qwen2.5-7B-Instruct
      api_base: http://vllm:8000/v1        # ← ONLY change vs vllm.yaml (was localhost)
```

**Why a NEW file, not an edit (Anti-Pattern):** editing `vllm.yaml`'s `api_base` to a service name breaks host `make use-vllm`/`run-vllm` (loopback) AND Phase-11's localhost-`api_base` assertion. Keep the Phase-8 files frozen.

---

### `config/model_gateway.cpu.compose.yaml` (NEW, Finding #1 + A5 gotcha)

**Analog:** `config/model_gateway.ollama.yaml` (whole file). Byte-identical EXCEPT `api_base`: `http://localhost:11434` → `http://ollama:11434` (service DNS, **no `/v1`** for Ollama — see ollama.yaml comment lines 9-11). Keep `ollama_chat/` prefix, frozen names, fallbacks, settings verbatim.

**A5 FILENAME GOTCHA (load-bearing):** the file is named `…cpu.compose.yaml`, NOT `…ollama.compose.yaml`. The compose volume source interpolates `${MODEL_PROFILE}` and `MODEL_PROFILE` values are `vllm | cpu` (D-05). `MODEL_PROFILE=cpu` resolves the source to `…model_gateway.cpu.compose.yaml`. Naming it `.ollama.compose.yaml` → the interpolation points at a non-existent file → silent/failed mount. The file is new this phase, so following the profile *value* (`cpu`) breaks no Phase-8 name.

---

### `docker-compose.yml` (NEW — composite; map piece-by-piece, NOT as one analog)

| Compose piece | Analog / source | Note |
|---------------|-----------------|------|
| `api` / `worker` / `gui` services | `build: .` (the new Dockerfile) + `command:` from `Makefile:63-70` | D-01 one image, command-parameterized |
| `postgres` (mesh store) | `Makefile run-pg:112-116` | `pgvector/pgvector:pg16`; `POSTGRES_USER/PASSWORD/DB=postgres/postgres/agent_mesh`; named volume; in-stack DSN host `@postgres:5432` |
| `vllm` / `ollama` services | RESEARCH §"vLLM / Ollama compose service" | `profiles: [vllm]` / `profiles: [cpu]`; pin concrete tags; GPU `deploy.resources.reservations.devices`; Pitfall-2 healthchecks |
| Langfuse v3 block (6 svc) | RESEARCH §"Langfuse v3 self-host service set" (upstream lift) | **NO repo analog** — see No-Analog section; all `profiles: [langfuse]`; Langfuse pg RENAMED `langfuse-postgres` (Pitfall 1) |
| `migrate` one-shot service | `tests/conftest.py:_apply_migrations` (file list + order ONLY) | mechanism NEW — see below |

**Postgres analog excerpt** (`Makefile:112-116`) the compose `postgres` service must match for DSN parity:
```makefile
run-pg:
	docker run -d --name $(PG_CONTAINER) \
	  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=agent_mesh \
	  -p 5432:5432 -v $(PG_VOLUME):/var/lib/postgresql/data \
	  $(PG_IMAGE)        # pgvector/pgvector:pg16
```

**Inter-service env overrides (RESEARCH wiring table — the env-driven rows):**
- `DATABASE_URL`: `postgresql://postgres:postgres@postgres:5432/agent_mesh` (creds/port/db identical to Phase-9 default; host `localhost`→`postgres`).
- `LANGFUSE_HOST`: `http://langfuse-web:3000` (host→service name; port identical).
- `LANGFUSE_PUBLIC_KEY`/`SECRET_KEY`: blank until UI-minted (D-03a) — tracing loud-skips.
- Distinct named volumes per store: mesh `postgres`, `langfuse_pgdata`, `clickhouse_data`, `minio_data`, `ollama_data` (do NOT share the mesh pg volume with Langfuse — Pitfall 1).

---

### `migrate` one-shot service (inside `docker-compose.yml`, NEW — Pitfall 5, load-bearing)

**Analog (WHAT to apply + order):** `tests/conftest.py:_apply_migrations` (invoked at `conftest.py:86`) — applies `migrations/0001..0004` in lexical order. The P9 fixture is the proof the repo NEVER self-applies migrations outside the test path.

**Mechanism is NEW (do not copy the python applier):** conftest uses psycopg with comment-stripping + split-on-`;`. The compose `migrate` service uses a `pgvector/pgvector:pg16`-based one-shot running `psql -v ON_ERROR_STOP=1 -f` over each ordered `migrations/*.sql`, then exits. api/worker/gui declare `depends_on: { migrate: { condition: service_completed_successfully } }`.

**Why it is mandatory (planner action item):** without it, `make compose-up` brings api/worker up against a schema-less DB and the first durable call fails (`relation does not exist`). `docker compose config` (COMPOSE-03 static parse) will NOT catch its absence — same "parses ≠ works" class as Finding #1. This blocks SC-1-as-functional, not SC-3. The planner MUST author it as an explicit task.

---

### `RUNBOOK.md` — full-stack compose section (MODIFY)

**Analog (section style + honest-disclosure tone):** `RUNBOOK.md:96-182` (`## Local inference lane`, P8) and `RUNBOOK.md:184-245` (`## Local data & telemetry plane`, P9). Add the new `## Full-stack local compose` section AFTER these and reconcile with the P9 Langfuse doc-only block (~L219-245), which explicitly defers the multi-container standup "to Phase 10's compose".

**Reuse the P9 dev-only-creds disclosure tone** (`RUNBOOK.md:186-191`):
> "...the run-targets are best-effort operator steps and the pinned `.env.example` DSNs are **dev-only** local creds — copy `.env.example` to an untracked `.env` and replace them for any real deployment..."

**Mandatory disclosures the new section MUST carry (D-02/D-03a/D-04/D-06 + Security domain):**
- **docker-socket mount is DEV-ONLY** (`/var/run/docker.sock` grants the worker effective host-root; production uses Cloud Run Jobs). — D-02
- **Langfuse keys are UI-minted** → tracing loud-skips on first bring-up until a human mints keys + sets `LANGFUSE_PUBLIC_KEY`/`SECRET_KEY`; carries forward the existing P9 client-vs-server key boundary note (`RUNBOOK.md:235-245`). — D-03a
- **vLLM is the default and needs a GPU**; non-GPU operators run `MODEL_PROFILE=cpu make compose-up` (Ollama). — D-04/D-05
- **LiteLLM runs EMBEDDED in api/worker, not as a proxy container** — mirrors deploy (no litellm image); COMPOSE-03's required-services list omits a litellm container by design. — D-06
- **Langfuse server `# CHANGEME` secrets** (`NEXTAUTH_SECRET`/`SALT`/`ENCRYPTION_KEY`/clickhouse/minio) are local-only dev defaults; replace for any non-local use.

---

### `.env.example` (MODIFY-or-confirm-no-change)

**Analog:** itself — already carries `DATABASE_URL`, `LANGFUSE_*`, `MODEL_GATEWAY_BASE_URL`, `MODEL_PROVIDER_MODE`. RESEARCH: **no new mesh keys expected**; compose env wiring overrides these inline (`DATABASE_URL`→`@postgres`, `LANGFUSE_HOST`→`@langfuse-web`). At most add a comment noting in-stack host overrides. Langfuse SERVER secrets and `MESH_SBX_DIR`/`DOCKER_GID`/`TMPDIR` live compose-inline (with `# CHANGEME`), NOT as mesh `.env` keys. **Default action: confirm-no-change**; only add explanatory comments if the planner deems it clearer.

---

## Shared Patterns

> These two are **cross-cutting** — they must be threaded into the compose-file
> tasks, not buried under the test. Both are the "parses ≠ works" gaps a static
> `docker compose config` cannot catch; under-weighting them yields a green
> COMPOSE-03 over a non-functional SC-1.

### Finding #1 — model `api_base` is NOT env-driven (mounted compose-variant profile)
**Source:** `config/model_gateway.vllm.yaml`/`.ollama.yaml` (api_base baked literal) + `src/agent_mesh/worker/model_gateway.py:build_router` (loads a HARDCODED `config/model_gateway.config.yaml`).
**Apply to:** the `api` AND `worker` services in `docker-compose.yml`.
```yaml
# ${MODEL_PROFILE} interpolates in volume SOURCE paths (empirically verified)
volumes:
  - ./config/model_gateway.${MODEL_PROFILE:-vllm}.compose.yaml:/app/config/model_gateway.config.yaml:ro
```
Inside compose `localhost` = the api/worker container itself → completions break unless the mounted profile's `api_base` is the backend service DNS (`vllm`/`ollama`). The two `.compose.yaml` variants (above) supply that. **No `src/` change** — the only alternative (an env-driven config-path seam in `build_router`) is a forbidden `src/` edit; surface as a blocker rather than make it.

### Finding #2 — DooD sandbox via socket + identical-path bind + `TMPDIR` (D-02)
**Source:** `src/agent_mesh/sandbox/executor.py` — `subprocess.run(["docker", ...])` (no python docker SDK; image needs the **docker CLI binary**), `shutil.which("docker")` gate (`:131`), `-v {snippet_dir}:/snippet:ro` (`:93`), `tempfile.TemporaryDirectory(prefix=...)` with **no `dir=`** (`:137`, honors `TMPDIR`).
**Apply to:** the `worker` service in `docker-compose.yml`.
```yaml
worker:
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock                                   # DooD — DEV-ONLY (RUNBOOK discloses)
    - ${MESH_SBX_DIR:-/tmp/agent-mesh-sbx}:${MESH_SBX_DIR:-/tmp/agent-mesh-sbx}   # source==target (IDENTICAL absolute path)
  environment:
    TMPDIR: ${MESH_SBX_DIR:-/tmp/agent-mesh-sbx}                                  # executor tempdir lands on the shared path
  group_add:
    - "${DOCKER_GID:-999}"                                                        # non-root socket gid (host-dependent; dev-only, A1)
```
**Load-bearing:** the bind source and target MUST be the IDENTICAL absolute string. With the socket mounted, the HOST daemon resolves `snippet_dir`; a mismatched bind (`./.sbxwork:/sbxwork`) fails loudly ("Mounts denied"). `/tmp/...` is a Docker-Desktop-shared path on macOS. **No `src/` change** — the real P2 executor runs unmodified.

### Best-effort / loud-skip / honest-disclosure (P8/P9 invariant)
**Source:** `Makefile:72-116` (run-* targets "best-effort, operator-run, DELIBERATELY never wired into `test`") + `RUNBOOK.md:96-245` honest-disclosure sections.
**Apply to:** `make compose-up`/`compose-down` (best-effort, never-CI) and every RUNBOOK disclosure. The compose-config test is the lone CI-wired piece and stays static (no bring-up).

### Zero-`src/`-change invariant (P8/P9 carry-forward)
**Apply to:** the whole phase. Assert `git diff <base>..HEAD -- src/` is empty as a phase gate (same invariant P8/P9 enforced).

---

## No Analog Found

Files with no close match in the codebase (planner uses RESEARCH lift-ready blocks + pyproject extras + deploy image names instead):

| File | Role | Source the planner uses instead | Reason |
|------|------|--------------------------------|--------|
| `Dockerfile` | config / build | `pyproject.toml` extras → install `.[runtime,agents,gui]` (A2; planner confirms vs imports); worker needs the **docker CLI binary** (Finding #2); `scripts/gcp_deploy_core.sh:16-18` for image-name parity (`agent-mesh-api`/`-worker`) | Repo has never had a Dockerfile; first real app image this milestone (L1) |
| `.dockerignore` | config | `.gitignore` exclusions as a starting list (exclude `.venv`, `.git`, test artifacts, `.sbxwork/`, the active `model_gateway.config.yaml` swap state) | Net-new; keeps build context lean |
| Langfuse v3 block (6 svc inside `docker-compose.yml`) | config | RESEARCH §"Langfuse v3 self-host service set" — verbatim upstream lift (web + worker + langfuse-postgres + clickhouse + redis + minio); **re-verify env-key spellings vs upstream `main` at plan time** (A4) | No Langfuse in the repo today (P9 deferred standup to P10); hard inter-service deps — do not hand-roll a trimmed set |

---

## Metadata

**Analog search scope:** `Makefile`, `config/model_gateway.{vllm,ollama}.yaml`, `tests/conftest.py`, `tests/test_local_data_plane.py`, `RUNBOOK.md`, `pyproject.toml`, `src/agent_mesh/sandbox/executor.py` (read-only DooD evidence), `scripts/gcp_deploy_core.sh` (image-name parity, per CONTEXT).
**Files scanned:** 8 analog sources read; 0 existing compose/Dockerfile artifacts (all NEW confirmed).
**Pattern extraction date:** 2026-06-10
