# Phase 11: Offline / No-Egress Posture - Research

**Researched:** 2026-06-11
**Domain:** Config/.env/docs/tests-only no-cloud-LLM-egress assertion harness (litellm 1.83.7 transport seam, pytest autouse deny-guard, YAML/compose marker sweep, durable zero-`src/` invariant)
**Confidence:** HIGH (the deny-guard seam choice is empirically proven against the installed litellm 1.83.7 / httpx 0.28.1)

## Summary

Phase 11 turns "runs offline with no cloud-hosted LLM egress" into an **asserted** property using only config/.env/docs/tests — **zero `src/` change** is a [BLOCKING] invariant. The work is three test/artifact bundles mapped 1:1 to OFFLINE-01/02/03, plus a durable expression of the zero-`src/` guardrail. Every artifact already has a precise pattern to mirror in the existing repo: `tests/test_local_profiles.py` (the LOCAL-04 sweep to **extend**, not duplicate), `tests/test_d06_chokepoint.py` (config-load + per-route assertion to mirror/invert), `tests/conftest.py` (loud-skip fixture convention), and `tests/test_compose_config.py` (the only CI-wired P10 artifact + its module-level loud-skip shape).

The single highest-value research result resolves Open Discretion #1 empirically. The deny-guard (D-02) must patch **`socket.getaddrinfo`**, NOT `socket.create_connection` and NOT an httpx-transport hook. Proven against installed litellm 1.83.7 + httpx 0.28.1: the **sync** path (`litellm.completion`) bottoms out at `socket.create_connection` (httpcore sync backend), but the **async** path (`litellm.acompletion`) uses anyio's `connect_tcp` and **bypasses `socket.create_connection` entirely** — it reached `api.anthropic.com` for real. Only `socket.getaddrinfo` (the DNS-resolution chokepoint below *both* backends) fired on both sync and async, with the host as `arg[0]`. The LangGraph/Deep Agents worker path is async, so a `create_connection`-only guard would be silently vacuous against the real default-lane path.

Two empirical pitfalls shape the design: (1) litellm fetches a remote model-cost map from `raw.githubusercontent.com` at call time — a non-cloud-LLM host that a naive deny-guard would either trip on or must allowlist; setting `LITELLM_LOCAL_MODEL_COST_MAP=True` suppresses it cleanly. (2) `vertex_ai/` calls fail at `DefaultCredentialsError` **before any socket connect** in the creds-free lane, so the connect-level guard reliably catches **Anthropic + CF** but NOT Vertex — Vertex's real guard is the D-01 file-content marker sweep. The durable zero-`src/` assertion has a genuine trilemma (always-in-`make test` × fixed base × survives-future-src-edits — pick two); the recommendation is an **env-var-gated loud-skip pytest** mirroring the repo's `pg_dsn`/docker-CLI convention, because the branch-relative `git diff main...HEAD` form is **vacuous on `main`** (where `make test` runs post-merge), and a hardcoded-base always-on form is a time-bomb that breaks the next src-touching milestone.

**Primary recommendation:** Three plans — (1) **D-01+D-04 marker sweep** extends `test_local_profiles.py` to all 4 local profiles + `docker-compose.yml` api/worker env blocks with a loopback+service-DNS allowlist; (2) **D-02 deny-guard** is a `socket.getaddrinfo` autouse fixture (scoped to NOT break `make test-live`) raising only on cloud-LLM hosts, with an `anthropic/`-based positive control + a representative routed default-lane path; (3) **D-03 `.env.offline.example` + RUNBOOK section** plus a **durable env-gated zero-`src/` loud-skip pytest**. All CI-wired tests slot into `make test -m "not live"`; the `.env.offline.example` and RUNBOOK are operator-facing.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01 (whole-file cloud-LLM sweep across all 4 local profiles):** Extend the assertion beyond `api_base` to a **whole-file** cloud-LLM-marker sweep over **all four** local profiles: `config/model_gateway.vllm.yaml` + `model_gateway.ollama.yaml` (loopback) and the P10 compose variants `model_gateway.vllm.compose.yaml` + `model_gateway.cpu.compose.yaml` (service-DNS). **Allowlist** local targets — loopback (`http://localhost`, `http://127.0.0.1`) and in-stack service-DNS (`vllm:8000`, `ollama:11434`). **Deny** cloud-LLM markers anywhere in the file: `CF_AIG_WRAPPER_URL`, `vertex_ai`, `googleapis.com`, `anthropic`, `anthropic.com`, `sk-`. Service-DNS is treated as egress-free in-stack, not required to be loopback.
- **D-02 (model-host deny-guard, connect-level, correctly scoped):** Enforce "the default creds-free lane makes no outbound to a real LLM provider/gateway" with a **model-host deny-guard** — an autouse test fixture patching the connect/transport seam to **raise only on known cloud-LLM hosts** (`anthropic.com`, `*.googleapis.com` Vertex, the CF AI Gateway host, and `MODEL_GATEWAY_BASE_URL` when it resolves cloud). **Every other host is allowed** (Postgres, Langfuse, SaaS adapters) — NOT a `pytest-socket disable_socket` global block. The guard runs over the default creds-free lane, which today makes no model call (`build_router` is lazy — Pitfall 6, verified litellm 1.83.7), so it should pass clean, PROVING the posture. Test-only, **zero new `src/`**. *(Needs at least one test that actually exercises a representative default-lane path under the fixture so the proof is non-vacuous.)*
- **D-03 (`.env.offline.example` concrete artifact):** Ship a concrete **`.env.offline.example`**: `CF_AIG_WRAPPER_URL=` blank, `ANTHROPIC_API_KEY=` blank, `VERTEX_*` blank, `MODEL_GATEWAY_BASE_URL` local, local model `api_base` via the `use-vllm`/`use-ollama` profile swap. **SaaS/tool-pack creds left as normal.** Plus a RUNBOOK "Offline / no-egress posture" section. **No new runtime OFFLINE env-guard** — zero-`src/` forbids reading a new env var at runtime; OFFLINE is asserted-over-config + documented, not a runtime switch.
- **D-04 (profiles + `docker-compose.yml` env sweep):** The no-cloud-LLM sweep also covers the `docker-compose.yml` `api`/`worker` env blocks — assert **no cloud-LLM `api_base`** and **no VALUED cloud-LLM key** (Vertex/Anthropic/CF). Local Postgres, self-hosted Langfuse, and service-DNS references stay legitimate and must NOT trip the sweep.
- **Zero `src/` change** — config/.env/Makefile/docs/tests only; a [BLOCKING] invariant asserts `git diff <phase-base>..HEAD -- src/` is empty (mirrors P8/P9/P10).
- **Delivery = make + RUNBOOK + loud-skip-test**; operator run/swap targets are best-effort, never wired into `make test`/CI. Canonical test interpreter is `.venv/bin/python`.
- **P8 D-06** already dropped cloud-named routes from local profiles; fallbacks stay within the 3 local deployment names — no cloud route exists for the sweep to trip.

