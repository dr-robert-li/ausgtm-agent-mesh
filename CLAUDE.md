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
implements them on **off-the-shelf open-source primitives** so the runtime is
not bespoke and not ours to maintain.

Stack: Python 3.11+, **LangGraph** (cognitive control plane), **Temporal**
(durable execution boundary, local Python SDK), **FastAPI** + **FastMCP**
(ingress), **PostgreSQL + pgvector** (mesh state of record, evidence index,
*and* LangGraph checkpoints), **Cloudflare AI Gateway** (default LLM egress
proxy), **OpenTelemetry** (traces/metrics). Slack enters over signed HTTP
endpoints on FastAPI.

First non-local deployment target: **AWS ECS Fargate**. Not Temporal Cloud.

> **Provider binding is pluggable and currently PENDING.** Cloudflare AI
> Gateway is the fixed LLM egress boundary; the specific model client behind
> it (Anthropic-native vs OpenAI-compatible vs multi-provider) is supplied by
> the repo owner's forthcoming provider documentation. Until then, write
> provider-neutral code against the gateway. See the stack table in
> `README.md` for the single source of this PENDING marker.

### 1.1 Why this is a pivot from v0.1.x

Earlier versions hand-rolled a four-plane scaffold and called the Anthropic
Claude Agent SDK **directly inside Temporal activities**, with bespoke
orchestration in Temporal workflows. `v0.2.0` replaces that custom substrate
with mature OSS components. **The reference-arch contracts and invariants are
unchanged.** Only the implementation substrate changed: orchestration logic
moves into LangGraph; Temporal becomes the durable shell around it.

---

## 2. Architectural design pattern

The reference architecture's **four planes** still hold. Each maps onto an
off-the-shelf component. Code lives in one plane. Cross-plane calls go through
named seams, never ad-hoc imports.

| Reference-arch plane | OSS component | Role |
|---|---|---|
| **Entry** (`apps/api/`, `apps/mcp/`, `apps/slack/`) | FastAPI + FastMCP + Slack signed HTTP | Ingress only. The API is the source of truth and the **only write surface**. |
| **Control** (`apps/api/`, `packages/graph/`) | **LangGraph** state machine | Supervisor, wave router (`Send` fan-out), reducers, egress guards, interrupt-driven HITL. Runs **inside a Temporal activity**. |
| **Execution** (`packages/graph/` nodes, `packages/tool_gateway/`) | LangGraph worker nodes + Cloudflare AI Gateway + Tool Gateway | Worker LLM calls go through the **gateway**; tool calls go through the **Tool Gateway**. |
| **Persistence & telemetry** (Postgres+pgvector, `packages/observability/`) | PostgreSQL + pgvector + OpenTelemetry | Mesh state of record, evidence index, LangGraph checkpoints, five log streams. |

### 2.1 Entry plane — ingress only

- End users live in **Slack**. External agents enter via **MCP** (FastMCP,
  mounted on FastAPI) and use it for self-loopback. The **REST API** is the
  source of truth and the only write surface.
- Slack, MCP, and REST handlers **call the API / start a Temporal workflow**.
  They never run the LangGraph engine inline, never write `Task` state
  directly, never call the Tool Gateway directly, and never do durable work in
  a request handler (no FastAPI `BackgroundTasks` for orchestration — Temporal
  owns durability).
- **Slack ingress is signature-verified** before any parsing: HMAC over the
  raw request body with `X-Slack-Signature` / `X-Slack-Request-Timestamp`,
  a versioned `v0:` basestring, and a replay window ≤ 5 minutes.

### 2.2 Control plane — LangGraph inside Temporal

- **Temporal owns the durable execution boundary.** A `@workflow.defn`
  workflow is a **thin deterministic shell**. It invokes exactly one activity
  that runs the compiled LangGraph engine. Temporal provides retries, durable
  timers/sleep, and survival across deploys and pod restarts.
- **LangGraph owns the cognition.** The agent state machine, deterministic
  reducers, dynamic `Send` fan-out, the collector fan-in node, the egress
  guards, and the interrupt-driven HITL flow all live in `packages/graph/`
  and execute **inside the activity**, never inside the workflow.
- The **Planner/Decomposer**, **Swarm Supervisor**, **Policy/Governance
  engine**, **Evaluator**, **Contract Validator**, and **Routine & Release
  Registry** are LangGraph nodes or services behind the API.
