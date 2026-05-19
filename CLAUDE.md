# CLAUDE.md — agentic coding instructions for this repo

This file is the **operating manual for any coding agent** (Claude Code,
subagents, autonomous harnesses) working in this repository. The architectural
pattern below is normative. The boundaries are non-negotiable.

If a request conflicts with these rules, refuse or escalate — do not silently
relax them.

---

## 1. What this repo is

A **local-first Python POC** of the Agentic Mesh defined in
[`agentic-mesh-reference-arch`](https://github.com/dr-robert-li/agentic-mesh-reference-arch)
`v0.1.3`. The reference repo defines contracts and invariants; this repo
implements them.

Stack: Python 3.11+, FastAPI, Temporal (local, Python SDK), Postgres+pgvector,
Slack Bolt for Python, MCP Python SDK, Anthropic Claude Agent SDK (primary)
with Bedrock and Vertex adapters as fallbacks.

First non-local deployment target: **AWS ECS Fargate**. Not Temporal Cloud.

---

## 2. Architectural design pattern

Four planes. Code lives in one of them. Cross-plane calls go through named
seams, never ad-hoc imports.

### 2.1 Entry plane — `apps/slack/`, `apps/mcp/`, `apps/api/` (read-side)

- End users live in **Slack**.
- External agents enter via **MCP** (and use it for self-loopback).
- The **API** is the source of truth and the **only write surface**.
- Slack and MCP **call the API**. They never write `Task` state directly.
  They never call the Tool Gateway directly. They never start workflows
  directly — they POST to the API, which starts workflows.

### 2.2 Control plane — `apps/api/`, `packages/policy/`, `packages/registry/`, Swarm Supervisor

- The **Orchestrator** (Temporal workflows in `packages/workflows/`) is the
  only mutator of `Task.state`.
- The **Planner/Decomposer**, **Swarm Supervisor**, **Policy/Governance
  engine**, **Evaluator**, **Contract Validator**, and **Routine & Release
  Registry** all live in or behind the API.
- The Swarm Supervisor **never writes Task state and never invokes tools**.
  It emits a spawn decision and writes a row to the **SpawnLedger**. A
  workflow picks that up and runs the child.

### 2.3 Execution plane — `packages/workflows/`, `packages/activities/`, `packages/model_gateway/`, `packages/tool_gateway/`

- **Workflows** in `packages/workflows/` are **deterministic** Temporal
  workflows. They orchestrate. They do not call model APIs, network APIs,
  databases, or clocks directly.
- **Activities** in `packages/activities/` are where side effects live —
  including **every agent SDK call**. Agent SDKs run **inside activities**,
  never inside workflows.
- **Model Gateway** (`packages/model_gateway/`) abstracts model providers.
  Default route: **direct Anthropic Claude Agent SDK**. Adapters:
  **Bedrock** (fallback), **Vertex** (fallback). Tier (`S`/`M`/`L`) is chosen
  by policy, not by the calling activity.
- **Tool Gateway** (`packages/tool_gateway/`) is the **only** code that
  holds credentials and the **only** code that calls external tool APIs
  (Slack write, Monday, Sheets, tl;dv, etc.). It enforces tool **trust
  tiers**: `read_safe`, `read_sensitive`, `write_revocable`,
  `write_destructive`, `external_egress`.

### 2.4 Persistence & telemetry plane — Postgres+pgvector, `packages/observability/`

- **Postgres + pgvector** is the system of record **for mesh state** —
  Tasks, SpawnLedger, policies, routines, releases, the five log streams.
  Vector indexes for routine retrieval and evaluator memory live in the
  same DB.
- **The Knowledge Layer is NOT a system of record.** Ground truth for
  external facts stays in the external tools (Monday, Drive, Sheets,
  Slack, HubSpot, Stripe, BigQuery, tl;dv). See §2.5.
- The **five log streams** — Event, Decision, Action, Validation,
  Evaluation — are first-class. Every state change, spawn, tool call,
  validator verdict, evaluator score, KL read/refetch, and egress check
  writes a row.
- A task must be **reconstructable from logs alone** (see
  `tests/observability/`).

### 2.5 Context and Evidence Knowledge Layer

A tenant-scoped **cache + index + evidence-pointer substrate** that gives
agents sufficient, governed, source-aware context for more capable
reasoning. KL is *not* a system of record. Authoritative state stays in
external tools. KL holds pointers + freshness + version, not ground truth.

- Entries are keyed `(tenant_id, source_system, source_id)` with optional
  `content_hash`, addressed as `kl:{tenant}:{source}/{path}#v{n}`.
- Writes are **append-only and versioned**. LLMs never write KL entries
  directly — only ingest activities do, via the Tool Gateway.
- Workflow state carries **refs/IDs** (`intake_id`, `claim_evidence_map_ref`,
  KL entry IDs, `payload_ref: blob://…`) — never raw context payloads.
- KL reads are budgeted via `evidence_fetch_budget` (`max_reads`,
  `max_refetches`, `max_stale_acceptance`), propagated to children as a
  fraction of the parent's remaining budget.

### 2.6 Intake contract and S-tier feasibility

Inbound requests from the entry plane produce an **`Intake`** artifact
*before* the Orchestrator creates a Task. Intake performs exactly three
cheap checks: **schema parse**, **tool-plan lookup**, and **one S-tier
classifier call**. Verdict is `feasible | ambiguous | infeasible`.

- **No silent escalation above S-tier at intake.** Ambiguity produces one
  disambiguating question, not an M/L cascade.
- The resulting Task references the intake via `Task.intake_id` and emits
  a `ProvenanceRef(kind=intake, ref=intake_…)`.
- **Feasibility is decided once.** It is not re-run mid-stream.

### 2.7 Egress-only verification and LLM-first claim verification

Verification against systems of record happens **only at egress** — at
the external output/action boundary — not continuously mid-stream. The
LLM proposes the output/action and a **claim-evidence map** sidecar
(`ClaimEvidenceMap`, `cem_…`); deterministic guards then enforce, in this
fixed order:

1. `schema` — payload validates against its output schema.
2. `claim_evidence_map` — sidecar present and well-formed.
3. `evidence_resolvable` — every claim's evidence ref resolves.
4. `freshness` — every evidence ref meets freshness policy.
5. `source_authority` — evidence sources are authoritative for the
   predicate being asserted.
6. `tenancy` — hard refuse on cross-tenant evidence leakage.
7. `tier_and_policy` — tool tier, policy, HITL thresholds; may
   `require_hitl`.
8. `budget` — `evidence_fetch_budget` and other budgets not exceeded.

Outcomes: `pass`, `blocked`, `blocked_require_hitl`. A blocked egress
produces an `EgressCheckRecord` (`egc_…`) and a `decision_kind:
egress_blocked` Decision-log entry. A `require_hitl` outcome moves the
Task to `AWAITING_HITL` with `hitl.from_state = EGRESS_CHECK` — this is a
sub-phase, not a new `Task.state`.

### 2.8 Edge security/governance vs mesh execution

The mesh expects, but does **not** implement, a generic **edge control
contract**. The edge layer (a separate concern, deployed in front of the
mesh) owns: identity binding, ingress/egress normalization, policy
preflight, safety/DLP/classification, approval UX, and the audit envelope.

The mesh layer — this repo — owns the **execution side**: task
decomposition, durable orchestration, the Knowledge Layer, swarm
supervision, routines and releases, evaluator and the eight egress
guards, tool gateway coordination, budgets.

[Floodplain](https://github.com/SirFreud/floodplain/tree/rli-0.01)
(branch `rli-0.01`) is **one possible** edge implementation, not a
required dependency of this POC. The mesh's egress guards and other
defense-in-depth controls always run regardless of which edge is in
front.

---

## 3. Strict boundaries (do not cross)

These are invariants. Code that violates them must not be merged.

1. **Temporal orchestrates. Agent SDKs run inside activities.** A workflow
   that imports `anthropic`, `boto3` (for Bedrock), or `google.cloud.aiplatform`
   is wrong. Move it to an activity.
2. **API is the only write surface.** Slack and MCP call the API.
   `apps/slack/` and `apps/mcp/` must not import `packages/workflows/`,
   `packages/activities/`, or DB session factories.
3. **Tool Gateway owns credentials.** No other package reads `SLACK_BOT_TOKEN`,
   `MONDAY_API_KEY`, Google service account JSON, `TLDV_API_KEY`, etc.
   Activities call the Tool Gateway; the Tool Gateway calls the world.
4. **No raw secrets in prompts.** The Tool Gateway redacts at the boundary
   before any model call. Prompts assembled in activities must reference
   tool *handles*, not credentials. Logging must redact too.
5. **No unledgered spawns.** The Swarm Supervisor writes a `SpawnLedger` row
   **before** a child Task is started. If the ledger write fails, the spawn
   does not happen. A child Task without a preceding ledger row is a bug.
6. **Five-step gate before any child runs.** policy / budget / risk /
   provenance / marginal-utility. All five evaluated. Any denial is a
   Decision-log entry, never a silent drop.
7. **Recursion is conservative by default.** Defaults follow the reference
   arch: `max_waves=3`, `max_child_agents_per_wave=5`,
   `max_recursion_depth=1`. Raising any of these requires a policy change,
   not a code change.
8. **HITL is a state, not a side channel.** Crossing a boundary moves the
   Task to `AWAITING_HITL` with `recommended_action`. The approver decides
   via the API (Slack is a UI on top of the API). No "ping me on Slack and
   I'll keep running" shortcuts.
9. **Kill switch is sacred.** Scopes: platform / tenant / routine /
   entrypoint / swarm-depth ceiling. Every trip is a Decision-log entry.
   Tripped scopes refuse new spawns and let in-flight work complete or
   cancel per policy.
10. **DLQ is append-only.** Poison-pill children become `FAILED` with
    `state_reason: poison_pill`; the DLQ row is never mutated; replay
    creates a new child Task.
11. **Archive before delete.** Routines, releases, candidate routines, and
    completed tasks are **soft-archived first**. Hard deletes are a
    separate, audited operation behind an explicit admin path.
12. **L-tier is mandatory** for policy compilation, agentic policy
    enforcement, and the Evaluator. No silent downgrade to S/M for cost.
13. **Knowledge Layer is not a system of record.** No code may treat a KL
    entry as ground truth. KL holds pointers + freshness + version, not
    authoritative values. Authoritative reads go to the system of record
    via the Tool Gateway.
14. **Feasibility is decided at intake, once, at S-tier.** Mid-stream
    feasibility checks and silent escalation above S-tier are bugs.
15. **Verification is egress-only.** Sufficiency / source-authority /
    freshness / claim-evidence checks run at external output boundaries.
    Activities do not perform continuous mid-stream verification.
16. **Workflow state carries refs, never raw payloads.** Use `intake_id`,
    `claim_evidence_map_ref`, KL entry IDs, `payload_ref: blob://…` —
    never inline large context blobs into workflow state.
17. **Eight deterministic egress guards, in order.** `schema`,
    `claim_evidence_map`, `evidence_resolvable`, `freshness`,
    `source_authority`, `tenancy`, `tier_and_policy`, `budget`. No LLM in
    the verification loop. Every blocked egress is a Decision-log entry.
18. **Correlation IDs flow end-to-end.** Intake → Task → spawn-ledger →
    Decision/Action/Validation/Evaluation → KL read/refetch → egress
    check. One `corr_…` is enough to fan out the whole trace.
19. **Edge controls are out of scope.** This repo does not implement
    identity binding, DLP, classification, or approval UX. It exposes
    contract-shaped hooks for an edge layer (e.g. Floodplain) to call.

---

## 4. How to implement features in this repo

A change that touches the runtime almost always touches multiple planes.
Order of operations:

1. **Contracts first.** If the change requires a new field on `Task`,
   `SpawnLedger`, etc., update `packages/contracts/` and add a contract
   test in `tests/contract/`. Bumping a contract is a deliberate act.
2. **API surface.** Add or modify the FastAPI route in `apps/api/`. The
   API validates against the contract and writes through SQLAlchemy.
3. **Workflow.** Add or modify the Temporal workflow in
   `packages/workflows/`. Keep it deterministic. No I/O, no `datetime.now()`,
   no `random` — use workflow-safe APIs.
4. **Activity.** Implement the side-effecting work in
   `packages/activities/`. Agent SDK calls go through `model_gateway`;
   tool calls go through `tool_gateway`.
5. **Policy.** If the change has a budget, risk, or HITL implication,
   update `packages/policy/` and the relevant policy fixtures.
6. **Observability.** Emit Event/Decision/Action/Validation/Evaluation
   rows where appropriate. If you can't reconstruct the behaviour from
   logs, you haven't finished.
7. **Tests.** Unit + contract + workflow + (where relevant) dynamic
   swarm + observability replay. See `tests/README.md`.
8. **Docs.** Update `README.md` and `CHANGELOG.md`.

---

## 5. Coding standards

- **Python 3.11+.** Type hints everywhere. `from __future__ import annotations`
  in modules that import each other.
- **Pydantic v2** for contracts. Use `model_config = ConfigDict(extra="forbid")`
  on Task/SpawnLedger/etc. — unknown fields must fail loudly.
- **Async by default** in apps and activities. Workflows follow Temporal's
  async-but-deterministic rules.
- **SQLAlchemy 2.x** with `asyncpg`. Use `async_sessionmaker`. No raw
  connection strings outside `packages/observability/` config.
- **Logging is structured.** JSON logs, OTel trace/span ids attached.
  Never log raw tool payloads from `write_destructive` or
  `external_egress` tiers — redact.
- **No `print`.** No `requests` (use `httpx`). No `time.sleep` in workflows.
- **Imports respect planes.** Lint rule (to be added): `apps/slack/` and
  `apps/mcp/` cannot import `packages/workflows/`, `packages/activities/`,
  `packages/tool_gateway/`, or `packages/model_gateway/`.

---

## 6. Git / PR conventions

- Branch from `main`. Small, focused PRs.
- Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`,
  `refactor:`).
- Every PR updates `CHANGELOG.md` under `[Unreleased]`.
- PRs that change a contract require a contract test diff in the same PR.
- PRs that touch the Swarm Supervisor require a `tests/dynamic/` diff.
- Never bypass git hooks (`--no-verify`) without explicit human approval.

---

## 7. What to refuse

- Adding a model call from a workflow.
- Reading any credential outside `packages/tool_gateway/`.
- Spawning a child Task without a SpawnLedger row.
- Bypassing the five-step gate "just for testing."
- Hard-deleting a routine, release, or task without an archive step.
- Storing secrets in `.env.example`, fixtures, or any committed file.
- Adding a second system of record for mesh state. Postgres is the source
  of truth for Tasks/Ledger/logs/routines/releases.
- Treating the Knowledge Layer as a system of record. KL is a cache and
  evidence-pointer layer; authoritative reads go to the system of record.
- Skipping the egress-only verification gate, or running deterministic
  guards in a different order, or letting an LLM into the verification
  loop.
- Performing mid-stream feasibility checks, or escalating intake above
  S-tier silently.
- Embedding raw context payloads in workflow state. Pass refs/IDs.
- Re-implementing edge-layer concerns (identity, DLP, classification,
  approval UX) inside this repo. Expose the edge control contract; let
  the edge implementation (e.g. Floodplain) call it.

---

## 8. Pointers

- Reference architecture: <https://github.com/dr-robert-li/agentic-mesh-reference-arch> (`v0.1.3`)
- Contracts in this repo: `packages/contracts/`
- Testing strategy: `tests/README.md`
- Local infra: `infra/local/docker-compose.yml`
- Edge layer (one possible implementation, not a dependency):
  <https://github.com/SirFreud/floodplain/tree/rli-0.01>