### Claude's Discretion (RESOLVED by this research — see Open Questions)
- **Exact connect/transport seam for the deny-guard** — RESOLVED: `socket.getaddrinfo` (empirically the only seam catching both sync+async litellm 1.83.7). See Code Examples + Open Question 1.
- **Exact cloud-LLM marker/host list finalization** — RESOLVED: see "Final Marker/Host Lists" below. Keep cloud-LLM-scoped, never generic-online.
- **Durable zero-`src/` invariant** (carried from P10 Audit Note 1) — RESOLVED: env-var-gated loud-skip pytest. See Open Question 3.

### Deferred Ideas (OUT OF SCOPE)
- **Runtime OFFLINE enforcement guard** (env-gated `OFFLINE=1` that hard-blocks cloud-LLM routes at runtime) — requires reading a new env var in `src/`, forbidden by the zero-`src/` guardrail. Defer to a future src-touching milestone.
- **Distinct-model-per-tier** locally — already deferred in Phase 8 (D-04).
- **Blanket no-network test posture** (block ALL outbound) — explicitly rejected this phase as out-of-scope over-reach; offline is cloud-LLM-scoped only.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OFFLINE-01 | An OFFLINE posture is expressible via config/.env (CF off, no Vertex/Anthropic keys, local-only `api_base`, `.env`-sourced secrets) and documented in RUNBOOK | D-03: `.env.offline.example` derived from `.env.example` lines 51-59 (cloud-LLM key block blanked) + RUNBOOK section after line 250 ("Full-stack local compose"). The offline `api_base` is supplied by the `use-vllm`/`use-ollama` file-swap (Makefile:94-97), not a new env var. |
| OFFLINE-02 | A test asserts the local/offline model profiles contain NO cloud `api_base` (no Vertex/Anthropic/CF wrapper URL) and no cloud-key env references — egress-free by construction | D-01 (4 profiles, whole-file sweep) + D-04 (`docker-compose.yml` api/worker env blocks). Extend `test_local_profiles.py` `_CLOUD_MARKERS`/`_LOOPBACK`/`_NAMES`. Allowlist loopback + service-DNS. The cloud reference `config/model_gateway.cloud.yaml` is the NEGATIVE control (must TRIP the sweep) — proves the sweep is non-vacuous. |
| OFFLINE-03 | A test asserts the default creds-free lane performs no outbound network to a real provider/gateway (the existing stub posture, made explicit and enforced) | D-02 `socket.getaddrinfo` deny-guard, autouse, cloud-LLM-host-scoped. Positive control: `anthropic/` call under fixture must raise. Representative path: route a completion through the active local profile under the fixture; assert only loopback/service-DNS hosts resolve. `build_router` lazy (Pitfall 6) ⇒ default lane passes clean. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| File-content cloud-LLM marker sweep (D-01/D-04) | Test harness (config-validation) | — | Reads YAML/compose files off disk and asserts over content; no runtime, no `src/`, mirrors `test_d06_chokepoint`/`test_local_profiles`. |
| Connect-level cloud-LLM host deny (D-02) | Test harness (autouse fixture) | litellm transport (`socket.getaddrinfo`, observed-not-modified) | Patches the stdlib DNS seam in-test only; the in-process litellm Router is the surface being constrained, but the guard lives entirely in `tests/`. Zero `src/`. |
| OFFLINE posture expression (D-03) | Operator config (`.env.offline.example`) + docs (RUNBOOK) | Test harness (the D-01 sweep can run over `.env.offline.example`) | Posture is asserted-over-config + documented, never a runtime switch (zero-`src/` forbids a new runtime env read). |
| Durable zero-`src/` invariant | Test harness (env-gated loud-skip pytest) | Operator/CI (sets the base-SHA env var) | `git diff <base>..HEAD -- src/`; the base ref cannot be hardcoded durably (time-bomb) nor branch-relative (vacuous on `main`), so it is env-gated like `pg_dsn`. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pytest` | (installed, repo default) | Test runner for all 3 plans; autouse fixtures for the deny-guard | The entire repo test convention; `make test` = `pytest -q -m "not live"`. [VERIFIED: Makefile:41] |
| `pyyaml` | (installed) | Load the 4 profiles + (optionally) parse compose env blocks | Already used by `test_local_profiles.py`/`test_d06_chokepoint.py` (`yaml.safe_load`). [VERIFIED: tests/test_local_profiles.py:25] |
| `litellm` | 1.83.7 | The transport whose cloud-LLM connect the deny-guard intercepts (observed only — NOT modified) | Pinned `litellm>=1.40` in pyproject; installed 1.83.7. [VERIFIED: `.venv/bin/python -c "from importlib.metadata import version; version('litellm')"` → 1.83.7] |
| `httpx` | 0.28.1 | litellm's HTTP client; its sync backend → `socket.create_connection`, async backend → anyio `connect_tcp` | Confirms why `getaddrinfo` (below both) is the correct seam. [VERIFIED: `version('httpx')` → 0.28.1] |
| `socket` (stdlib) | py3.14 | The `getaddrinfo` deny-guard seam | Stdlib; no install. The DNS chokepoint shared by sync + async httpx backends. [VERIFIED: empirical, this session] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `subprocess` + `git` (stdlib/CLI) | — | The durable zero-`src/` `git diff` assertion | Plan 3, env-gated loud-skip pytest. `git` confirmed available in the work tree. [VERIFIED: `git rev-parse --is-inside-work-tree` → true] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `socket.getaddrinfo` patch | `socket.create_connection` patch | **REJECTED** — empirically misses the async `acompletion` path (anyio `connect_tcp`); the worker is async, so the guard would be vacuous against the real default-lane path. [VERIFIED this session] |
| `socket.getaddrinfo` patch | httpx custom transport / litellm client injection | **REJECTED** — litellm builds its own httpx `HTTPHandler`/`AsyncHTTPHandler` instances internally; there is no single injectable client, and intercepting per-instance would touch many call sites and risk `src/` coupling. `getaddrinfo` is one stdlib chokepoint. [VERIFIED: litellm `custom_httpx/http_handler.py` builds clients internally] |
| `socket.getaddrinfo` patch | `pytest-socket` `disable_socket()` | **REJECTED in CONTEXT (D-02)** — over-reaches into legitimate Postgres/Langfuse/SaaS traffic and mischaracterizes the cloud-LLM-only scope. |
| env-gated loud-skip zero-`src/` pytest | hardcoded-base always-on pytest | **REJECTED** — time-bomb: passes in P11, then fails permanently in the next legitimate src-touching milestone's `make test`. |
| env-gated loud-skip zero-`src/` pytest | `git diff main...HEAD -- src/` (branch-relative) | **REJECTED** — vacuous on `main`; phases merge worktree branches into `main`, and `make test` runs post-merge on `main` where `main...HEAD` is empty. [VERIFIED: `git diff main...HEAD -- src/` empty on main, this session] |

**Installation:** None. All dependencies already installed; `git` already available. No new packages ⇒ Package Legitimacy Audit is N/A (see below).

## Package Legitimacy Audit

**No external packages are installed by this phase.** Every dependency (`pytest`, `pyyaml`, `litellm`, `httpx`, stdlib `socket`/`subprocess`, the `git` CLI) is already present and pinned. The slopcheck/registry gate is therefore **N/A** — there is nothing to install. (If the planner adds any helper package, run the Package Legitimacy Gate before doing so; none is needed for the design below.)

## Architecture Patterns

### System Architecture Diagram

```
                          OFFLINE-02 (file-content sweep)              OFFLINE-03 (connect-level deny)
                          ────────────────────────────────            ───────────────────────────────
   on-disk artifacts                                                     in-test litellm call
   ┌─────────────────────────────┐                                       ┌───────────────────────────┐
   │ config/model_gateway.        │   yaml.safe_load / read_text         │ litellm.completion(...)    │  sync  → socket.create_connection
   │   vllm.yaml                  │ ────────────┐                        │ litellm.acompletion(...)   │  async → anyio connect_tcp
   │   ollama.yaml                │             │                        └──────────────┬────────────┘
   │   vllm.compose.yaml          │             ▼                                       │ BOTH resolve DNS via
   │   cpu.compose.yaml           │   ┌──────────────────────┐                          ▼
   │ docker-compose.yml (api/     │   │ whole-file marker     │              ┌────────────────────────────┐
   │   worker env blocks)         │   │ sweep:                │              │ socket.getaddrinfo(host,…) │ ← AUTOUSE deny-guard patches HERE
   │ .env.offline.example         │   │  ALLOW loopback +     │              │  host == cloud-LLM host? ──┼─→ raise (DENY)
   └─────────────────────────────┘   │       service-DNS     │              │  else ─────────────────────┼─→ real getaddrinfo (ALLOW)
                                      │  DENY cloud markers   │              └────────────────────────────┘
   config/model_gateway.cloud.yaml ─→│  (NEGATIVE control:   │                         │
     (NEGATIVE control — MUST trip)   │   must TRIP)          │              allow: localhost, 127.0.0.1, vllm, ollama,
                                      └──────────┬───────────┘                          postgres, langfuse-web, SaaS hosts
                                                 ▼                          deny:  api.anthropic.com, *.googleapis.com (Vertex),
                                          assert no-cloud-marker                    gateway.ai.cloudflare.com, cloud MODEL_GATEWAY_BASE_URL

   OFFLINE-01 (posture): .env.offline.example (cloud-LLM creds blank, local api_base via use-vllm/use-ollama) + RUNBOOK section
   ZERO-SRC invariant:  env-gated pytest → subprocess `git diff $ZERO_SRC_BASE..HEAD -- src/` must be empty (loud-skip when unset)
