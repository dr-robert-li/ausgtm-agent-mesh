# ausgtm-agent-mesh

Local-first Python POC runtime for the **Agentic Mesh** described in
[`dr-robert-li/agentic-mesh-reference-arch`](https://github.com/dr-robert-li/agentic-mesh-reference-arch)
(currently tracking `v0.1.3`).

This repository is the **implementation** of the architecture. The reference
repo defines contracts, planes, and invariants; this repo wires them into a
runnable system using **off-the-shelf open-source primitives** — LangGraph,
Temporal, FastAPI, FastMCP, PostgreSQL + pgvector, OpenTelemetry — with
**Cloudflare AI Gateway** as the default LLM egress proxy.

> **Scope.** Local-first POC. No Temporal Cloud. First non-local deployment
> target is AWS ECS Fargate.

> **`v0.2.0` is an architecture pivot.** Earlier versions hand-rolled a
> four-plane scaffold and called an agent SDK directly inside Temporal
> activities. This version moves all orchestration logic into **LangGraph**
> and keeps **Temporal** as a thin durable shell around it, so the runtime is
> built from maintained OSS components rather than bespoke code. The
> reference-arch contracts and invariants are unchanged.

---

## Purpose

Demonstrate that the reference architecture's four-plane design (entry /
control / execution / persistence) can be implemented on commodity OSS with:

- **A durable execution boundary** via Temporal — retries, durable
  timers/sleep, and survival across deploys and pod restarts.
- **A cognitive control plane** via LangGraph — agent state machine, dynamic
  `Send` fan-out, deterministic reducers, a collector fan-in node, and
  interrupt-driven HITL.
- **LangGraph running inside a Temporal activity** — never inside a workflow.
  The workflow is a deterministic shell; all LLM/tool calls happen in the
  graph, in the activity.
- **FastAPI as ingress only** — REST, mounted FastMCP, and signed Slack HTTP
  endpoints. The API is the source of truth and the only write surface.
- **Persistent LangGraph checkpointing** in Postgres (`AsyncPostgresSaver`) so
  interrupts and HITL pause and resume across restarts.
- **Cloudflare AI Gateway** as the default LLM egress proxy (observability,
  rate controls, logging, gateway policy).
- **A Tool Gateway** that owns all tool credentials and is the only code that
  calls external tool APIs.
- **Postgres + pgvector** as the system of record **for mesh state** (Tasks,
  SpawnLedger, log streams, routines/releases) and the vector store, distinct
  from the LangGraph checkpoint schema.
- **Context and Evidence Knowledge Layer** — a tenant-scoped cache + index +
  evidence-pointer layer in front of external tools. **Not** a system of
  record; ground truth stays in the external tools.
- **Intake contract** with a cheap S-tier feasibility check at the entry plane.
- **Egress-only verification** with eight deterministic guards — no LLM in the
  verification loop.
- **Swarm Supervisor** with wave-based dynamic spawning, conservative
  recursion, policy / budget / risk / marginal-utility gates, an append-only
  spawn ledger, HITL escalation, kill switch, and DLQ.

The POC's job is to make the boundaries in [`CLAUDE.md`](./CLAUDE.md) real and
verifiable on the OSS stack — not to ship every routine.

---

## Stack

| Layer | Choice | Role |
|---|---|---|
| Language | Python 3.11+ | — |
| Ingress | FastAPI + uvicorn | REST, auth middleware, ingress only |
| MCP | FastMCP (MCP Python SDK), mounted on FastAPI | External-agent entry + self-loopback |
| Slack | Signed HTTP endpoints on FastAPI | HMAC signature verification over raw body |
| Durable boundary | Temporal (`temporalio` Python SDK) | Retries, durable timers, restart survival |
| Control plane | LangGraph | State machine, `Send` fan-out, reducers, HITL interrupts |
| Checkpoint state | Postgres + `AsyncPostgresSaver` | Durable interrupt/resume for LangGraph threads |
| Mesh state of record | Postgres 16 + `pgvector` | Tasks, SpawnLedger, log streams, evidence index |
| DB driver | `asyncpg` + SQLAlchemy 2.x | — |
| Contracts | Pydantic v2 | Reference-arch `v0.1.3` shapes |
| LLM egress | **Cloudflare AI Gateway** (Anthropic route) | Default proxy for all model traffic |
| LLM provider | **Claude Agent SDK + Anthropic API** | Model client behind the gateway; `langchain-anthropic` / `anthropic` with `base_url` at the gateway |
| Observability | OpenTelemetry (traces/metrics) + Grafana stack | Correlated traces across ingress/workflow/graph |
| Tests | `pytest`, `pytest-asyncio`, Temporal test harness | — |

