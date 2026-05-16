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
`v0.1.2`. The reference repo defines contracts and invariants; this repo
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

- **Postgres + pgvector** is the system of record from day one. No
  shadow stores. No "we'll add a DB later." Vector indexes for routine
  retrieval and evaluator memory live in the same DB.
- The **five log streams** — Event, Decision, Action, Validation,
  Evaluation — are first-class. Every state change, spawn, tool call,
  validator verdict, and evaluator score writes a row.
- A task must be **reconstructable from logs alone** (see
  `tests/observability/`).

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
- Adding a second system of record. Postgres is the source of truth.

---

## 8. Pointers

- Reference architecture: <https://github.com/dr-robert-li/agentic-mesh-reference-arch> (`v0.1.2`)
- Contracts in this repo: `packages/contracts/`
- Testing strategy: `tests/README.md`
- Local infra: `infra/local/docker-compose.yml`
