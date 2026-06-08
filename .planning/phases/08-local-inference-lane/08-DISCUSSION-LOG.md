# Phase 8: Local Inference Lane - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-08
**Phase:** 08-local-inference-lane
**Areas discussed:** Profile selection mechanism, Local model topology, Local fallback chain shape, make-target ambition + tool-calling caveat

---

## A — Profile selection mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Make-managed swap + restore | make use-vllm/use-ollama copy profile onto config.config.yaml; make use-cloud restores cloud default; RUNBOOK documents. Reversible. | ✓ |
| RUNBOOK manual cp only | No automation; user cp's the profile themselves. No reversible restore path. | |
| Gitignore + profile-only | Stop tracking config.config.yaml, generate active one. Larger structural change. | |

**User's choice:** Make-managed swap + restore (D-01/D-02).
**Notes:** Forced by build_router's hardcoded DEFAULT_CONFIG_PATH (model_gateway.py:35) — no env seam, and adding one is a forbidden src/ change. LOCAL-04 test calls build_router on the profile path directly, independent of the swap (D-03).

---

## B — Local model topology

| Option | Description | Selected |
|--------|-------------|----------|
| One shared model, 3 nominal tiers | All 3 deployment names route to the same local served model; tiering nominal. Realistic for one box. | ✓ |
| Distinct model per tier | low/medium/high each a different local model. True tiering, heavier VRAM. | |

**User's choice:** One shared model, 3 nominal tiers (D-04).
**Notes:** Model must be tool-call-capable instruct (D-05) — Qwen2.5-Instruct default / Llama-3.1-Instruct alt; researcher pins exact ids + matching vLLM tool-call-parser. Distinct-per-tier deferred.

---

## C — Local fallback chain shape

| Option | Description | Selected |
|--------|-------------|----------|
| Self-contained 3-deployment chain | Drop cloud high-complexity-vertex 4th; fallbacks stay within the 3 local names. Clean for Phase 11 no-egress. | ✓ |
| Carry a local 4th route | Mirror cloud chain with a 4th local route. Extra route the no-egress test must reason about. | |

**User's choice:** Self-contained 3-deployment chain (D-06).
**Notes:** Exact fallback edges left to the planner; shape (within-3-names, no cloud route) is fixed.

---

## D — make-target ambition + tool-calling caveat

| Option | Description | Selected |
|--------|-------------|----------|
| Real best-effort run + baked tool-parser flags | Targets run vllm serve / ollama pull+serve, local-only never CI; tool-call-parser flags baked into run-vllm; caveat also in RUNBOOK. | ✓ |
| Real run, caveat in RUNBOOK only | Targets run the backend minimally; caveat + flags only in RUNBOOK prose. | |
| Document-only targets | make targets echo instructions; user runs backend manually. Safest, least real. | |

**User's choice:** Real best-effort run + baked tool-parser flags (D-07/D-08).
**Notes:** Targets are local-only, never wired into CI / make test; may fail without GPU/Ollama (acceptable, documented). Exact parser name pinned by research to match the chosen model.

## Claude's Discretion

- Exact fallback edges within the 3 local deployment names.
- Exact local api_base ports/paths (vLLM OpenAI server vs Ollama endpoint).
- use-cloud restore mechanism (cp from saved cloud.yaml vs git checkout).
- LiteLLM route prefixes (hosted_vllm/<model>; ollama/ vs ollama_chat/<model>).

## Deferred Ideas

- Distinct-model-per-tier local topology — revisit if local tiering must be real.
- Env-driven config-path seam (MODEL_GATEWAY_CONFIG_PATH) — cleaner than file-swap but a src/ change; out of scope for the zero-src-change guardrail; future hardening milestone.
</content>