```

### Recommended Project Structure
```
tests/
├── test_local_profiles.py     # EXTEND (D-01) — add 2 compose profiles, service-DNS allowlist, whole-file sweep
├── test_offline_compose_env.py# NEW (D-04) — docker-compose.yml api/worker env-block sweep
├── test_offline_deny_guard.py # NEW (D-02) — socket.getaddrinfo autouse deny-guard + positive control + representative path
├── test_zero_src_invariant.py # NEW — env-gated loud-skip `git diff` durable assertion
└── conftest.py                # MIRROR loud-skip convention (do NOT add a session-wide autouse that breaks -m live)
config/
└── (4 profiles + cloud.yaml unchanged — sweep targets, FROZEN)
.env.offline.example           # NEW (D-03)
RUNBOOK.md                     # ADD "Offline / no-egress posture" section (near line 250)
```
*(Plan boundaries are the planner's call; file split shown so plans own non-overlapping files. The deny-guard fixture may live in its own `tests/test_offline_deny_guard.py` rather than the root `conftest.py` to avoid leaking the autouse patch into the whole suite — see Pitfall 4.)*

### Pattern 1: Extend the existing `_CLOUD_MARKERS` sweep, don't duplicate it
**What:** `test_local_profiles.py` already has `_CLOUD_MARKERS`, `_LOOPBACK`, `_NAMES`, and a parametrized per-profile loop scoped to `api_base`. D-01 extends this to (a) the 2 compose profiles, (b) a `_SERVICE_DNS` allowlist (`vllm:8000`, `ollama:11434`), and (c) a **whole-file** `read_text()` sweep (its docstring literally says the whole-file sweep is "Phase 11's job").
**When to use:** OFFLINE-02 profile sweep.
**Example:**
```python
# Source: extends tests/test_local_profiles.py (existing _CLOUD_MARKERS at :40-46)
_PROFILES = {
    "vllm": _REPO / "config" / "model_gateway.vllm.yaml",
    "ollama": _REPO / "config" / "model_gateway.ollama.yaml",
    "vllm-compose": _REPO / "config" / "model_gateway.vllm.compose.yaml",   # ADD (D-01)
    "cpu-compose": _REPO / "config" / "model_gateway.cpu.compose.yaml",     # ADD (D-01)
}
_LOOPBACK = ("http://localhost", "http://127.0.0.1")
_SERVICE_DNS = ("http://vllm:8000", "http://ollama:11434")                  # ADD — egress-free in-stack
_LOCAL_ALLOW = _LOOPBACK + _SERVICE_DNS
# Whole-file deny markers (D-01 floor + justified additions — see Final Marker List)
_FILE_DENY = ("CF_AIG_WRAPPER_URL", "vertex_ai", "googleapis.com",
              "anthropic", "anthropic.com", "sk-")

