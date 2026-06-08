---
phase: 08-local-inference-lane
plan: 02
subsystem: local-inference-tooling
tags: [local-inference, vllm, ollama, makefile, runbook, config-validation, test]
requires:
  - "config/model_gateway.vllm.yaml (Plan 08-01) — vLLM local profile under test/swap"
  - "config/model_gateway.ollama.yaml (Plan 08-01) — Ollama local profile under test/swap"
  - "config/model_gateway.cloud.yaml (Plan 08-01) — pristine restore anchor for make use-cloud"
provides:
  - "Makefile run-vllm/run-ollama/use-vllm/use-ollama/use-cloud targets (LOCAL-01/02/03 tooling)"
  - "tests/test_local_profiles.py — LOCAL-04 config-validation guard (default lane, no network)"
  - "RUNBOOK.md Local inference lane section (LOCAL-03)"
affects:
  - "Phase 10 (compose) — operators stand up a local backend via run-vllm/run-ollama + use-* swap"
  - "Phase 11 (no-egress) — LOCAL-04 loopback/no-cloud-marker assertions are a sibling guard to OFFLINE-02"
tech-stack:
  added: []
  patterns:
    - "cp-based reversible profile file-swap (NOT git checkout, Pitfall 5) — works on a dirty tree / non-git export"
    - "Best-effort operator-only run targets, deliberately absent from the test/CI path (D-07)"
    - "Mirror tests/test_d06_chokepoint.py config-load pattern; INVERT api_base assertion (loopback, not CF wrapper)"
    - "Baked model-matched tool-call parser in run-vllm (hermes/Qwen2.5); parser caveat duplicated to RUNBOOK so it survives a hand-run backend (D-08)"
key-files:
  created:
    - tests/test_local_profiles.py
  modified:
    - Makefile
    - RUNBOOK.md
decisions:
  - "Canonical test interpreter is .venv/bin/python (litellm 1.83.7 present); the bare PATH python is 3.14 without deps — a pre-existing env note, not introduced here. All default-lane suites (test_d06_chokepoint, test_model_gateway_router) require the venv likewise."
  - "RUNBOOK section inserted after the WHOLE Local Smoke Checks section (incl. the Postgres subsection), before Credentials & live lane — not fragmenting the Postgres subsection."
  - "run-vllm/run-ollama explanatory comments live on own-line # at column 0 (not inline on recipe lines) to keep make -n output clean and avoid tab/separator hazards."
metrics:
  duration: ~12 min
  completed: 2026-06-08
---

# Phase 8 Plan 02: Local-Inference Tooling, Test & RUNBOOK Summary

Wired the Plan-01 local profiles into operator-facing tooling and a CI-safe guard: five Makefile targets (best-effort `run-vllm`/`run-ollama` backends + reversible `cp`-based `use-vllm`/`use-ollama`/`use-cloud` profile swap), the LOCAL-04 config-validation test (parametrized over both local profiles, default lane, no network), and a RUNBOOK "Local inference lane" section — completing LOCAL-01..04 and making the local lane usable, provable, and documented.

## What Was Built

| Task | Artifact | Commit |
|------|----------|--------|
| 1 | `Makefile` — five targets: `run-vllm` (`vllm serve … --enable-auto-tool-choice --tool-call-parser hermes`, D-08), `run-ollama` (`ollama pull && ollama serve`), `use-vllm`/`use-ollama`/`use-cloud` (`cp` swap/restore, D-01/D-02/Pitfall 5). All five added to `.PHONY` + `help`; run targets kept out of `test`/CI (D-07). | cb7d0dc |
| 2 | `tests/test_local_profiles.py` — LOCAL-04 guard, 4 parametrized tests × 2 profiles = 8 cases: three exact deployment names (Pitfall 3), loopback api_base + no cloud markers (inverted vs test_d06_chokepoint), no `high-complexity-vertex` (D-06), offline `build_router` → real `litellm.Router` (Pitfall 6). No `importorskip` (matches the non-skipping router test). | c3d8418 |
| 3 | `RUNBOOK.md` — "Local inference lane" section: run each backend (best-effort, may fail without GPU/Ollama), file-swap profile selection with honest git-dirty disclosure, tool-calling caveat + matched parser flags (hermes/Qwen2.5, llama3_json/Llama-3.1, never cross), and the `/v1` vs no-`/v1` api_base gotcha. | 1738276 |

