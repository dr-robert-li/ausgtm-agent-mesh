---
phase: 08-local-inference-lane
verified: 2026-06-08T11:45:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
deferred:
  - truth: "Full no-cloud-env-ref sweep over entire local profile file (beyond api_base)"
    addressed_in: "Phase 11"
    evidence: "REQUIREMENTS.md OFFLINE-02: A test asserts local/offline model profiles contain NO cloud api_base and no cloud-key env references — egress-free by construction"
  - truth: "WR-02: litellm_params fields other than api_base not swept by LOCAL-04"
    addressed_in: "Phase 11"
    evidence: "Phase 11 OFFLINE-02 sweep covers the whole litellm_params blob"
---

# Phase 8: Local Inference Lane Verification Report

**Phase Goal:** Add local-model profiles so the mesh runs inference fully on-box behind the existing LiteLLM Router — vLLM (GPU) and Ollama (CPU/dev) — without touching agent or gateway code.
**Verified:** 2026-06-08T11:45:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Zero-src Guardrail (Headline Constraint)

`git diff --stat 83ff1d3..HEAD -- src/` produces no output (empty).

The complete changeset since the planning commit (83ff1d3) is:

| File | Change |
|------|--------|
| `.planning/REQUIREMENTS.md` | updated (LOCAL-01..04 marked complete) |
| `.planning/ROADMAP.md` | updated (Phase 8 marked complete) |
| `.planning/STATE.md` | updated (session continuity) |
| `.planning/phases/08-local-inference-lane/08-01-SUMMARY.md` | new |
| `.planning/phases/08-local-inference-lane/08-02-SUMMARY.md` | new |
| `.planning/phases/08-local-inference-lane/08-REVIEW.md` | new |
| `Makefile` | extended (+34 lines) |
| `RUNBOOK.md` | extended (+88 lines) |
| `config/model_gateway.cloud.yaml` | new (+85 lines) |
| `config/model_gateway.ollama.yaml` | new (+68 lines) |
| `config/model_gateway.vllm.yaml` | new (+67 lines) |
| `tests/test_local_profiles.py` | new (+94 lines) |

No `src/` file appears. Zero-src guardrail: VERIFIED.

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | `config/model_gateway.vllm.yaml` routes all three tiers to a local vLLM endpoint via `hosted_vllm/*`; `make run-vllm` starts the server | ✓ VERIFIED | Config confirmed: 3 routes x `hosted_vllm/Qwen/Qwen2.5-7B-Instruct`, `api_base: http://localhost:8000/v1`. `make -n run-vllm` prints `vllm serve Qwen/Qwen2.5-7B-Instruct --port 8000 --enable-auto-tool-choice --tool-call-parser hermes`. Phase acceptance bar is `make -n` (plan 08-02 Task 1 AC verbatim). Operator runtime startup is best-effort/deferred per D-07. |
| SC-2 | `config/model_gateway.ollama.yaml` routes all three tiers to a local Ollama endpoint via LiteLLM; `make run-ollama` starts/pulls it | ✓ VERIFIED | Config confirmed: 3 routes x `ollama_chat/qwen2.5:7b-instruct`, `api_base: http://localhost:11434`. `make -n run-ollama` prints `ollama pull qwen2.5:7b-instruct && ollama serve`. Phase acceptance bar is `make -n`. Operator runtime startup is best-effort/deferred per D-07. |
| SC-3 | RUNBOOK documents the local-inference lane: how to run each backend, how the Router selects a profile, and the tool-calling model-capability caveat | ✓ VERIFIED | `## Local inference lane` section at RUNBOOK.md:96. All five `make` targets named. Tool-call-parser caveat (hermes/Qwen2.5, llama3_json/Llama-3.1) at lines 154-160. `/v1` vs no-`/v1` api_base gotcha at lines 171-174. Git-dirty disclosure at lines 132-137. WR-01 fix (d06 chokepoint warning) confirmed at lines 139-142. |
| SC-4 | A config-validation test asserts each local profile defines all three deployment names with a local `api_base` and builds via `build_router` with no network | ✓ VERIFIED | `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_local_profiles.py` — **8 passed in 1.61s**. Full default suite: **312 passed, 9 skipped, 23 deselected** (no regression). |

