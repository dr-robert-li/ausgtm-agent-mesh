# Phase 2: Real Orchestration Engine - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-05
**Phase:** 2-real-orchestration-engine
**Areas discussed:** P2/P3 sequencing, Sandbox hardening on macOS, Roster realness under stubbed model

---

## P2/P3 Sequencing

| Option | Description | Selected |
|--------|-------------|----------|
| Keep layering (stub model in P2) | Durability → orchestration → model plane. P2 proves topology/checkpointer/interrupts with a fake/deterministic model; no model creds needed. Real-model behaviour proven P3/P5. | ✓ |
| Swap — real model in P2 | Pull the live LiteLLM gateway forward to run the roster against real models now. Exercises real behaviour sooner but couples P2 to creds/budget and breaks the dependency layering. | |

**User's choice:** Keep layering (stub model in P2)
**Notes:** ROADMAP openly flagged the swap as available; user declined it. Confirms the intended horizontal-layer phasing.

---

## Sandbox hardening (local dev = macOS)

| Option | Description | Selected |
|--------|-------------|----------|
| Docker required for sandbox exec | Hardened container path (cgroup memory) is the only real exec path; if Docker absent, skip/refuse — never run unbounded. | ✓ |
| Docker-or-refuse, documented degraded note | Same refuse-not-fail-open invariant, plus an explicit documented degraded/skip path so make test/make smoke stay green on macOS. | |
| rlimit where supported, else refuse | Keep rlimit on Linux as fallback; refuse on platforms rejecting RLIMIT_AS (macOS). Container path primary. | |

**User's choice:** Docker required for sandbox exec
**Notes:** Closes the current fail-open `RLIMIT_AS` bug directly. CONTEXT.md captures the implication (D-03a) that the memory-enforcement test should pytest-skip cleanly when Docker is absent so local suites stay green — to confirm during planning.

---

## Roster realness under the stubbed model

| Option | Description | Selected |
|--------|-------------|----------|
| Real graph, deterministic node outputs | Build the actual LangGraph supervisor + 4 declared nodes; each runs for real, emits deterministic stub output instead of calling a model. Delegation + roster log genuinely exercised; real models become a config change in P3. | ✓ |
| Thin supervisor pass-through | Minimal supervisor that names/logs the roster and routes once, deferring real delegation topology to Phase 3. | |

**User's choice:** Real graph, deterministic node outputs
**Notes:** Ensures ORCH-01 ("delegates to the four declared roster members; roster size logged at startup") is met for real, not faked, while staying credential-free.

## Claude's Discretion

- Checkpointer backend choice + restart-simulation mechanism (within Postgres-prod constraint) — deferred to research/planning.
- Internal LangGraph node/state-schema shape.

## Deferred Ideas

- Real-model agent behaviour / live LiteLLM gateway — Phase 3/5.
- Langfuse graph-span trace wiring (`trace_id`) — Phase 3 (OBS-01/02).
- Production sandbox isolation (gVisor/Cloud Run Job, signed images, egress controls) — production hardening, out of v1.

## Items routed to research (not user decisions — see CONTEXT.md <specifics>)

- Interrupt ↔ Phase-1 signed-token/ledger binding (highest priority).
- Checkpointer backend lib + simulated >60-min restart proof.
- `deepagents>=0.0.2` version/API stability.
- Docker hardened-container invocation specifics on macOS.