- The Swarm Supervisor **never writes authoritative Task state and never
  invokes tools**. It emits a spawn decision and writes a durable
  **SpawnLedger** row to mesh-state Postgres. A `Send` fan-out then activates
  the child worker node.

### 2.3 The layered orchestration model (the crux)

This is the reconciliation that keeps the OSS stack faithful to the reference
arch's "no model calls in the orchestrator" invariant:

```
Temporal workflow  (deterministic shell — no LLM, no LangGraph import)
  └─ execute_activity(run_langgraph_activity)
        └─ compiled LangGraph engine  (control plane)
              ├─ supervisor node        → writes SpawnLedger rows (durable)
              ├─ wave_router (Send)      → deterministic fan-out
              ├─ worker nodes           → LLM via Cloudflare AI Gateway,
              │                            tools via Tool Gateway
              ├─ collector node         → reducer fan-in
              ├─ egress guards          → 8 deterministic checks, in order
              └─ human_review (interrupt_before) → AWAITING_HITL
```

Temporal makes the run **durable**; LangGraph makes the cognition
**structured, checkpointed, and resumable**. Neither leaks into the other:
the workflow module imports no LLM client and no LangGraph; the graph holds no
Temporal handles.

### 2.4 Execution plane — gateways

- **LLM egress** routes through **Cloudflare AI Gateway** (observability,
  rate controls, logging, gateway policy). Worker nodes never call a provider
  base URL directly. The model tier (`S`/`M`/`L`) is chosen by **policy**, not
  by the calling node. Provider binding is PENDING (see §1).
- **Tool egress** routes through the **Tool Gateway** (`packages/tool_gateway/`),
  the **only** code that holds tool credentials and the **only** code that
  calls external tool APIs (Slack write, Monday, Sheets, tl;dv, etc.). MCP
  tools wired into worker nodes call **through** the Tool Gateway. It enforces
  tool **trust tiers**: `read_safe`, `read_sensitive`, `write_revocable`,
  `write_destructive`, `external_egress`.
- **Cloudflare AI Gateway is LLM egress only — never tool egress.** Do not
  conflate the two boundaries.

### 2.5 Persistence & telemetry — two Postgres concerns, one instance

PostgreSQL + pgvector serves **two distinct concerns**. Do not conflate them:

1. **Mesh state of record** — Tasks, SpawnLedger, policies, routines,
   releases, the five log streams, and the pgvector evidence/retrieval index.
   This is authoritative.
2. **LangGraph checkpoints** — `AsyncPostgresSaver` thread state. This is
   **cognitive working memory** for interrupt/resume, **not** authoritative
   mesh state.

- The **five log streams** — Event, Decision, Action, Validation, Evaluation
  — are first-class Postgres tables. Every state change, spawn, tool call,
  validator verdict, evaluator score, KL read/refetch, and egress check writes
  a row. **OpenTelemetry is observability (traces/metrics), not a replacement
  for this durable audit substrate.**
- A task must be **reconstructable from the log streams alone**.
- **Persistent checkpointing is mandatory.** `AsyncPostgresSaver` in every
  environment; `MemorySaver` only in unit tests. Interrupts and HITL must
  survive restarts.

### 2.6 Context and Evidence Knowledge Layer

A tenant-scoped **cache + index + evidence-pointer substrate**. KL is *not* a
system of record. Authoritative state stays in external tools. KL holds
pointers + freshness + version, not ground truth.

- Entries keyed `(tenant_id, source_system, source_id)` with optional
  `content_hash`, addressed as `kl:{tenant}:{source}/{path}#v{n}`.
- Writes are **append-only and versioned**. LLMs never write KL entries
  directly — only ingest activities do, via the Tool Gateway.
- LangGraph state carries **refs/IDs** (`intake_id`, `claim_evidence_map_ref`,
  KL entry IDs, `payload_ref: blob://…`) — never raw context payloads.
- KL reads are budgeted via `evidence_fetch_budget` (`max_reads`,
  `max_refetches`, `max_stale_acceptance`), propagated to children as a
  fraction of the parent's remaining budget.

### 2.7 Intake contract and S-tier feasibility

Inbound requests from the entry plane produce an **`Intake`** artifact
*before* a Task is created. Intake performs exactly three cheap checks:
**schema parse**, **tool-plan lookup**, and **one S-tier classifier call**.
Verdict is `feasible | ambiguous | infeasible`.