**Score: 4/4 roadmap success criteria verified**

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `config/model_gateway.cloud.yaml` | Pristine cloud restore anchor (byte-identical to active config) | ✓ VERIFIED | `diff config/model_gateway.cloud.yaml config/model_gateway.config.yaml` — identical. Contains `high-complexity-vertex` (2 occurrences) and `CF_AIG_WRAPPER_URL` (4 occurrences). 85 lines. |
| `config/model_gateway.vllm.yaml` | 3-tier local vLLM profile — no cloud env-refs | ✓ VERIFIED | 67 lines. All negative greps 0. 3 exact deployment names. `hosted_vllm/Qwen/Qwen2.5-7B-Instruct` x3. `api_base: http://localhost:8000/v1` x3. |
| `config/model_gateway.ollama.yaml` | 3-tier local Ollama profile — no cloud env-refs | ✓ VERIFIED | 68 lines. All negative greps 0. 3 exact deployment names. `ollama_chat/qwen2.5:7b-instruct` x3. `api_base: http://localhost:11434` x3. No `/v1` on any api_base line. |
| `Makefile` | 5 new targets: run-vllm, run-ollama, use-vllm, use-ollama, use-cloud | ✓ VERIFIED | All 5 in `.PHONY` line. `run-vllm` count=4, `run-ollama` count=4, `use-vllm` count=3, `use-ollama` count=3, `use-cloud` count=4 (all >=2). `tool-call-parser hermes` present. Test recipe unchanged: `PYTHONPATH=$(PYTHONPATH) $(PY) -m pytest -q -m "not live"`. |
| `tests/test_local_profiles.py` | LOCAL-04 config-validation test, default lane | ✓ VERIFIED | 94 lines. `build_router` count=5. `high-complexity-vertex` count=3. `localhost` present. `importorskip` count=0. 4 parametrized tests x 2 profiles = 8 cases, all pass. |
| `RUNBOOK.md` | "Local inference lane" section | ✓ VERIFIED | Section at line 96. All 5 targets present. WR-01 fix (chokepoint failure disclosure) confirmed at lines 139-142. hermes/llama3_json caveat present. /v1 gotcha present. Git-dirty disclosure present. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `Makefile use-cloud` | `config/model_gateway.cloud.yaml` | `cp` restore | ✓ WIRED | `make -n use-cloud` — `cp config/model_gateway.cloud.yaml config/model_gateway.config.yaml` |
| `Makefile use-vllm` | `config/model_gateway.vllm.yaml` | `cp` swap | ✓ WIRED | `make -n use-vllm` — `cp config/model_gateway.vllm.yaml config/model_gateway.config.yaml` |
| `Makefile use-ollama` | `config/model_gateway.ollama.yaml` | `cp` swap | ✓ WIRED | `make -n use-ollama` — `cp config/model_gateway.ollama.yaml config/model_gateway.config.yaml` |
| `tests/test_local_profiles.py` | `agent_mesh.worker.model_gateway.build_router` | offline Router construction on each profile file | ✓ WIRED | `from agent_mesh.worker.model_gateway import build_router` + `build_router(str(_PROFILES[name]))` — 8 passed |
| `Makefile run-vllm` | vLLM tool-call parser | baked `--tool-call-parser hermes` flag | ✓ WIRED | `make -n run-vllm` — `vllm serve Qwen/Qwen2.5-7B-Instruct --port 8000 --enable-auto-tool-choice --tool-call-parser hermes` |
| `config/model_gateway.vllm.yaml` | TIER_TO_DEPLOYMENT seam | exact `model_name` values | ✓ WIRED | All three names are exactly `low-complexity`, `medium-complexity`, `high-complexity` — match the frozen seam verbatim |
| `config/model_gateway.ollama.yaml` | TIER_TO_DEPLOYMENT seam | exact `model_name` values | ✓ WIRED | Same — all three frozen names present exactly once each |

### Egress-Free Invariant (Detailed Evidence)

Negative grep results (Python re.findall, whole file):

| Marker | vllm.yaml | ollama.yaml |
|--------|-----------|-------------|
| `high-complexity-vertex` | 0 | 0 |
| `CF_AIG_WRAPPER_URL` | 0 | 0 |
| `vertex_` | 0 | 0 |
| `anthropic` | 0 | 0 |
| `x-gateway-shared-secret` | 0 | 0 |

All api_base lines in vllm.yaml: `http://localhost:8000/v1` x3 (all loopback, all with `/v1`).
All api_base lines in ollama.yaml: `http://localhost:11434` x3 (all loopback, none with `/v1`).

The retained `general_settings.master_key: os.environ/MODEL_GATEWAY_MASTER_KEY` is a proxy-auth indirection that `build_router` never reads (`general_settings` not consumed by `build_router` — D-09). It is not a cloud provider credential and correctly kept for structural parity.

### Data-Flow Trace (Level 4)

Not applicable. Phase deliverables are config files, Makefile targets, a test, and documentation — not components that render dynamic data. The data-flow from profile to Router is proven by the LOCAL-04 `build_router` test (8 passed).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| LOCAL-04 test passes in default lane | `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_local_profiles.py` | 8 passed in 1.61s | ✓ PASS |
| Full default suite unaffected | `PYTHONPATH=src .venv/bin/python -m pytest -q -m "not live"` | 312 passed, 9 skipped, 23 deselected | ✓ PASS |
| `make -n use-cloud` recipe | `make -n use-cloud` | `cp config/model_gateway.cloud.yaml config/model_gateway.config.yaml` | ✓ PASS |
| `make -n use-vllm` recipe | `make -n use-vllm` | `cp config/model_gateway.vllm.yaml config/model_gateway.config.yaml` | ✓ PASS |
| `make -n run-vllm` has hermes parser flag | `make -n run-vllm` | `vllm serve ... --enable-auto-tool-choice --tool-call-parser hermes` | ✓ PASS |
| Test recipe unchanged (no run targets) | `make -n test` | `PYTHONPATH=$(PYTHONPATH) $(PY) -m pytest -q -m "not live"` — no run-vllm/run-ollama | ✓ PASS |
| vLLM server actual startup | best-effort operator step (D-07) | SKIPPED — requires GPU hardware; acceptance bar is `make -n` per plan 08-02 Task 1 AC | SKIP (by design) |
| Ollama daemon actual startup | best-effort operator step (D-07) | SKIPPED — requires Ollama installed; acceptance bar is `make -n` per plan 08-02 Task 1 AC | SKIP (by design) |