External integrations targeted for v1: **Slack**, **Monday.com**,
**Google Sheets / Workspace**, **tl;dv / external meeting artifacts**, with
HubSpot, Clockify, and Bitscale as additional tool packs.

---

## System topography

```text
                    [ User Interaction Entrypoints ]
              ┌───────────────┬───────────────┬───────────────┐
              ▼               ▼               ▼
      [ REST / Web UI ] [ Claude / MCP ]  [ Slack Commands ]
              │               │               │
              └───────────────┴───────┬───────┘
                                      ▼
                           [ FastAPI Gateway Layer ]   (ingress only)
                     - REST endpoints + auth middleware
                     - Mounted FastMCP server
                     - Slack HMAC signature verification
                                      │
                                      ▼
                           [ Temporal Workflow Layer ]
                    - Durable execution / retries / sleep / resume
                    - Deterministic shell — no LLM, no LangGraph import
                                      │  execute_activity(run_langgraph_activity)
                                      ▼
                           [ LangGraph Control Plane ]
                    (checkpointed in Postgres via AsyncPostgresSaver)
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          ▼                           ▼                           ▼
 [ Swarm Supervisor ]         [ Worker Fan-Out ]         [ Egress + HITL ]
 (plans wave + budget,       (Send API + reducers,      (8 guards in order;
  durable SpawnLedger)        collector fan-in)          interrupt → HITL)
          │                           │                           │
          └───────────────────────────┴───────────────┬───────────┘
                                                      ▼
                          LLM egress → [ Cloudflare AI Gateway ] → Anthropic API
                          Tool egress → [ Tool Gateway ] → external tool APIs
```

LLM egress and tool egress are **separate boundaries**: model traffic goes
through Cloudflare AI Gateway; external tool calls go through the Tool Gateway,
which is the only code that holds tool credentials.

---

## Target repo structure

> The scaffold was reset in `v0.2.0` for the OSS rebuild. The structure below
> is the **target** layout for the new stack — directories are created as
> features land (see [`CLAUDE.md`](./CLAUDE.md) §4 for the build order).

```
apps/
  api/          FastAPI — system of record. Only write surface. Mounts FastMCP.
  slack/        Slack signed-HTTP handlers. POST to the API. No graph inline.
  mcp/          FastMCP tools. External-agent entry + loopback. POST to the API.
  workers/      Temporal worker process(es) hosting workflows + activities.
packages/
  contracts/    Pydantic v2 models: Task, Policy, Routine, SpawnLedger,
                Intake, KnowledgeLayerEntry, ClaimEvidenceMap,
                EgressCheckRecord, HITLDecision, EvaluationRecord.
  workflows/    Temporal workflows — deterministic shells that invoke the
                LangGraph activity. No LLM/LangGraph imports.
  activities/   Temporal activities — side-effecting boundary, incl.
                run_langgraph_activity (engine build + ainvoke).
  graph/        LangGraph nodes/edges/reducers: supervisor, wave_router (Send),
                worker nodes, collector (fan-in), egress guards, human_review.
  model_gateway/  Cloudflare AI Gateway client + model-tier (S/M/L) selection.
  tool_gateway/   The only place tool credentials live. Trust tiers enforced.
  policy/       Policy engine, evaluator, validator, five-step spawn gate.
  registry/     Routine + Release manifest registry.
  observability/ OTel setup, the five log streams, log helpers.
infra/
  local/        docker-compose (Postgres+pgvector, Temporal), seed scripts.
  aws/          ECS Fargate stubs (later).
tests/
  unit/ contract/ workflow/ integration/ dynamic/ system/ chaos/ observability/
```

---

## Local quickstart

> This is a documentation-stage scaffold post-pivot. The commands below are the
> **intended** workflow for the OSS stack once the application code lands.

### Prerequisites

- Python 3.11+
- Docker + Docker Compose
- A Cloudflare AI Gateway (account id + gateway id) and an Anthropic API key
  for the Claude Agent SDK / Anthropic API behind the gateway's Anthropic route
- Optional: Slack app (bot token + signing secret), Monday API token, Google
  service account, tl;dv API key

