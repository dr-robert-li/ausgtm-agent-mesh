---
phase: 08-local-inference-lane
plan: 01
subsystem: model-gateway-config
tags: [local-inference, vllm, ollama, litellm, config, egress-free]
requires: []
provides:
  - "config/model_gateway.cloud.yaml — pristine cloud restore anchor (D-02 restore source for make use-cloud)"
  - "config/model_gateway.vllm.yaml — 3-tier local vLLM profile (LOCAL-01)"
  - "config/model_gateway.ollama.yaml — 3-tier local Ollama profile (LOCAL-02)"
affects:
  - "Plan 08-02 (make use-*/run-* targets + LOCAL-04 build_router test + RUNBOOK consume these profiles)"
  - "Phase 10 (compose) stands up a local model backend against these profiles"
  - "Phase 11 (no-egress) asserts these local profiles carry no cloud api_base / cloud env-refs"
tech-stack:
  added: []
  patterns:
    - "Mirror cloud profile structure, repoint per-route litellm_params.model + api_base to loopback, drop high-complexity-vertex (D-06)"
    - "Self-authored egress-free header comments (NOT copied from cloud file) to keep negative greps + Phase-11 invariant clean"
    - "Unquoted literal value lines so substring grep gates match"
key-files:
  created:
    - config/model_gateway.cloud.yaml
    - config/model_gateway.vllm.yaml
    - config/model_gateway.ollama.yaml
  modified: []
decisions:
  - "vLLM api_base ends in /v1 (LiteLLM hosted_vllm appends only chat/completions; Pitfall 1, settled vs installed litellm 1.83.7)"
  - "Ollama uses ollama_chat/ prefix (/api/chat for tool-calling) + api_base http://localhost:11434 with NO /v1 (Pitfall 2)"
  - "Fallback chain low->[medium], medium->[high], high->[medium] — self-contained, no cloud-named route, no high->high self-ref (D-06)"
  - "general_settings + success/failure callbacks kept for structural parity (inert locally; build_router never reads general_settings — D-09)"
metrics:
  duration: ~10 min
  completed: 2026-06-08
---

# Phase 8 Plan 01: Local-Backend Config Profiles Summary

Authored the three foundation config profiles of the local inference lane: a byte-identical pristine cloud restore anchor plus two egress-free local profiles (vLLM via `hosted_vllm/*` on `:8000/v1`, Ollama via `ollama_chat/*` on `:11434` no-`/v1`), each routing the three frozen deployment tiers to a single shared local model with a self-contained fallback chain and zero cloud env-refs.

## What Was Built

| Task | Artifact | Commit |
|------|----------|--------|
| 1 | `config/model_gateway.cloud.yaml` — byte-identical copy of today's active cloud profile; restore source for `make use-cloud` (D-02). Retains all four routes, CF wrapper indirection, vertex/anthropic env-refs (correct for the cloud lane). | c978c67 |
| 2 | `config/model_gateway.vllm.yaml` — 3 frozen tiers (low/medium/high-complexity) → `hosted_vllm/Qwen/Qwen2.5-7B-Instruct`, loopback `api_base http://localhost:8000/v1` (/v1 required). Drops `high-complexity-vertex`; self-contained fallback chain; no cloud env-refs (LOCAL-01). | 09fdb97 |
| 3 | `config/model_gateway.ollama.yaml` — same clean structure, `ollama_chat/qwen2.5:7b-instruct`, loopback `api_base http://localhost:11434` (no /v1). Drops `high-complexity-vertex`; no cloud env-refs (LOCAL-02). | 7dbcd9a |

## Acceptance Criteria — Verified

- **Task 1:** `diff config/model_gateway.cloud.yaml config/model_gateway.config.yaml` → empty (byte-identical). `high-complexity-vertex` present (route + fallback ref); `CF_AIG_WRAPPER_URL` present. PASS.
- **Task 2 (vLLM):** 3 exact deployment names; literal `model: hosted_vllm/Qwen/Qwen2.5-7B-Instruct` ×3; literal `api_base: http://localhost:8000/v1` ×3; negative greps (high-complexity-vertex, CF_AIG_WRAPPER_URL, vertex_, anthropic, x-gateway-shared-secret) all 0; python set-equality + api_base assertion PASS.
- **Task 3 (Ollama):** 3 exact deployment names; literal `model: ollama_chat/qwen2.5:7b-instruct` ×3; literal `api_base: http://localhost:11434` ×3; `/v1` on api_base lines = 0; negative greps all 0; python assertion PASS.

## Key Decisions / Notes

- **Header comments are self-authored, not copied** from the cloud file — the cloud header names Cloudflare/Anthropic/Vertex/shared-secret, and the negative greps are case-sensitive, so a copied header could pass the greps yet still violate the "NO cloud env-refs" must-have and trip the Phase-11 invariant. Local headers are clean.
- **Value lines unquoted** so the literal-substring grep gates match (a YAML quote would pass the python assert but fail the grep).
- **Runtime tool-calling correctness lives in config + RUNBOOK, not the test** — the `/v1` (vLLM) and `ollama_chat/` (Ollama) choices are correct here; LOCAL-04 (Plan 02) builds offline and cannot catch a wrong api_base path (Pitfall 1/6). Captured in the profile header comments.

## Deviations from Plan

None — plan executed exactly as written.

## Threat Surface

T-08-01 (Information Disclosure — local profile silently retaining cloud egress) is mitigated by construction and asserted: both local profiles carry loopback-only `api_base`, drop `high-complexity-vertex`, and the five cloud-marker negative greps all return 0. The retained inert `general_settings.master_key: os.environ/MODEL_GATEWAY_MASTER_KEY` is a prod-proxy field never read by `build_router` (D-09) — not a cloud provider key — and is intentionally kept for structural parity.

No new threat surface introduced beyond the plan's threat model.

## Self-Check: PASSED

- FOUND: config/model_gateway.cloud.yaml (85 lines)
- FOUND: config/model_gateway.vllm.yaml (67 lines)
- FOUND: config/model_gateway.ollama.yaml (68 lines)
- FOUND commit c978c67 (cloud anchor)
- FOUND commit 09fdb97 (vLLM)
- FOUND commit 7dbcd9a (Ollama)