## Acceptance Criteria — Verified

- **Task 1:** `make -n use-cloud/use-vllm/use-ollama` print the exact `cp …` recipes; `make -n run-vllm` includes `vllm serve` + `--enable-auto-tool-choice` + `--tool-call-parser hermes`; `make -n run-ollama` includes `ollama pull` + `ollama serve`; `.PHONY` carries all five; `run-vllm` count = 4 (≥2); `make -n test` recipe unchanged (`pytest -q -m "not live"`, no run-* reference). PASS.
- **Task 2:** `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_local_profiles.py` → 8 passed. Greps: `build_router`=5 (≥1), `high-complexity-vertex`=3 (≥1), loopback present, `importorskip`=0. PASS.
- **Task 3:** `## Local inference lane` heading present; all five `make` targets named; parser caveat (hermes|llama3_json) present; git-dirty disclosure present; `/v1` gotcha present. PASS.
- **Suite-wide:** full default suite `PYTHONPATH=src .venv/bin/python -m pytest -q -m "not live"` → **312 passed, 9 skipped, 23 deselected**. Green.

## Key Decisions / Notes

- **Interpreter:** the project's canonical default-lane interpreter is `.venv/bin/python` (litellm 1.83.7). The bare `python` on PATH is 3.14 without project deps — a pre-existing environment note (STATE/memory), not introduced by this plan. The new test imports `litellm` exactly as the existing `test_d06_chokepoint.py` / `test_model_gateway_router.py` do, so it shares their lane. Under the venv all 8 cases pass and the full suite is green.
- **RUNBOOK placement:** inserted after the entire "Local Smoke Checks" section — *after* its `### Postgres durable checkpointer lane` subsection — so the Postgres subsection stays attached to its parent; placed immediately before `## Credentials & live lane`.
- **Runtime-only correctness lives in config + RUNBOOK, not the test:** the `/v1` (vLLM) vs no-`/v1` (Ollama) api_base path is a 404-at-call-time trap the offline LOCAL-04 build cannot catch (Pitfall 1/6) — documented in RUNBOOK and baked into the profiles, exactly as Plan 01 noted.

## Deviations from Plan

None — plan executed exactly as written. (The bare-`python` `ModuleNotFoundError: litellm` during the first test run is an interpreter-selection artifact of this box, not a code issue; the canonical `.venv` interpreter — the one the rest of the default suite already requires — runs all 8 cases green. No code change was needed.)

## Threat Surface

T-08-02 (Information Disclosure — local lane silently retaining cloud egress) is mitigated and asserted: `use-vllm`/`use-ollama` swap in only the egress-free Plan-01 profiles; `use-cloud` restores via `cp` from the pristine cloud anchor (not `git checkout`, Pitfall 5); `run-vllm`/`run-ollama` are best-effort operator-only targets kept out of `make test`/CI (verified: `make -n test` recipe unchanged). The LOCAL-04 test further asserts every route's api_base is loopback and carries no cloud markers, constructing `build_router` with no network. T-08-SC (install tampering): no Python packages installed this phase — config/Makefile/docs/tests only; vLLM/Ollama are operator-installed runtimes invoked best-effort, never project deps. No new threat surface beyond the plan's threat model.

## Self-Check: PASSED

- FOUND: Makefile (modified — 5 new targets)
- FOUND: tests/test_local_profiles.py (94 lines)
- FOUND: RUNBOOK.md (Local inference lane section, +81 lines)
- FOUND commit cb7d0dc (Makefile targets)
- FOUND commit c3d8418 (LOCAL-04 test)
- FOUND commit 1738276 (RUNBOOK section)