@pytest.mark.parametrize("name", list(_PROFILES))
def test_profile_file_has_no_cloud_llm_marker(name):
    text = _PROFILES[name].read_text()
    hits = [m for m in _FILE_DENY if m in text]
    assert not hits, f"{name}: cloud-LLM marker(s) {hits} present in profile file"

@pytest.mark.parametrize("name", list(_PROFILES))
def test_every_route_api_base_is_local(name):
    cfg = yaml.safe_load(_PROFILES[name].read_text())
    for r in cfg["model_list"]:
        ab = r["litellm_params"]["api_base"]
        assert ab.startswith(_LOCAL_ALLOW), f"{name}/{r['model_name']}: api_base {ab!r} not local"
```

### Pattern 2: Negative control — the cloud reference MUST trip the sweep
**What:** Prove the sweep is non-vacuous by asserting that `config/model_gateway.cloud.yaml` (which contains `vertex_ai/`, `anthropic/`, `CF_AIG_WRAPPER_URL`) **DOES** trip the deny list. Mirrors `test_d06_chokepoint.py`'s `test_guard_detects_a_synthetic_offender` negative-control pattern (:180).
**When to use:** OFFLINE-02 — defends against a future edit that silently empties `_FILE_DENY`.
**Example:**
```python
def test_cloud_reference_profile_does_trip_the_sweep():
    text = (_REPO / "config" / "model_gateway.cloud.yaml").read_text()
    assert any(m in text for m in _FILE_DENY), (
        "cloud.yaml no longer trips _FILE_DENY — the sweep is vacuous/broken"
    )
```

### Pattern 3: `socket.getaddrinfo` autouse deny-guard (the proven seam)
**What:** Patch `socket.getaddrinfo` to raise only on cloud-LLM hosts. Catches BOTH sync (`completion`) and async (`acompletion`) litellm paths — verified this session. Set `LITELLM_LOCAL_MODEL_COST_MAP=True` so the model-cost-map fetch to `raw.githubusercontent.com` does not make a real outbound call during the offline suite.
**When to use:** OFFLINE-03.
**Example:** see Code Examples below (full fixture).

### Anti-Patterns to Avoid
- **`socket.create_connection`-only patch:** misses the async worker path → vacuous proof. Use `getaddrinfo`.
- **Session-wide autouse deny-guard in root `conftest.py`:** would also block the legitimate cloud calls in `make test-live` (`-m live`). Scope it to the offline test module / condition it off when `live` creds are present.
- **Substring host match that catches `googleapis.com` too broadly:** `*.googleapis.com` is Vertex's host family, but be precise — match the Vertex host (`aiplatform.googleapis.com` / `*-aiplatform.googleapis.com`), not every Google API a SaaS adapter might legitimately use. (Vertex rarely reaches the seam anyway — see Pitfall 2.)
- **Hardcoded-base durable `git diff` pytest:** time-bomb. Use env-gated loud-skip.
- **Editing the 4 frozen profiles or `model_gateway.cloud.yaml`:** they are sweep TARGETS / the negative control. P8/P10 froze them. Touching them is out of scope and risks the negative control.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Intercepting litellm's outbound for a host check | A custom httpx transport / monkeypatched litellm client | `socket.getaddrinfo` autouse patch | One stdlib chokepoint below both httpx backends; no per-call-site coupling, zero `src/`. |
| Per-profile sweep scaffolding | A new test module from scratch | Extend `test_local_profiles.py`'s `_CLOUD_MARKERS`/`_LOOPBACK`/parametrize | The seam exists and its docstring designates the whole-file sweep as Phase 11's job. |
| Loud-skip-when-unavailable | A bespoke skip mechanism | Mirror `pg_dsn` (`pytest.skip` when `TEST_DATABASE_URL` unset) / `test_compose_config.py` module-level `skipif(shutil.which(...))` | Established repo convention; keeps `make test` green on any box. |
| Suppressing litellm's GitHub cost-map fetch | A network-mock layer | `os.environ["LITELLM_LOCAL_MODEL_COST_MAP"]="True"` in the fixture | Documented litellm switch; removes a non-cloud-LLM outbound that would otherwise confuse the guard. [VERIFIED this session] |

**Key insight:** The litellm transport is a moving target across versions; the stdlib DNS seam (`getaddrinfo`) is stable and is the single point both the sync and async httpx backends must pass through. Pinning the guard to that seam (not to httpx/litellm internals) makes it durable.

## Common Pitfalls

### Pitfall 1: The async path bypasses `socket.create_connection`
**What goes wrong:** A deny-guard patching `socket.create_connection` passes its sync positive control but the real LangGraph/Deep Agents worker is async (`acompletion`) and reaches the provider unblocked — the proof is silently vacuous.
**Why it happens:** httpcore's **sync** backend uses `socket.create_connection`; its **anyio async** backend uses `anyio.connect_tcp` (does NOT call `socket.create_connection`).
**How to avoid:** Patch `socket.getaddrinfo` — it fires on both. [VERIFIED: async `acompletion` raised the guard only under `getaddrinfo`, never under `create_connection`, this session.]
**Warning signs:** A deny-guard test that only ever exercises `litellm.completion` (sync) and never `acompletion`.

### Pitfall 2: Vertex dies at credential-load BEFORE the socket seam
**What goes wrong:** A "does the guard catch Vertex?" test passes for the wrong reason — `vertex_ai/` raises `google.auth.exceptions.DefaultCredentialsError` before ANY connect, so neither `getaddrinfo` nor the guard is reached in the creds-free lane.
**Why it happens:** litellm loads ADC credentials before resolving the Vertex host.
**How to avoid:** Use **`anthropic/`** for the positive control (it reaches the seam with a fake `sk-ant-` key). Treat the **D-01 file-content marker sweep** as Vertex's real guard, and say so in the doc. Do not claim the connect-level guard "catches Vertex" in the creds-free lane.
**Warning signs:** A Vertex positive-control assertion that depends on `DefaultCredentialsError` rather than the deny raising.

### Pitfall 3: litellm's model-cost-map fetch is a non-cloud-LLM outbound
**What goes wrong:** At call time litellm fetches `https://raw.githubusercontent.com/.../model_prices_and_context_window.json`. A guard that denies "any unexpected host" trips on GitHub; a guard that only watches cloud-LLM hosts lets a *real* outbound to GitHub happen during the "offline" suite.
**Why it happens:** litellm refreshes its price map from GitHub unless told to use the local backup.
**How to avoid:** `os.environ["LITELLM_LOCAL_MODEL_COST_MAP"]="True"` in the deny-guard fixture (verified to suppress the fetch). Keep the deny list cloud-LLM-scoped so GitHub is allowed if it does occur.
**Warning signs:** `raw.githubusercontent.com` appearing in observed connect hosts during the suite.