- **No silent escalation above S-tier at intake.** Ambiguity produces one
  disambiguating question, not an M/L cascade.
- The Task references the intake via `Task.intake_id` and emits a
  `ProvenanceRef(kind=intake, ref=intake_…)`.
- **Feasibility is decided once.** It is not re-run mid-stream.

### 2.8 Egress-only verification and the eight guards

Verification against systems of record happens **only at egress** — at the
external output/action boundary — not continuously mid-stream. The LLM
proposes the output/action plus a **claim-evidence map** sidecar
(`ClaimEvidenceMap`); deterministic guards then enforce, in this fixed order:

1. `schema` — payload validates against its output schema.
2. `claim_evidence_map` — sidecar present and well-formed.
3. `evidence_resolvable` — every claim's evidence ref resolves.
4. `freshness` — every evidence ref meets freshness policy.
5. `source_authority` — sources are authoritative for the predicate asserted.
6. `tenancy` — hard refuse on cross-tenant evidence leakage.
7. `tier_and_policy` — tool tier, policy, HITL thresholds; may `require_hitl`.
8. `budget` — `evidence_fetch_budget` and other budgets not exceeded.

The blueprint's `egress_guard_node` ships a **4-guard MVP subset**
(schema/budget/evidence/worker-errors). That is a starting point only:
production requires **all eight, in this order**. **No LLM in the verification
loop.** Outcomes: `pass`, `blocked`, `blocked_require_hitl`. A blocked egress
produces an `EgressCheckRecord` and a `decision_kind: egress_blocked`
Decision-log entry. A `require_hitl` outcome maps to the LangGraph
`human_review_node` interrupt and the Task's `AWAITING_HITL` sub-phase
(`hitl.from_state = EGRESS_CHECK`).

### 2.9 HITL via LangGraph interrupts

HITL is a **state**, not a side channel. The graph compiles with
`interrupt_before=["human_review_node"]` over an `AsyncPostgresSaver`, so a
thread pauses durably and resumes across restarts. The interrupt maps to the
mesh Task state `AWAITING_HITL` with a `recommended_action`. The approver
decides **via the API** (Slack is a UI on top of the API). No "ping me on
Slack and I'll keep running" shortcuts.

### 2.10 Edge security/governance vs mesh execution

The mesh expects, but does **not** implement, a generic **edge control
contract**. The edge layer (deployed in front of the mesh) owns: identity
binding, ingress/egress normalization, policy preflight, safety/DLP/
classification, approval UX, and the audit envelope.

This repo owns the **execution side**: task decomposition, durable
orchestration, the Knowledge Layer, swarm supervision, routines and releases,
the evaluator and eight egress guards, tool gateway coordination, budgets.

[Floodplain](https://github.com/SirFreud/floodplain/tree/rli-0.01) (branch
`rli-0.01`) is **one possible** edge implementation, not a required
dependency. The mesh's egress guards and other defense-in-depth controls
always run regardless of which edge is in front.

---

## 3. Strict boundaries (do not cross)

These are invariants. Code that violates them must not be merged.

1. **Temporal owns durable execution; workflows are deterministic shells.**
   LangGraph runs inside the activity. A `@workflow.defn` module that imports
   `langgraph`, `langchain_*`, an LLM client, or a tool client is wrong. No
   `datetime.now()`, `random`, network, or DB in a workflow.
2. **FastAPI is ingress only.** No durable work in request handlers. No
   `BackgroundTasks` for orchestration — Temporal owns durable jobs. Handlers
   POST to the API / start a workflow; they never run the graph inline.
3. **API is the only write surface for mesh Task state.** The mesh `Task`
   (Postgres) is authoritative for the state machine
   (`PENDING`/`RUNNING`/`AWAITING_HITL`/`COMPLETED`/`FAILED`). LangGraph
   thread state is execution working memory, **never** authoritative mesh
   state.
4. **Tool Gateway owns credentials.** No other package reads `SLACK_BOT_TOKEN`,
   `MONDAY_API_KEY`, Google service-account JSON, `TLDV_API_KEY`, etc.
   Worker nodes call the Tool Gateway; the Tool Gateway calls the world.
5. **Cloudflare AI Gateway is the only LLM egress path.** No worker node calls
   a provider base URL directly. It is **LLM egress only**, not tool egress.
