<!-- refreshed: 2026-06-05 -->
# Architecture

**Analysis Date:** 2026-06-05

## System Overview

This is a reusable, governed autonomous agent mesh POC built on **LangChain + LangGraph + Deep Agents + Langfuse**, designed for small consultancies and client delivery teams. The architecture separates a stable reusable platform boundary from deployment-specific client/SaaS bindings.

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                           INGRESS LAYER                                      │
├──────────────────────────┬──────────────────────────┬───────────────────────┤
│  Slack App Ingress       │  MCP HTTP Ingress        │  Direct API Ingress   │
│  (Slack Events API)      │  (Claude Desktop/Code)   │  (/v1/tasks)          │
│  `src/agent_mesh/api/`   │  `src/agent_mesh/api/`   │  `src/agent_mesh/api/ │
└──────────────┬───────────┴───────────────┬──────────┴───────────────────────┘
               │                           │
               └───────────┬───────────────┘
                           │
                ┌──────────▼────────────┐
                │  Shared Task Service  │
                │ `services/task_service.py`
                │ - Normalize all ingress into
                │   canonical TaskRequest
                │ - Create TaskRecord
                │ - Dispatch to queue
                └──────────┬────────────┘
                           │
                ┌──────────▼──────────────────┐
                │  Dispatcher / Pub/Sub        │
                │  `services/dispatch.py`     │
                │  - In-memory (POC)          │
                │  - Pub/Sub ready (prod)     │
                └──────────┬───────────────────┘
                           │
        ┌──────────────────▼──────────────────────┐
        │   ORCHESTRATION / EXECUTION LAYER       │
        ├──────────────────────────────────────────┤
        │  Worker (Cloud Run Job / Worker Pool)   │
        │  `src/agent_mesh/worker/`               │
        │                                          │
        │  1. Resume task from durable state      │
        │  2. Run LangGraph + Deep Agents mesh    │
        │  3. Gate proposed writes via approval   │
        │  4. Execute approved tool calls         │
        │  5. Emit observability telemetry        │
        └──────────┬───────────────────────────────┘
                   │
        ┌──────────┴─────────────────────┐
        │                                 │
        ▼                                 ▼
    ┌──────────────────────┐    ┌──────────────────┐
    │  Approval Ledger     │    │  Tool Gateway    │
    │ (shared, HITL pause) │    │ (+ Credentials)  │
    │ `services/approvals` │    │  `tools/gateway` │
    └──────────────────────┘    └──────────────────┘
        │
        ▼
    ┌──────────────────────┐
    │  Approval Decision   │
    │  Callback            │
    │  (Slack/MCP/API)     │
    └──────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                          DURABLE STATE LAYER                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  Cloud SQL PostgreSQL (australia-southeast1) + pgvector                      │
│  `migrations/0001_init.sql`, `0002_self_improvement.sql`                     │
│                                                                              │
│  Tables (tenant-partitioned):                                               │
│  - tasks, task_events (lifecycle audit trail)                               │
│  - sessions, session_summaries (operational state)                          │
│  - memory_chunks, evidence_chunks (separate retrieval/long-term memory)     │
│  - tool_calls (tool invocation audit)                                       │
│  - approval_records (shared approval ledger)                                │
│  - ai_bom_snapshots (versioned capability inventory)                        │
│  - budget_ledger (model token/cost tracking)                                │
│  - gateway_events (model provider logs, Cloudflare correlation)             │
│  - langgraph_checkpoints (durable >60-min run state)                        │
│  - self_improvement_proposals, evaluations, promotions                      │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                         OBSERVABILITY PLANE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  Langfuse (REQUIRED: traces, prompts, evals, token/cost, audit dashboards) │
│  `src/agent_mesh/observability.py`                                          │
│  - LangChain/LangGraph callback handler integration                         │
│  - Shared trace metadata (tenant, task, session, requester, approval_state) │
│  - Correlates model calls + Cloudflare AI Gateway decisions + tool calls    │
│                                                                              │
│  Cloudflare AI Gateway (integration-ready: DLP, query blocking, guardrails) │
│  `cloudflare/ai-gateway-wrapper/`                                           │
│  - Model-traffic governance (separate from LiteLLM control plane)           │
│  - Logging, payload inspection, rate limiting                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                       MODEL ACCESS LAYER                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  LiteLLM-compatible Gateway (control plane)                                  │
│  `src/agent_mesh/worker/model_gateway.py`                                   │
│  `config/model_gateway.config.yaml`                                         │
│                                                                              │
│  Separates control from governance:                                         │
│  - Routing (Anthropic direct, Vertex AI)                                    │
│  - Cascades/fallbacks per task complexity                                   │
│  - Per-user & per-task budget enforcement (USD 50/month default)           │
│  - Token/max-output limits                                                  │
│  - Cost attribution                                                         │
│  - Upstream: Cloudflare AI Gateway → Model providers                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| **Task Service** | Single entry point for all ingress (Slack/MCP/API); creates, dispatches, and resumes tasks; records approvals | `src/agent_mesh/services/task_service.py` |
| **Repository** | Abstract durable store (in-memory POC; Postgres in prod); persists tasks, sessions, approvals, tool calls, AI-BOM | `src/agent_mesh/services/repository.py` |
| **Dispatcher** | Queues tasks for worker consumption (in-process POC; Pub/Sub in prod) | `src/agent_mesh/services/dispatch.py` |
| **Worker Runner** | Consumes task from queue; orchestrates with LangGraph mesh; gates writes via approval ledger | `src/agent_mesh/worker/runner.py` |
| **Orchestrator (LangGraph adapter)** | Invokes LangChain/LangGraph/Deep Agents supervisor with bounded subagent roster (planner, researcher/tool-router, code-writer, reviewer) | `src/agent_mesh/worker/orchestrator.py` |
| **Approval Gating** | Opens approval requests for write-class actions; records decisions with payload-hash binding; blocks replay | `src/agent_mesh/services/approvals.py` |
| **Tool Gateway** | Loads per-client tool-pack manifests; validates categories vs approval requirements; stub execution (real adapters in prod) | `src/agent_mesh/tools/gateway.py` |
| **Model Gateway** | Routes model requests through LiteLLM to Anthropic/Vertex; enforces budgets, cascades, cost attribution | `src/agent_mesh/worker/model_gateway.py` |
| **Self-Improvement Loop** | Ingests proposals; evaluates; requires HITL approval; promotes to versioned, rollback-able capability (no silent mutation) | `src/agent_mesh/services/self_improvement.py` |
| **Observability Seam** | Langfuse callback handler + shared trace metadata for all spans, token usage, cost, task/tool correlation | `src/agent_mesh/observability.py` |
| **Contract Models** | Pydantic v2 schemas + lifecycle state machine + JSON Schema export for all data structures | `src/agent_mesh/contracts/` |
| **API Ingress** | FastAPI service: /healthz, /v1/tasks, /slack/events (signature-verified, 3s ack), /v1/approvals | `src/agent_mesh/api/app.py` |
| **Slack Verification** | Cryptographic verification of Slack request signatures; timestamp tolerance | `src/agent_mesh/api/slack_verify.py` |
| **MCP Server** | Streamable HTTP endpoint for Claude Desktop/Claude Code; normalizes MCP tool calls to TaskRequest | `src/agent_mesh/api/mcp_server.py` |
| **Budget Tracker** | Tracks model token usage and cost per user/task; enforces monthly ceiling | `src/agent_mesh/worker/budget.py` |
| **Sandbox Executor** | Executes generated code in isolated subprocess (production: Docker/Cloud Run Job); resource limits | `src/agent_mesh/sandbox/executor.py` |
| **GUI Admin Console** | Streamlit read-model app for operator visibility: tasks, approvals, toolpacks, AI-BOM, budget, self-improvement | `src/agent_mesh/gui/admin_app.py` |

## Pattern Overview

**Overall:** Reusable, governed, multi-agent orchestration mesh with durable checkpoints, human-in-the-loop approval gating, and tenant partitioning.

**Key Characteristics:**

- **Normalized Ingress:** All entry points (Slack, MCP, API) funnel into a shared `TaskRequest` contract and task lifecycle state machine so capabilities are mirrored.
- **Durable by Design:** Tasks and state persist in Cloud SQL before long-running execution; LangGraph checkpoints enable resumability after approval decisions or restarts.
- **Write-Action Approval Gating:** Every write-class tool (write, external_send, financial, publishing, admin, code) is gated: proposed → approval request → human decision (Slack/MCP) → execution or rejection. Payload hash prevents replay after mutation.
- **Supervisor-Orchestrated Subagent Roster:** LangGraph runs a supervisor that delegates to a bounded, declared team (planner, researcher/tool-router, code-writer, reviewer); no uncontrolled self-spawning.
- **Separated Gateway Planes:** LiteLLM-compatible gateway owns model routing, budgets, cascades (control plane); Cloudflare AI Gateway owns logging, DLP, query blocking, guardrails (governance plane). Neither replaces tool-write approval gates.
- **Tenant Partitioning:** Every record carries `tenant_id` and `client_slug`; one schema backs many client redeployments without data leakage.
- **Self-Improvement (Option C):** Proposals are inert until evaluated, human-approved, and versioned-promoted. No runtime mutation of live instructions, permissions, or routing.
- **Langfuse-Centered Observability:** All spans, prompts, token/cost, task/tool/approval events correlate into Langfuse for audit and analytics.

## Layers

**Ingress Layer:**
- Purpose: Accept tasks from Slack, MCP (Claude Desktop/Code), or HTTP API.
- Location: `src/agent_mesh/api/`
- Contains: FastAPI application, Slack signature verification, MCP HTTP server stub, approval callback endpoint.
- Depends on: Task service, settings.
- Used by: External Slack App, MCP clients, CI/CD scripts.

**Task Orchestration Layer:**
- Purpose: Normalize all ingress into a shared task contract; persist durable state; dispatch to workers.
- Location: `src/agent_mesh/services/task_service.py`, `dispatch.py`, `sessions.py`, `repository.py`
- Contains: Task service (create/get/transition), dispatcher (in-process or Pub/Sub), session management, in-memory repository (production: Postgres).
- Depends on: Contract models, settings.
- Used by: Ingress services, worker runner.

**Worker Execution Layer:**
- Purpose: Consume tasks; run LangGraph + Deep Agents orchestration; gate writes; execute approved actions.
- Location: `src/agent_mesh/worker/`
- Contains: Runner (task consumer, approval pause/resume), orchestrator (LangGraph adapter, degrades to stub), model gateway (routing/budgets), budget tracker.
- Depends on: Repository, tool gateway, approvals service, observability seam.
- Used by: Cloud Run Jobs / Worker Pools.

**Approval & Tool Layer:**
- Purpose: Gate write-class actions; load and execute tools; track tool invocations.
- Location: `src/agent_mesh/services/approvals.py`, `src/agent_mesh/tools/gateway.py`
- Contains: Approval ledger (open/decide/validate with payload hash), tool pack loader (YAML manifest), tool execution stub.
- Depends on: Repository, contract models.
- Used by: Worker runner, ingress (approval callbacks).

**Self-Improvement & Governance Layer:**
- Purpose: Ingest proposals from agents; evaluate; require human approval; promote versioned changes without runtime mutation.
- Location: `src/agent_mesh/services/self_improvement.py`
- Contains: Proposal ingestion, risk classification, evaluation hooks, promotion with rollback.
- Depends on: Repository, approvals service.
- Used by: Worker (after task completion); admin console.

**Data Layer:**
- Purpose: Persist all durable state: tasks, approvals, tool calls, memory/evidence, AI-BOM, budgets, LangGraph checkpoints.
- Location: `migrations/0001_init.sql`, `0002_self_improvement.sql`
- Contains: Tenant-partitioned tables; separate evidence/memory; append-only audit trail; pgvector indexes.
- Depends on: PostgreSQL 13+, pgvector extension.
- Used by: Repository abstraction.

**Observability Layer:**
- Purpose: Emit spans, prompts, token/cost, task/approval events to Langfuse; correlate with Cloudflare AI Gateway logs.
- Location: `src/agent_mesh/observability.py`
- Contains: Langfuse callback handler factory, shared trace metadata builder.
- Depends on: Langfuse client (optional).
- Used by: Worker, model gateway.

**Cloudflare AI Gateway Layer:**
- Purpose: Model-traffic governance, logging, DLP, query blocking, guardrails.
- Location: `cloudflare/ai-gateway-wrapper/` (Cloudflare Worker + wrangler config)
- Contains: Worker script to wrap AI Gateway; authentication; metadata attachment.
- Depends on: Cloudflare account + AI Gateway.
- Used by: LiteLLM-compatible gateway (upstream).

**Contract & Schema Layer:**
- Purpose: Define durable data contracts for all models, lifecycle state machine, JSON Schema export.
- Location: `src/agent_mesh/contracts/models.py`, `lifecycle.py`, `enums.py`, `export_schemas.py`
- Contains: Pydantic v2 models (TaskRecord, ApprovalRecord, ToolCall, etc.), state transitions, risk enums.
- Depends on: Pydantic v2.
- Used by: All layers (via imports).

## Data Flow

### Primary Request Path (Write-Gated Action)

1. **Slack/MCP/API creates task** (`src/agent_mesh/api/app.py:create_task` or `slack_events`)
   - Signature-verify (Slack); normalize to `TaskRequest` contract.
   - Call `TaskService.create_task(request)`.

2. **Task service persists and dispatches** (`src/agent_mesh/services/task_service.py:create_task`)
   - Ensure session exists.
   - Create `TaskRecord`, persist via `repo.create_task()`.
   - Transition to `QUEUED` state.
   - Publish task ID to dispatcher (in-process queue or Pub/Sub).
   - Return `TaskRecord` with state to ingress.

3. **Ingress acknowledges immediately** (required for Slack 3-second ack limit).
   - Return HTTP 200 to Slack; async processing continues.
   - Return `{"task_id": "...", "state": "queued"}` to API/MCP client.

4. **Worker picks up task** (`src/agent_mesh/worker/runner.py:process`)
   - Get task from repository.
   - If terminal state → return.
   - If `APPROVED` state → skip to resume path.
   - Otherwise transition to `RUNNING`.

5. **Run orchestration** (`src/agent_mesh/worker/orchestrator.py:run_mesh`)
   - If LangGraph available → `_run_langgraph()` (real: supervisor graph + subagents).
   - Else → `_run_stub()` (heuristic: detect write-triggering words; propose dummy write).
   - Return `OrchestrationResult` with summary + proposed writes.

6. **Gate proposed writes** (`src/agent_mesh/worker/runner.py:process` continued)
   - For each proposed write:
     - Create `ToolCall` with status `AWAITING_APPROVAL`.
     - Build `ApprovalRequest` with payload hash of parameters.
     - Call `approvals.open_approval()` to persist `ApprovalRecord`.
     - Update task state to `AWAITING_APPROVAL`.
   - Return control to worker consumer (task paused).

7. **Approval decision arrives** (Slack button, MCP endpoint, or API callback)
   - POST `/v1/approvals` with `approval_record_id`, `decision` (APPROVED/REJECTED), `approver_id`, `channel`.
   - Call `TaskService.submit_approval_decision()`.
   - Update `ApprovalRecord` with decision + approver + timestamp.
   - If `APPROVED` → transition task to `APPROVED` state; re-publish task ID to dispatcher.
   - If `REJECTED` → transition task to `REJECTED` state (terminal).

8. **Worker resumes** (re-consumes from queue)
   - Get task, detect state is `APPROVED`.
   - Call `_resume_after_approval()`.
   - For each pending `ToolCall`:
     - Fetch `ApprovalRecord`.
     - Call `approvals.is_approved(record, call.parameters)` — checks decision is APPROVED AND payload hash matches (prevents replay).
     - If approved → execute tool via gateway (`self._execute(call)`).
     - Update `ToolCall` status to `EXECUTED`, store result.
     - If rejected → update status to `REJECTED`.
   - Transition task to `COMPLETED`.

9. **Task completion** (query via GET `/v1/tasks/{task_id}`)
   - Return `TaskRecord` with final state, summary, and result.

### Secondary Flow: Read-Only (No Approval)

1. Same as steps 1–5 above.
2. **Orchestration returns no writes** → `OrchestrationResult.proposed_writes` is empty.
3. Worker transitions task directly to `COMPLETED` without approval pause.
4. Task is terminal.

**State Management:**

- All state transitions are durable: persisted in `tasks` table + audit trail in `task_events`.
- LangGraph checkpoints (in prod) store intermediate graph state in `langgraph_checkpoints` table so resumability survives process restarts.
- Approval records are immutable once decided: `ApprovalRecord.decided_at`, `approver_id`, `channel` are write-once.

## Key Abstractions

**TaskRequest & TaskRecord:**
- Purpose: Normalize all ingress payloads into a shared contract; persist durable task state.
- Examples: `src/agent_mesh/contracts/models.py` — `TaskRequest` (inbound), `TaskRecord` (durable).
- Pattern: Pydantic v2 BaseModel with enum-based serialization (`use_enum_values=True`) so JSON is clean and values are distinct from enum objects.

**Lifecycle State Machine:**
- Purpose: Define legal task state transitions; keep Temporal-ready.
- Examples: `src/agent_mesh/contracts/lifecycle.py` — `can_transition()`, `assert_transition()`, `ALLOWED` transition table.
- Pattern: Static lookup table; all ingress/worker/tests call `assert_transition()` before any update to catch bugs early.

**Tenant Partitioning:**
- Purpose: One schema backs many client deployments without data leakage; every record carries `tenant_id` and `client_slug`.
- Examples: All `TaskRecord`, `ApprovalRecord`, `ToolCall`, memory/evidence chunks include `tenant_id`.
- Pattern: Index and query on `(tenant_id, ...)` for isolation; migrations use `IF NOT EXISTS` so re-apply is safe.

**Approval Payload Hash:**
- Purpose: Bind an approval decision to an exact action; prevent replay if parameters mutate.
- Examples: `src/agent_mesh/services/approvals.py` — `payload_hash()` (canonical JSON → SHA-256), `is_approved()` (check decision + hash match).
- Pattern: Canonical JSON (sort keys, no spaces) ensures re-serialization of the same logical payload yields the same hash.

**Tool Pack Manifest:**
- Purpose: Declare per-client SaaS tools (name, category, credential secret, approval requirement, integration style).
- Examples: `manifests/tool_pack_manifest.yaml` — tools from Xero, HubSpot, Webflow, Google Workspace, etc.; each declares `approval_required` based on category.
- Pattern: YAML → ToolSpec dataclass; `ToolGateway.from_manifest()` loads and validates (write-class tools must require approval).

**Model Route Profile:**
- Purpose: Define task-tier routing to Anthropic-direct or Vertex AI; separate concerns (routing vs. governance).
- Examples: `config/model_gateway.config.yaml` — profiles (mixed-cascade, anthropic-direct); per-complexity preferred/fallback models.
- Pattern: LiteLLM reads the config; selects based on `model_route_profile` in task; Cloudflare AI Gateway is always downstream.

**Deep Agents Roster:**
- Purpose: Bounded, supervisor-orchestrated subagent team (planner, researcher/tool-router, code-writer, reviewer); not a free-spawning swarm.
- Examples: `src/agent_mesh/worker/orchestrator.py` — real implementation builds LangGraph with supervisor node delegating to fixed roster.
- Pattern: Declared in code; roster members are configured with isolated context; no dynamic agent creation.

**Evidence vs. Memory Separation:**
- Purpose: Keep retrieval/tool-call evidence (e.g., documents, source excerpts) separate from long-term memory (summaries, routines, learnings).
- Examples: `migrations/0001_init.sql` — `memory_chunks` (reusable semantic), `evidence_chunks` (retrieval), `tool_evidence_chunks` (tool audit).
- Pattern: Separate tables, separate embedding indexes; operational state never mixes with retrieval corpus.

## Entry Points

**HTTP Ingress (FastAPI):**
- Location: `src/agent_mesh/api/app.py`
- Triggers: POST `/v1/tasks` (API), POST `/slack/events` (Slack App), POST `/v1/approvals` (decision callback), GET `/v1/tasks/{id}` (status query), GET `/healthz` (liveness).
- Responsibilities: Signature verify (Slack), normalize payloads to TaskRequest, delegate to TaskService, return fast ack.

**MCP HTTP Ingress:**
- Location: `src/agent_mesh/api/mcp_server.py` (stub; production uses Anthropic SDK).
- Triggers: POST `/mcp` with tool name + arguments.
- Responsibilities: Map MCP tool call to TaskRequest; create task via TaskService; correlate requester identity.

**Worker Consumer:**
- Location: `src/agent_mesh/worker/main.py` (entrypoint).
- Triggers: Task ID from in-process queue (POC) or Pub/Sub subscription (prod).
- Responsibilities: Call `Worker.process(task_id)`; handle approval pause/resume; emit observability events.

**Admin GUI:**
- Location: `src/agent_mesh/gui/admin_app.py` (Streamlit).
- Triggers: HTTP GET on GUI Cloud Run service URL.
- Responsibilities: Read-model queries to repository for tasks, approvals, toolpacks, AI-BOM, self-improvement proposals, budget/routing, memory; operator dashboards.

**Self-Improvement Promotion:**
- Location: `src/agent_mesh/services/self_improvement.py` (API called from GUI or admin CLI).
- Triggers: Manual operator action (approve promotion) or automated evaluation hook.
- Responsibilities: Validate proposal has passed evaluation + approval; version and persist promotion record; emit rollback capability.

## Architectural Constraints

- **Threading:** Single-threaded event loop per ingress service (FastAPI + uvicorn). Worker processes are single-threaded (LangGraph + Deep Agents are sync); Cloud Run Jobs are isolated per task. No shared mutable state across processes.
- **Global state:** Minimal: settings singleton (`Settings` Pydantic model), optional Langfuse/Slack/Cloudflare API clients (lazy-imported). Repository and dispatcher are injected (testable). No module-level task stores; all state persists to Cloud SQL (prod) or in-memory dict (POC).
- **Circular imports:** None detected. Contracts (`models.py`, `lifecycle.py`, `enums.py`) have no dependencies on services; services import contracts. Observability seam imports settings but not vice versa.
- **Durable checkpoints:** LangGraph checkpoints are stored in Postgres table `langgraph_checkpoints` (prod); in-memory list (POC stub). Checkpoint key is `task_id` so resumption is deterministic.
- **Tenant isolation:** Query and index on `(tenant_id, ...)` to prevent cross-tenant leakage. Test fixtures use distinct `tenant_id` values. In-memory repository uses dict keys like `(tenant_id, resource_id)` to simulate isolation.

## Anti-Patterns

### Uncontrolled Subagent Spawning

**What happens:** If the supervisor node is replaced with a pattern that dynamically creates new agents at runtime without bounds, the mesh becomes an uncontrolled swarm. Token usage, observability, and safety guarantees collapse.

**Why it's wrong:** The POC's core safety model is a **declared, bounded roster** (planner, researcher/tool-router, code-writer, reviewer). Observability traces every subagent's input/output via Langfuse. Budget enforcement is per-task, not per-subagent. Approval gating depends on knowing which agents can propose writes. Dynamic spawning breaks all three.

**Do this instead:** Keep the roster fixed and declared in code (or in a versioned manifest loaded at startup). If flexibility is needed (e.g., per-client rosters), load from `AI-BOM snapshot` rather than creating agents dynamically. Test the roster size and log it at startup.

### Silent Self-Improvement (Autonomous Mutation)

**What happens:** A proposal becomes active (mutates system prompts, tool permissions, routing rules) without explicit human approval and without versioning. Rollback is impossible; audit trails don't capture the activation.

**Why it's wrong:** Proposals in the POC are **inert artifacts** until promoted. Promotion requires:
  1. Evaluation passing (deterministic checks or human review pending).
  2. An `ApprovalRecord` with `decision=APPROVED` and unchanged payload hash.
  3. Explicit call to `promote()` which writes a `PromotionRecord`.

Silent mutation breaks the approval gate and auditing.

**Do this instead:** Every proposal starts in `PROPOSED` status. Evaluate deterministically (or mark `PENDING_EVALUATION`). Open an approval request if needed. Only after APPROVED does `promote()` create a versioned `PromotionRecord`. Do NOT update live system config based on a proposal. Instead, the PromotionRecord is an artifact; wiring it into production is a separate, manual, operator-owned step.

### Approval Replay (Mutated Payload)

**What happens:** An approval for parameters `{"deal_name": "Acme Inc", "stage": "appointmentscheduled"}` is issued. The agent later mutates the parameters to `{"deal_name": "Acme Inc", "stage": "closedwon"}` and tries to re-use the same approval.

**Why it's wrong:** The approval is bound to a payload hash. If the payload changes, the hash no longer matches, and `is_approved()` returns False. But if the code skips the hash check (or always replays the same approval), the wrong action executes.

**Do this instead:** Always call `approvals.is_approved(record, call.parameters)` which checks both the decision AND the payload hash match. Never execute a tool call without verifying the current parameters match the approved payload. Tool calls are immutable once approved; if parameters need to change, a new approval is required.

### Single-Gateway Architecture (Conflating Control & Governance)

**What happens:** A single gateway owns both model routing (control plane) and DLP/query blocking (governance plane). Policy changes affect routing; observability is blind to governance decisions.

**Why it's wrong:** The POC deliberately separates them:
  - **LiteLLM-compatible gateway** (control plane): model selection, cascades, budgets, cost attribution.
  - **Cloudflare AI Gateway** (governance plane): logging, DLP, query blocking, guardrails.

Conflating them means policy can accidentally break routing; observability can't tell the difference between a deliberate governance block and a routing fallback.

**Do this instead:** Keep the planes separate. LiteLLM always routes upstream through Cloudflare AI Gateway. Cloudflare logs/blocks/guardrails are separate from routing decisions. Langfuse correlates both planes' decisions via shared request metadata (`tenant_id`, `task_id`, etc.).

## Error Handling

**Strategy:** Fail fast with clear error messages; persist error state in `TaskRecord.error` field; emit events to audit trail; do NOT auto-retry at the agent level (retries are a worker/queue concern).

**Patterns:**

- **Illegal state transitions:** `lifecycle.assert_transition()` raises `IllegalTransition` before any update. Caller catches and logs.
- **Missing task:** Worker catches `KeyError` from `repo.get_task()` and logs. Never escalates to cloud infrastructure.
- **Approval not found:** `approvals.record_decision()` raises `KeyError` if approval record doesn't exist. Ingress returns 400 Bad Request to caller.
- **Tool execution failure:** `ToolGateway.execute()` (stub) always succeeds. In production, real adapters would catch API errors, wrap in `ExecutionError` with retry metadata, and store in `ToolCall.result["error"]`. Worker logs and transitions task to FAILED (or queues for retry).
- **Model API errors:** LiteLLM gateway layer catches provider timeouts/rate limits and invokes fallback routing. Langfuse traces all attempts. If all cascades exhaust, task transitions to FAILED with error summary.
- **Approval deadline exceeded:** If approver doesn't respond within a configurable window, task auto-cancels and stores deadline timestamp. Audit trail notes the reason.

## Cross-Cutting Concerns

**Logging:** Built into FastAPI via uvicorn; workers use Python logging module. All state transitions, approval decisions, tool invocations, and observability events are logged with `task_id` / `approval_record_id` for correlation. Logs flow to Cloud Logging (GCP) in production.

**Validation:** Pydantic v2 validates all inbound contracts (TaskRequest, ApprovalRequest, etc.) at the API boundary. Lifecycle state machine validates transitions. ToolSpec validates that write-class tools declare approval_required. No data enters the system without type/schema checking.

**Authentication:** Slack signature verification (HMAC-SHA-256 of timestamp + body). MCP uses OAuth resource-server mode (token validation via upstream). Cloudflare AI Gateway uses API token authentication. All credentials stored in Google Secret Manager (GCP) or environment variables (local POC). Never logged.

**Authorization:** Every task carries a `requester` identity (Slack user ID, MCP subject, or API key holder). Approval decisions must be made by the requester OR a designated approver (configured per client). Tool Gateway access is gated: agents never receive raw credentials; the gateway resolves them at execution time against a `credential_secret_name` from the tool pack manifest.

**Audit Trail:** `task_events` table is append-only. Every state transition, approval decision, tool call, and self-improvement promotion creates a new event with timestamp and optional payload. Retention: 12 months (configurable per deployment manifest). Langfuse traces provide a second audit layer: every agent decision, tool call, and model invocation is recorded.

---

*Architecture analysis: 2026-06-05*