### Pitfall 4: A session-wide autouse guard breaks `make test-live`
**What goes wrong:** A root-`conftest.py` `@pytest.fixture(autouse=True)` deny-guard also fires during `pytest -m live`, blocking the legitimate real cloud calls the live lane exists to make.
**Why it happens:** autouse fixtures apply to every test in their scope.
**How to avoid:** Put the fixture in the offline test module (module-scoped autouse), OR gate it to no-op when the `live` marker / real creds (`ANTHROPIC_API_KEY` etc.) are present — mirroring `conftest.py`'s `live_creds` skip (:124-136).
**Warning signs:** `make test-live` starts failing/erroring after the deny-guard lands.

### Pitfall 5: Non-vacuous representative path — `build_router` is lazy
**What goes wrong:** The "default lane makes no model call" proof is vacuous because the default creds-free lane genuinely never calls a model (`build_router` only loads `model_list` into memory — Pitfall 6, verified litellm 1.83.7), so an autouse guard over it asserts nothing.
**Why it happens:** Construction is lazy; no provider call happens at build time.
**How to avoid:** Add an explicit representative-path test under the fixture: route a completion through the **active local profile** (`use-vllm` style — loopback/service-DNS api_base) and assert it resolves only allowlisted hosts (the guard does NOT fire); PLUS the `anthropic/` positive control asserting the guard DOES fire. Together they prove the guard is wired and discriminating.
**Warning signs:** The OFFLINE-03 test only constructs a Router and never drives a completion through the guard.

### Pitfall 6: The host argument position in `getaddrinfo`
**What goes wrong:** A patch that reads `args[0]` breaks if a caller passes `host=` as a keyword, or vice-versa.
**Why it happens:** `socket.getaddrinfo(host, port, ...)` — observed callers pass `host` positionally, but be defensive.
**How to avoid:** `def guard(host, *args, **kwargs)` then inspect `host` — handles the positional case observed empirically; the signature still accepts the rest. [VERIFIED: host was `arg[0]` in both httpcore sync and anyio backends this session.]

## Code Examples

### D-02 deny-guard fixture (the core deliverable)
```python
# Source: empirically derived against litellm 1.83.7 / httpx 0.28.1 (this session).
# Lives in tests/test_offline_deny_guard.py — module-scoped autouse so it does NOT
# leak into the rest of the suite or the -m live lane (Pitfall 4).
import os, socket, asyncio
import pytest

# Cloud-LLM hosts the offline posture forbids. anthropic.com VERIFIED at the seam;
# the others ASSUMED (host shape known, not observed reaching the seam — see Assumptions).
_CLOUD_LLM_HOSTS = (
    "api.anthropic.com",
    "anthropic.com",
    "aiplatform.googleapis.com",          # Vertex (regional: <region>-aiplatform.googleapis.com)
    "gateway.ai.cloudflare.com",          # Cloudflare AI Gateway
)

def _is_cloud_llm_host(host: str) -> bool:
    h = (host or "").lower()
    if h in _CLOUD_LLM_HOSTS:
        return True
    if h.endswith("-aiplatform.googleapis.com") or h.endswith(".gateway.ai.cloudflare.com"):
        return True
    return False

@pytest.fixture(autouse=True)
def _cloud_llm_deny_guard(monkeypatch):
    # Suppress litellm's model-cost-map fetch to raw.githubusercontent.com (Pitfall 3).
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    real = socket.getaddrinfo
    def guard(host, *args, **kwargs):
        if _is_cloud_llm_host(host):
            raise RuntimeError(f"OFFLINE deny: cloud-LLM host {host!r} contacted")
        return real(host, *args, **kwargs)
    monkeypatch.setattr(socket, "getaddrinfo", guard)
    yield

def test_guard_denies_anthropic_positive_control():
    """Positive control: an anthropic/ call MUST trip the guard (proves it's wired)."""
    import litellm
    with pytest.raises(Exception) as ei:
        litellm.completion(model="anthropic/claude-sonnet-4-6",
                           messages=[{"role": "user", "content": "hi"}],
                           api_key="sk-ant-fake", max_retries=0)
    assert "OFFLINE deny" in str(ei.value) or "anthropic.com" in str(ei.value)

def test_guard_denies_anthropic_async_path():
    """The async path (acompletion) is what the worker uses — it MUST also trip."""
    import litellm
    async def go():
        with pytest.raises(Exception) as ei:
            await litellm.acompletion(model="anthropic/claude-sonnet-4-6",
                                      messages=[{"role": "user", "content": "hi"}],
                                      api_key="sk-ant-fake", max_retries=0)
        assert "OFFLINE deny" in str(ei.value) or "anthropic.com" in str(ei.value)
    asyncio.run(go())

def test_default_lane_local_profile_resolves_only_local(monkeypatch, tmp_path):
    """Representative default-lane path (Pitfall 5): drive a completion through the
    ACTIVE LOCAL profile (loopback/service-DNS api_base) under the guard. The guard
    must NOT fire (no cloud-LLM host). A connection refused to localhost is FINE — it
    proves egress targeted loopback, not a cloud host."""
    from agent_mesh.worker.model_gateway import build_router
    router = build_router("config/model_gateway.vllm.yaml")  # loopback api_base
    try:
        router.completion(model="low-complexity",
                          messages=[{"role": "user", "content": "hi"}])
    except Exception as e:
        # Acceptable: connection refused / timeout to http://localhost:8000.
        # NOT acceptable: the OFFLINE deny (would mean a cloud host was contacted).
        assert "OFFLINE deny" not in str(e), f"local profile reached a cloud-LLM host: {e}"
```