6. **No raw secrets in prompts or graph state.** Secrets live in the platform
   secret manager and are injected at worker runtime only. The Tool Gateway
   redacts at the boundary before any model call. Logging redacts too.
7. **No unledgered spawns.** The Swarm Supervisor writes a durable
   `SpawnLedger` row to mesh-state Postgres **before** a `Send` fan-out
   activates a child. The reducer-aggregated `spawn_ledger` in LangGraph state
   is aggregation only — it is **not** the authoritative ledger.
8. **Persistent checkpointer is mandatory.** `AsyncPostgresSaver` in all
   environments; `MemorySaver` only in unit tests.
9. **Deterministic fan-in.** Parallel worker outputs merge only through typed
   reducers plus a collector node. No node mutates shared state outside its
   reducer.
10. **Eight deterministic egress guards, in order.** `schema`,
    `claim_evidence_map`, `evidence_resolvable`, `freshness`,
    `source_authority`, `tenancy`, `tier_and_policy`, `budget`. The 4-guard
    node is an MVP subset. No LLM in the verification loop. Every blocked
    egress is a Decision-log entry.
11. **Verification is egress-only.** No continuous mid-stream verification.
12. **Knowledge Layer is not a system of record.** KL holds pointers +
    freshness + version, not authoritative values. Authoritative reads go to
    the system of record via the Tool Gateway.
13. **Feasibility is decided at intake, once, at S-tier.** Mid-stream
    feasibility checks and silent escalation above S-tier are bugs.
14. **LangGraph state carries refs, never raw payloads.** Use `intake_id`,
    `claim_evidence_map_ref`, KL entry IDs, `payload_ref: blob://…`.
15. **Five log streams are mandatory.** Event/Decision/Action/Validation/
    Evaluation Postgres tables. OTel is observability, not a substitute. A
    task must be reconstructable from logs alone.
16. **Slack ingress is signature-verified** over the raw body, timestamp, and
    versioned basestring, with a ≤ 5-minute replay window, before any parsing
    or workflow start.
17. **Five-step gate before any child runs.** policy / budget / risk /
    provenance / marginal-utility. Any denial is a Decision-log entry, never a
    silent drop.
18. **Recursion is conservative by default.** `max_waves=3`,
    `max_child_agents_per_wave=5`, `max_recursion_depth=1`. Raising any of
    these requires a policy change, not a code change.
19. **HITL is a state, not a side channel.** The `human_review_node` interrupt
    moves the Task to `AWAITING_HITL`; the approver decides via the API.
20. **Kill switch is sacred; DLQ is append-only; archive before delete.**
    Every kill-switch trip is a Decision-log entry. Poison-pill children
    become `FAILED` with `state_reason: poison_pill`; the DLQ row is never
    mutated; replay creates a new child Task. Routines, releases, candidate
    routines, and completed tasks are soft-archived before any hard delete.
21. **L-tier is mandatory** for policy compilation, agentic policy
    enforcement, and the Evaluator. No silent downgrade to S/M for cost.
22. **Correlation IDs flow end-to-end.** Intake → Task → spawn-ledger →
    Decision/Action/Validation/Evaluation → KL read/refetch → egress check.
    One `corr_…` fans out the whole trace.
23. **Edge controls are out of scope.** This repo does not implement identity
    binding, DLP, classification, or approval UX. It exposes contract-shaped
    hooks for an edge layer (e.g. Floodplain) to call.

---

## 4. How to implement features in this repo

A change that touches the runtime almost always touches multiple planes.
Order of operations:

1. **Contracts first.** New field on `Task`, `SpawnLedger`, `Intake`,
   `ClaimEvidenceMap`, `EgressCheckRecord`, etc. → update `packages/contracts/`
   and add a contract test in `tests/contract/`. These shapes come from the
   reference arch `v0.1.3`; bumping one is a deliberate act.
2. **API surface.** Add or modify the FastAPI route in `apps/api/`. It
   validates against the contract and writes mesh state through SQLAlchemy.
3. **Workflow.** Add or modify the Temporal workflow in `packages/workflows/`.
   Keep it a deterministic shell that invokes the LangGraph activity.
4. **Activity.** Implement the side-effecting boundary in
   `packages/activities/` — including `run_langgraph_activity`. Engine build
   and `ainvoke`/`astream` happen here.