**Operator runtime note:** `make run-vllm` and `make run-ollama` are best-effort, operator-only targets (D-07). They are absent from `make test` and every CI path. Actual server startup can be validated optionally by an operator with the required hardware — see RUNBOOK.md "Local inference lane" for instructions, including the IN-02 note that on a cold Ollama box `ollama serve` may need to be running before `ollama pull`.

### Probe Execution

No probes declared in PLAN frontmatter. No `scripts/*/tests/probe-*.sh` files exist for this phase. SKIPPED.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| LOCAL-01 | 08-01, 08-02 | `config/model_gateway.vllm.yaml` routes all three tiers to local vLLM; `make run-vllm` starts server | ✓ SATISFIED | Config file verified (egress-free, 3 tiers, hosted_vllm). Makefile target recipe verified via `make -n`. |
| LOCAL-02 | 08-01, 08-02 | `config/model_gateway.ollama.yaml` routes all three tiers to local Ollama; `make run-ollama` starts/pulls | ✓ SATISFIED | Config file verified (egress-free, 3 tiers, ollama_chat). Makefile target recipe verified via `make -n`. |
| LOCAL-03 | 08-02 | RUNBOOK "Local inference lane" section: run each backend, profile selection, tool-calling caveat | ✓ SATISFIED | Section at RUNBOOK.md:96. All 5 targets named. Parser caveat (hermes/llama3_json). /v1 gotcha. Git-dirty + d06 chokepoint disclosures confirmed. |
| LOCAL-04 | 08-02 | Config-validation test: 3 exact deployment names, local api_base, offline build_router | ✓ SATISFIED | `tests/test_local_profiles.py` — 8 passed (4 tests x 2 profiles). Runs in default lane (creds-free, no network). |

Note: REQUIREMENTS.md traceability table (lines 210-213) still shows LOCAL-01..04 as "Pending" while the checkbox section (lines 115-122) shows `[x]`. This is stale doc state in the traceability table — the actual requirements are implemented and verified. Informational only; not a phase gap.

### Anti-Patterns Found

Scanned all 6 files modified/created by this phase.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | No TBD/FIXME/XXX/placeholder/return null found in phase deliverables | — | — |

No debt markers. No stub implementations. No hardcoded-empty data. No TODO/HACK markers in production-path code.

### Code Review Findings (from 08-REVIEW.md)

The code review found 0 critical, 2 warnings, 2 info findings. Their disposition:

- **WR-01 (FIXED):** RUNBOOK did not disclose that `tests/test_d06_chokepoint.py` fails while a local profile is active. Fix confirmed landed at RUNBOOK.md:139-142: "While a local profile is active, `make test` will also fail `tests/test_d06_chokepoint.py`... This is expected, not a regression... Run `make use-cloud` to restore the cloud profile before running the full suite."
- **WR-02 (ACCEPTED/DEFERRED):** LOCAL-04 inspects only `litellm_params.api_base` for cloud markers; a future regression re-introducing a credential in a different litellm_params field would not be caught here. The test docstring explicitly documents this as the scoped boundary; full no-cloud-env-ref sweep is Phase 11's OFFLINE-02. Deferred — not a Phase 8 gap.
- **IN-01:** Loopback `startswith` check would pass a `localhost`-prefixed FQDN. Not a realistic threat (config is repo-authored, not attacker-controlled). Informational.
- **IN-02:** `run-ollama` runs `ollama pull` before `ollama serve`; pull requires a running daemon on a cold box. Best-effort/operator-only target (D-07); informational.

### Deferred Items

Items not yet met but explicitly addressed in later milestone phases.

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | Full no-cloud-env-ref sweep over entire local profile file (beyond api_base) | Phase 11 | REQUIREMENTS.md OFFLINE-02: "A test asserts the local/offline model profiles contain NO cloud `api_base`... and no cloud-key env references — egress-free by construction" |
| 2 | WR-02: litellm_params fields other than api_base not swept by LOCAL-04 | Phase 11 | Phase 11 OFFLINE-02 sweep covers the whole litellm_params blob |

Note: both local profiles are confirmed clean today via the Plan 01 grep acceptance criteria (all 5 cloud markers = 0 across the entire file text). The deferred item concerns future regressions, not a current gap.

---

_Verified: 2026-06-08T11:45:00Z_
_Verifier: Claude (gsd-verifier)_