### Bring up infra

```bash
cp .env.example .env          # to be regenerated for the OSS stack
# edit .env with real values
docker compose -f infra/local/docker-compose.yml up -d
```

This starts:

- **Postgres 16 + pgvector** on `localhost:5432` (mesh state + LangGraph saver)
- **Temporal** (server + UI) on `localhost:7233` / UI `localhost:8233`

### Run the processes

```bash
# 1. API ingress (system of record, mounts FastMCP)
opentelemetry-instrument uvicorn apps.api.main:app --reload --port 8000

# 2. Temporal worker (hosts workflows + the LangGraph activity)
python -m apps.workers.main
```

Slack and MCP enter through the API; there is no separate long-running Slack
socket process — Slack posts to signed FastAPI endpoints.

---

## POC scenarios

Each scenario must be reconstructable from the five log streams alone (see
`tests/observability/`).

1. **Slack → simple task.** A user invokes the bot with a goal. The signed
   Slack endpoint verifies the request, the API creates a `Task` and starts a
   Temporal workflow, the workflow runs the LangGraph activity (single worker,
   no fan-out, no HITL), and the result posts back to Slack via the Tool
   Gateway.
2. **Slack → wave-based swarm.** A goal that requires decomposition. The
   supervisor node writes durable SpawnLedger rows, `wave_router` fans out via
   `Send` within `max_child_agents_per_wave`, and the collector node merges
   results through reducers before egress.
3. **Monday.com + Sheets cross-tool task.** Reads a Monday board and writes a
   Google Sheet. Exercises the Tool Gateway and trust tiers (`read_sensitive`
   → `write_revocable`) with credential isolation.
4. **tl;dv meeting → action extraction.** Ingest a meeting artifact via tl;dv,
   produce action items, optionally fan out. Exercises external-agent entry via
   MCP and/or scheduled API ingest.
5. **HITL escalation + kill switch.** A task crosses a policy/budget boundary →
   the `human_review_node` interrupt fires, the Task moves to `AWAITING_HITL`,
   the thread checkpoints durably, and an approver decides via the API. A kill
   switch trip on the same routine demonstrates the scopes.
6. **Candidate routine promotion.** The system proposes a routine from observed
   traces; it lands as a candidate; async review approves it; the original is
   **archived before** any hard delete.

---

## The five production-critical properties (built in, not TODO)

1. **Valid Cloudflare gateway URL.** All LLM traffic uses Cloudflare's
   documented gateway base URL pattern
   (`https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/{provider}`).
2. **Signed Slack ingress.** Every inbound Slack request is verified with
   signing-secret HMAC over the raw body, timestamp, and versioned basestring,
   with a ≤ 5-minute replay window, before any parsing or workflow start.
3. **Persistent LangGraph checkpointing.** `AsyncPostgresSaver` backs every
   thread so interrupts and HITL survive restarts. No `MemorySaver` outside
   unit tests.
4. **Deterministic fan-out/fan-in.** Typed reducers plus a collector node merge
   parallel worker outputs and centralize cost/evidence aggregation before
   guard evaluation.
5. **Durable execution via Temporal.** FastAPI stays thin as ingress; Temporal
   owns durable job execution, retry, and recovery. No `BackgroundTasks` for
   orchestration.

---

## Testing strategy (summary)

Unit tests are necessary but **insufficient** for an agentic system. We add:

- **Contract tests** — every Pydantic model round-trips JSON Schema; version
  drift in `Task` / `SpawnLedger` / `Intake` / `EgressCheckRecord` is a build
  failure.
- **Workflow tests** — Temporal's test harness runs the deterministic shell
  with the LangGraph activity mocked or replayed.
- **Graph tests** — LangGraph nodes/reducers/guards in isolation; fan-out
  ordering and reducer merge determinism.
- **Integration tests** — Slack/Monday/Sheets/tl;dv against sandbox tenants
  through the Tool Gateway.
- **Dynamic swarm tests** — assert wave count, recursion depth, ledger
  ordering, and denial reasons (`max_recursion_depth`, `runaway_swarm`).
- **System tests** — full Slack → API → Temporal → LangGraph → tools → Slack.
- **Chaos tests** — kill a worker mid-activity, drop a tool to 5xx, expire
  activity heartbeats, exhaust budgets; verify durable resume from the saver.
- **Observability tests** — reconstruct the Task tree and final state from the
  five log streams alone.

---

## Deployment targets