### Durable zero-`src/` invariant (env-gated loud-skip)
```python
# Source: mirrors tests/conftest.py pg_dsn loud-skip (:75-88) + test_compose_config.py
# module-skip (:?). Lives in tests/test_zero_src_invariant.py.
import os, subprocess
from pathlib import Path
import pytest

_REPO = Path(__file__).resolve().parents[1]

def test_no_src_change_since_phase_base():
    base = os.getenv("ZERO_SRC_BASE")
    if not base:
        pytest.skip("ZERO_SRC_BASE unset; durable zero-src assertion needs the phase-base SHA")
    out = subprocess.run(
        ["git", "diff", f"{base}..HEAD", "--", "src/"],
        cwd=_REPO, capture_output=True, text=True, check=True,
    ).stdout
    assert out == "", f"src/ changed since {base}:\n{out}"
```
*Operator/CI exports `ZERO_SRC_BASE=5092323` (the P11 spawn-prompt phase base — current HEAD) for the enforcing run; default `make test` loud-skips. This mirrors the repo's `TEST_DATABASE_URL`/docker-CLI loud-skip convention exactly and avoids the time-bomb of a hardcoded always-on base.*

### D-04 compose env-block sweep
```python
# Source: NEW tests/test_offline_compose_env.py — mirrors test_compose_config.py shape.
import yaml
from pathlib import Path
_REPO = Path(__file__).resolve().parents[1]
_COMPOSE = _REPO / "docker-compose.yml"
# A VALUED cloud-LLM key = key present with a non-empty value. In compose, api/worker
# leave LANGFUSE_* blank ("") and set DATABASE_URL/LANGFUSE_HOST to in-stack DNS — all legit.
_CLOUD_KEY_NAMES = ("ANTHROPIC_API_KEY", "VERTEX_PROJECT_ID", "VERTEX_LOCATION",
                    "CF_AIG_WRAPPER_URL", "MODEL_GATEWAY_SHARED_SECRET")

def test_compose_api_worker_env_has_no_valued_cloud_llm_key():
    cfg = yaml.safe_load(_COMPOSE.read_text())
    for svc in ("api", "worker"):
        env = cfg["services"][svc].get("environment", {}) or {}
        # compose env may be list or dict — normalize
        items = env.items() if isinstance(env, dict) else (
            (e.split("=", 1) + [""])[:2] for e in env)
        for k, v in items:
            if k in _CLOUD_KEY_NAMES:
                assert not v, f"{svc}: cloud-LLM key {k} has a VALUED entry {v!r}"
        # And: no cloud api_base / cloud host in any env value
        for k, v in items:
            assert "googleapis.com" not in str(v) and "anthropic" not in str(v) \
                   and "gateway.ai.cloudflare.com" not in str(v), \
                   f"{svc}: cloud-LLM host in env {k}={v!r}"
```
*Note: the api/worker env blocks in `docker-compose.yml` (lines 40-49, 75-83) currently set only `DATABASE_URL` (@postgres), `LANGFUSE_HOST` (@langfuse-web), blank `LANGFUSE_*`, and `TMPDIR` — all legitimate; the sweep passes today and would catch a future cloud key/api_base. The `model_gateway.${MODEL_PROFILE}.compose.yaml` mount (service-DNS api_base) is covered by the D-01 profile sweep, not here.*

## Final Marker/Host Lists

Distinguish **file-content MARKERS** (D-01/D-04 whole-file/env sweep) from **network HOSTS** (D-02 connect-level deny). They overlap but are not identical.

**D-01/D-04 file-content deny markers** (floor + justified additions):
| Marker | Source | Rationale |
|--------|--------|-----------|
| `CF_AIG_WRAPPER_URL` | D-01 floor | CF AI Gateway env-indirection literal used by cloud profile |
| `vertex_ai` | D-01 floor | litellm Vertex model prefix |
| `googleapis.com` | D-01 floor | Vertex/Google host substring |
| `anthropic` | D-01 floor | litellm Anthropic prefix + host |
| `anthropic.com` | D-01 floor | Anthropic host |
| `sk-` | D-01 floor | Anthropic/OpenAI key prefix |
| `sk-ant-` | **ADD (justified)** | Anthropic-specific key prefix; subset of `sk-` but explicit |
| `aiplatform.googleapis.com` | **ADD (justified)** | precise Vertex host (subset of `googleapis.com`, explicit) |
| `gateway.ai.cloudflare.com` | **ADD (justified)** | CF AI Gateway host (in case a literal URL replaces the env ref) |

