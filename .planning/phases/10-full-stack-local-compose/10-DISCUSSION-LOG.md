# Phase 10: Full-Stack Local Compose - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-10
**Phase:** 10-full-stack-local-compose
**Areas discussed:** App-image strategy, Worker sandbox, Langfuse depth, Model backend default, CPU-path make targets, LiteLLM service shape

---

## App-image strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Shared Dockerfile, mirror deploy | One Dockerfile, command-parameterized per service (api/worker/gui); mirrors P7 deploy image model; highest deploy-fidelity | ✓ |
| Base python + bind-mount | No Dockerfile; python:3.x base + bind-mount + pip-install; leaner, but no real artifact, diverges from deploy | |
| Per-service Dockerfiles | Separate Dockerfile per service; most faithful to 3-image registry but most boilerplate for one shared codebase | |

**User's choice:** Shared Dockerfile, mirror deploy
**Notes:** Deploy-fidelity — compose proves the same artifact GCP would run. Consistent with controllability/real-validation preference.

---

## Worker sandbox (P2 Docker sandbox in-stack)

| Option | Description | Selected |
|--------|-------------|----------|
| Out of compose scope | No code-executor service, no docker socket on worker; required set = literal SC list; sandbox exercised by existing tests only | |
| Mount docker socket on worker | Bind-mount /var/run/docker.sock so the real sandbox path spawns sibling containers in-stack; higher fidelity, privileged/security wrinkle | ✓ |

**User's choice:** Mount docker socket on worker
**Notes:** Wants the real P2 sandbox to actually run in the composed stack, not stubbed. RUNBOOK must disclose privileged docker-socket mount as dev-only.

---

## Langfuse depth

| Option | Description | Selected |
|--------|-------------|----------|
| Profile-gated (compose-up brings it) | Full Langfuse v3 (~6 containers) inlined behind `--profile langfuse`; raw `up` lean, `make compose-up` adds the profile | ✓ |
| Always-on inline | All 6 langfuse services always-on; simplest one-command-everything, heavy by default | |
| Include upstream compose | Reference upstream compose via `include:`; less duplication but pins external file/version, complicates single-file COMPOSE-03 assertion | |

**User's choice:** Profile-gated (compose-up brings it)
**Notes:** Lean core; full langfuse opt-in via make. UI-minted keys → tracing loud-skips on first up regardless (carried from P9).

---

## Model backend default

| Option | Description | Selected |
|--------|-------------|----------|
| Ollama default, vLLM GPU profile | Ollama (CPU, any box) default, vLLM as `--profile gpu`; runs anywhere, recommended | |
| vLLM default | vLLM (GPU) default, Ollama as `--profile cpu`; higher serving fidelity, fails on no-GPU box | ✓ |
| Both profile-gated, no default | Neither always-on; collapses to a default once make picks one | |

**User's choice:** vLLM default
**Notes:** Real-serving choice (GPU, stronger tool-calling). Accepts GPU-default needs a CPU override path for no-GPU boxes — settled in next area.

---

## CPU-path make targets (consequence of vLLM-default)

| Option | Description | Selected |
|--------|-------------|----------|
| Two targets: compose-up + compose-up-cpu | Separate GPU and CPU one-command targets | |
| Single compose-up, env-selected | One `make compose-up` reading `MODEL_PROFILE ?= vllm` (vllm\|cpu); fewer targets | ✓ |
| vLLM only, document Ollama by hand | Only GPU target; CPU path is raw docker command in RUNBOOK | |

**User's choice:** Single compose-up, env-selected (`MODEL_PROFILE ?= vllm`)
**Notes:** `MODEL_PROFILE=cpu make compose-up` for non-GPU boxes; one target, env switch.

---

## LiteLLM service shape

> User paused this question to request verification before answering: "verify if the app
> honors MODEL_GATEWAY_BASE_URL via env today and whether using a proxy breaks the
> architectural alignment between deployed and local operation."
>
> **Verification performed:** Real completions route through the in-process
> `litellm.Router` (`get_chat_model`/`get_router_chat_model`, `worker/graph.py:149`,
> `eval/judges.py:351`); per-route `api_base` from yaml (D-06 chokepoint).
> `settings.model_gateway_base_url` (`:4000`) is read by exactly one site —
> `gui/admin_console.py:49`, display-only, zero completion calls. Deploy scripts define
> `agent-mesh-api/-worker/-code-executor` images only — no litellm Cloud Run service. A
> proxy would invent an absent topology and need a forbidden `src/` rewire off the GW-02
> chokepoint.

| Option | Description | Selected |
|--------|-------------|----------|
| In-process, no litellm service (aligned) | LiteLLM = embedded Router in api/worker; zero-src, preserves deploy↔local fidelity + GW-02 chokepoint; RUNBOOK/manifest note "embedded" | ✓ |
| Proxy container anyway (fidelity-break) | Standalone litellm proxy for literal SC match; up-but-unused unless rewired; diverges from deploy | |

**User's choice:** In-process, no litellm service (aligned)
**Notes:** Verification confirmed the proxy would break deploy↔local alignment and require a forbidden src/ change. COMPOSE-03 required-services list omits litellm by design; RUNBOOK + manifest document LiteLLM-is-embedded.

---

## Claude's Discretion

- Per-service healthchecks (which services + exact probes; COMPOSE-03 asserts present).
- Inter-service env/DNS wiring (service names for DSN/host; which env each app service receives) — reuse P9 pinned defaults.
- `make compose-down` profile scope (bring down all profiles cleanly).
- Exact `docker compose config` assertion shape in the COMPOSE-03 test (services / healthcheck keys / pgvector image string; whether to name profiles).

## Deferred Ideas

- Standalone LiteLLM proxy container — rejected (deploy↔local fidelity + forbidden src/ rewire).
- OFFLINE / no-egress assertions over the assembled stack → Phase 11.
- Actual `compose up` smoke in CI → out of scope; COMPOSE-03 stays static + loud-skip.
- Distinct-model-per-tier in the composed backend → inherited P8 deferral.
