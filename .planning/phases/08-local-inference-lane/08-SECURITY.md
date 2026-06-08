---
phase: 08
slug: local-inference-lane
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-08
---

# Phase 08 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (both 08-01-PLAN and 08-02-PLAN carry `<threat_model>` blocks);
> all dispositions verified CLOSED against the implementation. Scope this phase is
> config/Makefile/docs/tests only — zero `src/` change (`git diff 83ff1d3..HEAD -- src/` empty).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| local profile config → model backend | A profile's per-route `api_base` chooses where model traffic egresses. A loopback URL keeps it on-box; a cloud URL would leak egress out of an "offline" lane. | Prompt/response model traffic (potentially sensitive) |
| `make use-*` swap → active config | `make use-*` overwrites `config/model_gateway.config.yaml` (the active profile `build_router` reads). A wrong restore source would leave a stale/cloud config active. | Active routing/egress configuration |
| run targets → CI | `run-vllm`/`run-ollama` start real backends; wiring them into `make test`/CI would make CI depend on a GPU/Ollama and could trigger model egress. | CI execution + model egress |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-08-01 | Information Disclosure | config/model_gateway.{vllm,ollama}.yaml | mitigate | Both local profiles are egress-free by construction: every route `api_base` is loopback-only (`http://localhost:8000/v1` vLLM, `http://localhost:11434` Ollama); cloud `high-complexity-vertex` route dropped; all cloud env-refs stripped (`CF_AIG_WRAPPER_URL`, `vertex_*`, `ANTHROPIC_API_KEY`, `x-gateway-shared-secret`). Inert `general_settings.master_key` (never read by `build_router`, D-09) intentionally retained — not a cloud provider key. | closed |
| T-08-02 | Information Disclosure | Makefile run/swap + active config | mitigate | `use-vllm`/`use-ollama` swap in ONLY the egress-free Plan-01 profiles; `use-cloud` restores from the pristine cloud anchor via `cp` (not `git checkout`, Pitfall 5); `run-vllm`/`run-ollama` are best-effort operator-only targets kept out of `make test`/CI (D-07). LOCAL-04 test further asserts every swapped-in profile's `api_base` is loopback and free of cloud markers, constructing `build_router` with no network. | closed |
| T-08-SC | Tampering | npm/pip/cargo installs | accept | No Python packages installed this phase (config/Makefile/docs/tests only; `git diff -- src/` empty). vLLM/Ollama are operator-installed local runtimes invoked best-effort by `make run-*`, never project deps — no install surface to audit. | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Verification Evidence

| Threat | Check | Result |
|--------|-------|--------|
| T-08-01 | Negative greps on both local profiles (`high-complexity-vertex`, `CF_AIG_WRAPPER_URL`, `vertex_`, `anthropic`, `x-gateway-shared-secret`) | 10/10 return 0 |
| T-08-01 | `api_base` loopback-only (python set/value asserts on vllm + ollama) | pass |
| T-08-01 | LOCAL-04 `tests/test_local_profiles.py` (loopback + no-cloud-marker + offline `build_router`) | 8 passed |
| T-08-02 | `make -n test` references to `run-vllm`/`run-ollama` | 0 (run targets out of CI) |
| T-08-02 | `make -n use-cloud` restores from `config/model_gateway.cloud.yaml` via `cp` | confirmed |
| T-08-02 | Active config restored byte-identical after profile swap during review | `diff` clean |
| T-08-SC | `git diff 83ff1d3..HEAD -- src/` | empty (zero src/ change) |

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-08-01 | T-08-SC | This phase installs no packages; local model runtimes (vLLM/Ollama) are operator-installed, invoked best-effort, never project deps — no install/supply-chain surface introduced. | robertli | 2026-06-08 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-08 | 3 | 3 | 0 | /gsd:secure-phase (register authored at plan time; short-circuit verify) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-08