> Keep `openai` OUT unless an OpenAI route is ever introduced — the stack has no OpenAI provider, and adding it risks false positives on unrelated "openai-compatible" prose (e.g. vLLM's "OpenAI-compatible server" comment in the profiles). The `sk-` marker already covers an OpenAI key leak. **[ASSUMED]** — confirm with user if OpenAI coverage is wanted.

**D-02 connect-level deny hosts:**
| Host | Confidence | Rationale |
|------|-----------|-----------|
| `api.anthropic.com` / `anthropic.com` | **VERIFIED** (empirical, this session) | Observed at the `getaddrinfo` seam for both sync + async. |
| `aiplatform.googleapis.com` + `<region>-aiplatform.googleapis.com` | **[ASSUMED]** | Vertex host family; NOT observed at the seam (Vertex dies at cred-load first — Pitfall 2). Included defensively. |
| `gateway.ai.cloudflare.com` + `*.gateway.ai.cloudflare.com` | **[ASSUMED]** | CF AI Gateway host; not exercised in the creds-free lane. |
| `MODEL_GATEWAY_BASE_URL` host when it resolves cloud | conditional | If the env var points at a public host (not localhost/service-DNS), deny it. In the default lane it is `http://localhost:4000` (loopback) — allowed. |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `api_base`-only profile assertion (LOCAL-04) | Whole-file marker sweep across 4 profiles (D-01) | This phase | Catches stray cloud refs outside `api_base`. |
| One-shot bash zero-`src/` gate (P10) | Durable env-gated loud-skip pytest | This phase | Continuous enforcement without a time-bomb. |
| `socket.create_connection` intuition for socket guards | `socket.getaddrinfo` (covers async) | This phase (empirical) | Avoids a vacuous guard against the async worker. |

**Deprecated/outdated:** none relevant; litellm 1.83.7 is the installed/pinned version.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Vertex host `aiplatform.googleapis.com` / regional variants are the right deny hosts | Final Host List, D-02 | LOW — Vertex rarely reaches the seam (Pitfall 2); the D-01 file sweep is its real guard. A wrong host string only weakens an already-belt-and-suspenders layer. |
| A2 | CF AI Gateway host is `gateway.ai.cloudflare.com` | Final Host List, D-02 | LOW — same as A1; CF path is creds-gated and not exercised in the default lane. |
| A3 | `openai`/`sk-ant-` need not be added as file markers beyond the floor | Final Marker List | LOW — no OpenAI route exists; `sk-` already covers key leaks. Confirm with user if OpenAI coverage is desired. |
| A4 | `ZERO_SRC_BASE=5092323` (current HEAD) is the correct P11 phase base | Zero-src invariant | MEDIUM — must be the spawn-prompt base (commit before first `feat(11-…)`), per the P10 convention (10-03-SUMMARY). The planner/operator sets the exact SHA at execution time; if P11 commits land before the base is recorded, the SHA shifts. |
| A5 | The worker's real model path is async (`acompletion`) | Pitfall 1 rationale | LOW — confirmed `RouterChatLiteLLM` overrides both `completion_with_retry` and `acompletion_with_retry` (`model_gateway.py:146-150`); LangGraph runs async, so async coverage is mandatory regardless. |

## Open Questions

1. **Deny-guard seam (Open Discretion #1) — RESOLVED.**
   - What we know: `socket.getaddrinfo` catches both sync (`completion`) and async (`acompletion`) litellm 1.83.7 calls; `socket.create_connection` misses async; httpx-transport hooks are per-instance and `src/`-coupled. [VERIFIED empirically.]
   - Recommendation: **patch `socket.getaddrinfo`**, host as `arg[0]`, raise only on cloud-LLM hosts, set `LITELLM_LOCAL_MODEL_COST_MAP=True`, scope autouse to not break `-m live`.

2. **Final marker/host list (Open Discretion #2) — RESOLVED with one user check.**
   - What we know: file-markers and connect-hosts differ; floors + justified additions documented above.
   - What's unclear: whether `openai`/`sk-ant-` should be added (A3). No OpenAI route exists today.
   - Recommendation: ship the lists above; ask the user only about OpenAI coverage if they want future-proofing.

3. **Durable zero-`src/` invariant (Open Discretion #3) — RESOLVED with a trade-off the user should ratify.**
   - What we know: a true trilemma — (a) always in `make test`, (b) fixed/hardcoded base, (c) survives future src edits — pick two. Hardcoded-always-on is a time-bomb; branch-relative `main...HEAD` is vacuous on `main` (where `make test` runs post-merge — [VERIFIED empty this session]).
   - Recommendation: **env-gated loud-skip pytest** (`ZERO_SRC_BASE`) mirroring `pg_dsn`. Default `make test` loud-skips; the phase verify/CI run exports the base SHA to enforce. This is the only formulation that mirrors repo convention AND doesn't time-bomb. (If the user insists on always-on enforcement during P11 only, keep the P10-style one-shot bash gate *in addition*, scoped to this phase.)

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `.venv/bin/python` | canonical test interpreter | ✓ | 3.14 | none (bare PATH python lacks deps) |
| `litellm` | deny-guard seam (observed) | ✓ | 1.83.7 | none — pinned dependency |
| `httpx` | transport behind litellm | ✓ | 0.28.1 | none |
| `pyyaml` | profile/compose parse | ✓ | installed | none |
| `git` CLI | durable zero-`src/` `git diff` | ✓ | (work tree) | loud-skip when `ZERO_SRC_BASE` unset |
| `docker` CLI | NOT needed by P11 CI tests (compose env sweep reads the YAML statically) | n/a | — | the D-04 sweep parses `docker-compose.yml` text, no docker daemon |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** the durable zero-`src/` test loud-skips when `ZERO_SRC_BASE` is unset (by design).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (repo default) |
| Config file | `pyproject.toml` markers (`live`); `make test` = `pytest -q -m "not live"` |
| Quick run command | `.venv/bin/python -m pytest -q tests/test_offline_deny_guard.py tests/test_offline_compose_env.py tests/test_local_profiles.py tests/test_zero_src_invariant.py` |
| Full suite command | `PYTHONPATH=src .venv/bin/python -m pytest -q -m "not live"` (i.e. `make test`) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OFFLINE-01 | `.env.offline.example` blanks cloud-LLM creds, local api_base via swap; RUNBOOK section | unit (file-content) + manual (RUNBOOK) | `pytest tests/test_offline_posture_env.py -x` (sweep over `.env.offline.example`) | ❌ Wave 0 |
| OFFLINE-02 | 4 profiles + compose env: no cloud api_base / no valued cloud key; cloud.yaml trips (negative control) | unit (config-validation) | `pytest tests/test_local_profiles.py tests/test_offline_compose_env.py -x` | ⚠️ EXTEND `test_local_profiles.py` + ❌ new compose-env file |
| OFFLINE-03 | default creds-free lane resolves no cloud-LLM host; anthropic positive control (sync+async) trips | unit (autouse deny-guard) | `pytest tests/test_offline_deny_guard.py -x` | ❌ Wave 0 |
| (guardrail) | zero `src/` change since phase base | unit (env-gated loud-skip) | `ZERO_SRC_BASE=<sha> pytest tests/test_zero_src_invariant.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** the quick-run command above for the touched file(s).
- **Per wave merge:** `make test` (full `-m "not live"` lane).
- **Phase gate:** `make test` green + `ZERO_SRC_BASE=<base> make test` (or one-shot `git diff <base>..HEAD -- src/` empty) before `/gsd:verify-work`.

### Wave 0 Gaps
- [ ] `tests/test_offline_deny_guard.py` — covers OFFLINE-03 (deny-guard + positive controls + representative path)
- [ ] `tests/test_offline_compose_env.py` — covers OFFLINE-02 (compose api/worker env sweep, D-04)
- [ ] `tests/test_offline_posture_env.py` — covers OFFLINE-01 (sweep over `.env.offline.example`); may fold into the compose-env file
- [ ] `tests/test_zero_src_invariant.py` — durable zero-`src/` guardrail
- [ ] EXTEND `tests/test_local_profiles.py` — add 2 compose profiles, `_SERVICE_DNS` allowlist, whole-file sweep, cloud.yaml negative control (D-01)
- [ ] `.env.offline.example` + RUNBOOK "Offline / no-egress posture" section (artifacts, not tests)
- [ ] Framework install: none — pytest/pyyaml/litellm/httpx already present

## Security Domain

> `security_enforcement` assumed enabled. This phase IS a security posture (no-cloud-LLM-egress assertion), so the security framing is the whole point.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | no auth surface added (test/config only) |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | partial | the marker/host lists ARE the validation rules over config; keep them precise (no over-broad `googleapis.com` host match that flags non-Vertex Google APIs) |
| V6 Cryptography | no | no crypto; `.env.offline.example` blanks creds, never adds them |
| V10 Malicious Code / V14 Config | **yes** | egress configuration hardening: the sweep + deny-guard assert the no-cloud-LLM-egress invariant; `.env.offline.example` keeps cloud-LLM creds blank (mirrors P10 T-10-03-02 `.env.example` cleanliness) |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Stray cloud `api_base`/key leaks into a "local" profile | Information Disclosure | D-01 whole-file marker sweep across all 4 profiles + cloud.yaml negative control |
| Valued cloud-LLM key reaches the assembled compose stack | Information Disclosure | D-04 compose api/worker env sweep |
| Default lane silently egresses to a cloud LLM (esp. via async path) | Information Disclosure / Exfiltration | D-02 `socket.getaddrinfo` deny-guard covering sync + async |
| Vacuous guard (passes for the wrong reason) | (assurance gap) | `anthropic/` positive control (sync+async) + cloud.yaml negative control + representative routed path |
| Unintended `src/` change defeats the zero-`src/` guardrail | Tampering | durable env-gated `git diff` zero-`src/` pytest |

## Sources

### Primary (HIGH confidence)
- Empirical, this session (`.venv/bin/python`): litellm 1.83.7 / httpx 0.28.1; `socket.getaddrinfo` catches sync+async, `socket.create_connection` misses async; `api.anthropic.com` observed at the seam; Vertex dies at `DefaultCredentialsError` pre-connect; `LITELLM_LOCAL_MODEL_COST_MAP=True` suppresses the `raw.githubusercontent.com` fetch; `git diff main...HEAD -- src/` empty on `main`.
- Repo files: `tests/test_local_profiles.py`, `tests/test_d06_chokepoint.py`, `tests/conftest.py`, `tests/test_compose_config.py`, `src/agent_mesh/worker/model_gateway.py`, all 4 profiles + `model_gateway.cloud.yaml`, `docker-compose.yml`, `.env.example`, `Makefile`, `RUNBOOK.md`.
- `.planning/phases/11-offline-no-egress-posture/11-CONTEXT.md` (D-01..D-04), `.planning/REQUIREMENTS.md` (OFFLINE-01/02/03), `.planning/ROADMAP.md` (Phase 11), `.planning/phases/10-full-stack-local-compose/10-SECURITY.md` (Audit Note 1), `.planning/phases/10-full-stack-local-compose/10-03-SUMMARY.md` (phase-base SHA convention).

### Secondary (MEDIUM confidence)
- litellm `LITELLM_LOCAL_MODEL_COST_MAP` behavior (documented switch; confirmed empirically here).

### Tertiary (LOW confidence)
- Vertex/CF AI Gateway host strings (`aiplatform.googleapis.com`, `gateway.ai.cloudflare.com`) — ASSUMED, not observed at the seam (Vertex/CF not exercised in creds-free lane). Defensive belt-and-suspenders only; the file-marker sweep is the real Vertex/CF guard.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all deps installed/pinned, versions verified.
- Architecture (seam choice + patterns): HIGH — deny-guard seam empirically proven; sweep/compose patterns mirror existing repo tests.
- Pitfalls: HIGH — Pitfalls 1-3 and 5 each empirically reproduced this session.
- Marker/host lists: MEDIUM — Anthropic host VERIFIED; Vertex/CF hosts ASSUMED (defensive).
- Durable zero-`src/` formulation: HIGH on the trilemma + repo branching reality (verified); MEDIUM on the exact base SHA (A4, set at execution time).

**Research date:** 2026-06-11
**Valid until:** 2026-07-11 (stable; only a litellm/httpx major bump could move the transport seam — re-verify `getaddrinfo` coverage if either is upgraded)
