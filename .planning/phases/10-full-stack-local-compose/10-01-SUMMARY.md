---
phase: 10-full-stack-local-compose
plan: 01
subsystem: build-artifacts + model-profiles
tags: [docker, dockerfile, compose, model-gateway, litellm, finding-1, finding-2]
requires:
  - pyproject.toml extras [runtime, agents, gui]
  - config/model_gateway.vllm.yaml (frozen Phase-8 source)
  - config/model_gateway.ollama.yaml (frozen Phase-8 source)
  - src/agent_mesh/sandbox/executor.py (read-only — docker CLI gate)
provides:
  - Dockerfile (shared D-01 command-parameterized app image + docker CLI client)
  - .dockerignore (lean build context)
  - config/model_gateway.vllm.compose.yaml (service-DNS api_base, vllm:8000/v1)
  - config/model_gateway.cpu.compose.yaml (service-DNS api_base, ollama:11434; A5 name)
affects:
  - 10-02 (docker-compose.yml mounts the compose-variant profiles + builds this image)
  - Phase 11 (no-egress assertion — variants stay loopback-service-only, no cloud URL)
tech-stack:
  added: []   # zero new pip/npm packages; only the docker-cli OS package + python:3.12-slim base image
  patterns:
    - "one shared image, command-parameterized (api/worker/gui differ only by command:)"
    - "compose-variant model profile mount (Finding #1): service-DNS api_base, not loopback"
    - "worker DooD via subprocess + docker CLI client binary (Finding #2); no python docker SDK"
key-files:
  created:
    - Dockerfile
    - .dockerignore
    - config/model_gateway.vllm.compose.yaml
    - config/model_gateway.cpu.compose.yaml
  modified: []
decisions:
  - "Base image python:3.12-slim (pinned minor, >=3.11, no floating :latest)"
  - "docker-cli OS package (not docker.io) — on Debian trixie the slim base, docker.io ships only the daemon; the worker needs only the client"
  - "docker/ repo dir excluded from build context to avoid /app/docker shadowing import docker"
metrics:
  duration: ~20m
  completed: 2026-06-10
  tasks: 2
  files: 4
---

# Phase 10 Plan 01: Shared App Image + Compose-Variant Model Profiles Summary

One-liner: A single command-parameterized `Dockerfile` builds the shared D-01 app
image (installs `.[runtime,agents,gui]`, carries the docker CLI *client* for the worker
DooD path, no python docker SDK), plus two compose-variant model profiles
(`vllm.compose.yaml` → `http://vllm:8000/v1`, `cpu.compose.yaml` → `http://ollama:11434`)
that fix Finding #1's loopback-in-compose break without editing the frozen Phase-8 files.

## What Was Built

### Task 1 — Shared root `Dockerfile` (D-01) + `.dockerignore`
- `Dockerfile`: `FROM python:3.12-slim`, `WORKDIR /app`, `PYTHONPATH=/app/src`,
  `COPY . /app`, `pip install ".[runtime,agents,gui]"`. No ENTRYPOINT/CMD — compose
  `command:` selects api/worker/gui per service.
- Carries the **docker CLI client** via the `docker-cli` apt package (Finding #2 — the
  worker shells out to `docker` via `subprocess.run` gated by `shutil.which("docker")`).
- `.dockerignore`: starts from `.gitignore`, adds `.git`, `.sbxwork/`, the active
  `config/model_gateway.config.yaml` swap state, `docker/`, `.planning/`, `.claude/`.

### Task 2 — Compose-variant model profiles (Finding #1 + A5)
- `config/model_gateway.vllm.compose.yaml`: byte-identical to `model_gateway.vllm.yaml`
  except the three `api_base` → `http://vllm:8000/v1` (keeps `/v1`).
- `config/model_gateway.cpu.compose.yaml`: byte-identical to `model_gateway.ollama.yaml`
  except the three `api_base` → `http://ollama:11434` (no `/v1`). Named `cpu` so 10-02's
  `${MODEL_PROFILE}=cpu` interpolation resolves (A5).
- Frozen `low/medium/high-complexity` names, model strings, fallbacks, litellm/general
  settings kept verbatim. Phase-8 `vllm.yaml`/`ollama.yaml` untouched. No `localhost` leaked.

## CROSS-PLAN PATH CONTRACT (load-bearing for Finding #1 — copy-paste into 10-02)

- **WORKDIR set by the Dockerfile:** `/app`
- **Active config the container reads (ABSOLUTE path):**
  `/app/config/model_gateway.config.yaml`