5. **Graph.** Add or modify LangGraph nodes/edges/reducers in
   `packages/graph/`: `Send` fan-out, collector fan-in, guard nodes, interrupt
   points. LLM via Cloudflare gateway; tools via Tool Gateway.
6. **Policy.** Budget, risk, or HITL implications → update `packages/policy/`
   and the relevant policy fixtures.
7. **Observability.** Emit Event/Decision/Action/Validation/Evaluation rows
   and OTel spans. If you can't reconstruct the behaviour from the log
   streams, you haven't finished.
8. **Tests.** Unit + contract + workflow + (where relevant) dynamic swarm +
   observability replay.
9. **Docs.** Update `README.md` and `CHANGELOG.md`.

---

## 5. Coding standards

- **Python 3.11+.** Type hints everywhere. `from __future__ import annotations`
  in modules that import each other.
- **Pydantic v2** for contracts. `model_config = ConfigDict(extra="forbid")`
  on Task/SpawnLedger/Intake/etc. — unknown fields must fail loudly.
- **LangGraph state** uses `TypedDict` with `Annotated[..., reducer]` fields
  for all merge points. `langchain_core.messages` for message objects.
- **Async by default** in apps, activities, and graph nodes that do I/O.
  Workflows follow Temporal's async-but-deterministic rules.
- **SQLAlchemy 2.x** with `asyncpg`. Use `async_sessionmaker`. The LangGraph
  `AsyncPostgresSaver` connection is configured once and reused.
- **Logging is structured.** JSON logs, OTel trace/span ids attached. Never
  log raw tool payloads from `write_destructive` or `external_egress` tiers —
  redact.
- **No `print`.** No `requests` (use `httpx`). No `time.sleep` in workflows
  (use Temporal timers).
- **Imports respect planes.** Lint rule (to be added): `apps/slack/`,
  `apps/mcp/`, `apps/api/` route handlers cannot import `packages/graph/`,
  `packages/workflows/`, `packages/activities/`, `packages/tool_gateway/`, or
  `packages/model_gateway/`. No `@workflow.defn` module imports `langgraph`,
  `langchain_*`, or an LLM client.

---

## 6. Git / PR conventions

- Branch from `main`. Small, focused PRs.
- Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`,
  `refactor:`). Breaking changes carry `!` and a `BREAKING CHANGE:` footer.
- Every PR updates `CHANGELOG.md` under `[Unreleased]`.
- PRs that change a contract require a contract test diff in the same PR.
- PRs that touch the Swarm Supervisor / graph spawn path require a
  `tests/dynamic/` diff.
- Never bypass git hooks (`--no-verify`) without explicit human approval.

---

## 7. What to refuse

- Importing `langgraph`, `langchain_*`, an LLM client, or a tool client from a
  Temporal workflow module.
- Running durable orchestration in a FastAPI handler or `BackgroundTasks`.
- Using `MemorySaver` outside unit tests.
- Reading any credential outside `packages/tool_gateway/`.
- Routing an LLM call around the Cloudflare AI Gateway.
- Spawning a child Task without a durable `SpawnLedger` row first.
- Skipping the egress gate, reordering the eight guards, or putting an LLM in
  the verification loop.
- Treating LangGraph thread state as authoritative mesh state.
- Treating the Knowledge Layer as a system of record.
- Accepting Slack ingress without HMAC signature verification.
- Embedding raw context payloads in LangGraph state. Pass refs/IDs.
- Performing mid-stream feasibility checks, or escalating intake above S-tier
  silently.
- Hard-deleting a routine, release, or task without an archive step.
- Storing secrets in `.env.example`, fixtures, or any committed file.
- Adding a second system of record for mesh state. Postgres is the source of
  truth for Tasks/Ledger/logs/routines/releases.
- Re-implementing edge-layer concerns (identity, DLP, classification, approval
  UX) inside this repo.

---

## 8. Pointers

- Reference architecture: <https://github.com/dr-robert-li/agentic-mesh-reference-arch> (`v0.1.3`)
- LangGraph: <https://langchain-ai.github.io/langgraph/>
- Temporal Python SDK: <https://docs.temporal.io/develop/python>
- FastMCP / MCP Python SDK: <https://github.com/modelcontextprotocol/python-sdk>
- Cloudflare AI Gateway: <https://developers.cloudflare.com/ai-gateway/>
- Edge layer (one possible implementation, not a dependency):
  <https://github.com/SirFreud/floodplain/tree/rli-0.01>