| Stage | Target |
|---|---|
| Now (POC) | Local Docker Compose. Local Temporal server. |
| Next | **AWS ECS Fargate** for API / workers; managed Postgres (RDS) with pgvector; self-hosted Temporal on Fargate. |
| Later | Cloudflare AI Gateway in front of production providers; not Temporal Cloud. |

- **Ingress service:** FastAPI + mounted FastMCP — horizontally scalable,
  stateless, no long-running work in request handlers.
- **Workflow layer:** Temporal server + a separate worker deployment that hosts
  workflows and the LangGraph activity.
- **Database:** managed Postgres with pgvector — LangGraph checkpoints plus
  mesh state and the evidence index.
- **LLM egress:** Cloudflare AI Gateway with the documented base URL format.

---

## Boundaries (read these before writing code)

See [`CLAUDE.md`](./CLAUDE.md). The non-negotiables:

- **Temporal owns durable execution; workflows are deterministic shells.**
  LangGraph runs inside the activity — never in a workflow.
- **FastAPI is ingress only.** No durable work in handlers; no
  `BackgroundTasks` for orchestration.
- **API is the only write surface** for mesh Task state. LangGraph thread state
  is working memory, not authoritative.
- **Tool Gateway owns all tool credentials.** Cloudflare AI Gateway is LLM
  egress only.
- **No raw secrets in prompts or graph state.** Injected at runtime; redacted
  at the boundary.
- **No unledgered spawns.** A durable SpawnLedger row precedes every child.
- **Persistent checkpointer is mandatory.** `AsyncPostgresSaver` everywhere but
  unit tests.
- **Eight egress guards, in fixed order, no LLM in the loop.**
- **Archive before delete.** Soft-archive first; hard delete is separate and
  audited.
- **Knowledge Layer is a cache, not a source of truth.**
- **Verification is egress-only.**
- **LangGraph state carries refs, not raw payloads.**

---

## Context and Evidence Knowledge Layer

A tenant-scoped substrate that gives agents sufficient, governed, source-aware
context. KL provides:

- **Cache** of recent reads from external tools, keyed by
  `(tenant_id, source_system, source_id)`, with optional `content_hash`.
- **Index** (pgvector) for fast retrieval of relevant prior context.
- **Evidence pointers** — every entry carries an `evidence_pointer` back to the
  system of record it came from, plus a `freshness` verdict.
- **Append-only versioned writes** addressed as `kl:{tenant}:{source}/{path}#v{n}`.

LLMs never write KL entries directly. KL is consumed at read time and
referenced at egress through a **`ClaimEvidenceMap`** sidecar that binds each
output claim to evidence refs. The eight **deterministic egress guards** then
enforce schema, evidence presence/resolvability, freshness, source authority,
tenancy, tier/policy, and budget — no LLM in the loop.

---

## Intake contract and S-tier feasibility

Inbound requests from the entry plane produce an **`Intake`** artifact *before*
a Task is created. Intake runs three cheap checks:

1. **Schema parse** of the canonical intake payload.
2. **Tool-plan lookup** against the routine/release registry.
3. **One S-tier classifier call** producing `feasible | ambiguous | infeasible`.

Ambiguous intents produce one disambiguating question. Silent escalation above
S-tier at intake is a bug. Feasibility is decided once at intake — not re-run
mid-stream. The Task references the intake via `Task.intake_id`.

---

## Edge security/governance vs mesh execution

The mesh **does not** implement enterprise edge controls. It expects a generic
**edge control contract** in front of it.

| Concern | Owner |
|---|---|
| Identity binding, OAuth/OIDC, session | **Edge layer** |
| Ingress/egress normalization | **Edge layer** |
| Policy preflight, safety, DLP, classification | **Edge layer** |
| Approval UX, audit envelope | **Edge layer** |
| Task decomposition, durable orchestration | **Mesh (this repo)** |
| Knowledge Layer, swarm supervision | **Mesh (this repo)** |
| Routines, releases, evaluator, eight egress guards | **Mesh (this repo)** |
| Tool gateway, credentials, budgets | **Mesh (this repo)** |

[Floodplain](https://github.com/SirFreud/floodplain/tree/rli-0.01) (branch
`rli-0.01`) is **one possible** edge implementation. It is *not* a required
dependency, and the mesh's egress guards run defense-in-depth regardless of
which edge is in front.

---

## License

TBD. Treat as private until a license is added.