- **Why:** `build_router` reads the *relative* `config/model_gateway.config.yaml`, which
  resolves only when the container CWD == WORKDIR (`/app`) AND `config/` was copied under
  it (it is — `COPY . /app`). **10-02 MUST mount the chosen compose-variant onto this
  exact absolute target** (`/app/config/model_gateway.config.yaml`). A drift (different
  WORKDIR / config copied elsewhere) makes the bind silently miss and `docker compose
  config` (Pitfall 3) will NOT catch it — a green COMPOSE-03 over a hollow SC-1.
- **Volume source to interpolate:** `config/model_gateway.${MODEL_PROFILE}.compose.yaml`
  (`MODEL_PROFILE=vllm` → `…vllm.compose.yaml`; `MODEL_PROFILE=cpu` → `…cpu.compose.yaml`).

## Verification

All plan acceptance/verification criteria passed (Docker present in this worktree, so the
real Finding #2 checks ran against the **built image**, not greps):

| Check | Result |
|-------|--------|
| All 4 files exist | PASS |
| `grep runtime,agents,gui` Dockerfile | PASS |
| `grep -Ei docker.io\|docker-cli\|docker-ce-cli` Dockerfile | PASS (`docker-cli`) |
| `FROM python:3.1[1-9]+` pinned, no `:latest` | PASS (3.12-slim) |
| `.dockerignore` has `.venv` + `.git` + `.sbxwork` | PASS |
| **Image built** (`docker build -t agent-mesh:smoke .`) | PASS |
| **python `docker` SDK absent in image** (`find_spec('docker') is None`) | PASS |
| **docker CLI client present & runnable in image** (`docker --version`) | PASS |
| `agent_mesh` importable from CWD `/app` | PASS |
| `api_base: http://vllm:8000/v1` count == 3 | PASS |
| `api_base: http://ollama:11434` count == 3 | PASS |
| no `localhost` in either compose variant | PASS (0/0) |
| frozen `*-complexity` names count == 3 (vllm) | PASS |
| `ollama_chat/` prefix in cpu variant | PASS |
| both compose variants parse as YAML | PASS |
| non-comment diff vs source == only the 3 api_base lines | PASS |
| Phase-8 `vllm.yaml`/`ollama.yaml` untouched | PASS (empty diff) |
| `git diff --stat -- src/` empty | PASS (empty) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] docker CLI package corrected `docker.io` → `docker-cli`**
- **Found during:** Task 1 (image build + in-image CLI verification)
- **Issue:** The plan's action text suggested `apt docker.io OR the docker-cli package`.
  Empirically, on the current `python:3.12-slim` base (Debian trixie), the `docker.io`
  package ships **only the daemon** (`dockerd`, `docker-proxy`, `docker-init`) — it does
  NOT provide the `docker` **client** binary (`/usr/bin/docker`). The worker's DooD path
  needs the *client* only (it talks to the host daemon over the mounted socket). Installing
  `docker.io` would have left `shutil.which("docker")` failing in the worker → SandboxUnavailable.
- **Fix:** Install `docker-cli` (provides `/usr/bin/docker`, version 26.1.5). Acceptance
  criterion 3 greps `docker.io|docker-ce-cli|docker-cli` — `docker-cli` matches. Verified
  the client runs in the built image (`docker --version`).
- **Files modified:** Dockerfile
- **Commit:** b552aff

**2. [Rule 3 - Blocking] Excluded repo `docker/` dir from build context to keep `import docker` absent**
- **Found during:** Task 1 (python-`docker`-SDK-absent acceptance check)
- **Issue:** `COPY . /app` copied the repo's existing `docker/` directory (holding
  `docker/api.Dockerfile` etc.) to `/app/docker`. With CWD `/app`, `find_spec('docker')`
  resolved that directory as a **phantom namespace package**, so the acceptance check
  reported the SDK "present" even though the real PyPI `docker` distribution is genuinely
  absent (`importlib.metadata` shows no `docker` dist; `docker.__file__` is `None`).
- **Fix:** Added `docker/` to `.dockerignore`. Those per-service Dockerfiles are build-time
  only, superseded by the shared root Dockerfile, and referenced by nothing (verified via
  `git grep`). Excluding them keeps the context lean AND removes the namespace shadow, so
  the acceptance check now correctly reports the SDK absent against the built image.
- **Files modified:** .dockerignore
- **Commit:** b552aff

## Authentication Gates

None.

## Known Stubs

None — both artifacts are real, build-validated, and consumed as-is by 10-02.

## Self-Check: PASSED
- FOUND: Dockerfile
- FOUND: .dockerignore
- FOUND: config/model_gateway.vllm.compose.yaml
- FOUND: config/model_gateway.cpu.compose.yaml
- FOUND commit: b552aff (Task 1)
- FOUND commit: 9d89704 (Task 2)
