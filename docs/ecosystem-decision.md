# Ecosystem & Language Decision: LangChain / LangGraph / Deep Agents / Langfuse, Python-First, TypeScript at the Edge

## Decision

The agent mesh is built on the **LangChain + LangGraph + Deep Agents + Langfuse**
stack, implemented **Python-first**. TypeScript is used **only at the edge** —
specifically the Cloudflare Worker that wraps the AI Gateway
(`cloudflare/ai-gateway-wrapper/`), where the runtime is V8/Workers and TS is the
native choice.

Everything else — contracts, ingress (Slack/MCP/API), the shared task service,
the dispatch layer, the LangGraph + Deep Agents worker, the prompt-to-code
sandbox, the GUI admin console, and the tooling — is Python.

## Why this stack (default required)

- **LangChain (REQUIRED)** — the reusable tool/model abstraction. Tools, chat
  models, and the callback system are the shared vocabulary the rest of the stack
  builds on. The model gateway is reached through LangChain's `ChatLiteLLM`-style
  binding so providers stay swappable.
- **LangGraph (REQUIRED)** — durable orchestration. State graphs give explicit,
  inspectable control flow; checkpoints make >60-minute runs resumable; and
  `interrupt`-based human-in-the-loop pauses implement the write-approval gate as a
  first-class graph primitive rather than ad-hoc plumbing. In production the
  checkpointer is Postgres, matching the Cloud SQL durable store.
- **Deep Agents (REQUIRED)** — the subagent harness. Deep Agents builds on
  LangGraph and gives a **supervisor-orchestrated, bounded, observable** team
  (planner, researcher/tool-router, code-writer, reviewer) with isolated context.
  This is deliberately **not** an uncontrolled self-spawning swarm: the roster is
  declared and fixed, which keeps the blast radius and the AI-BOM tractable.
- **Langfuse (REQUIRED)** — observability. Open-source and self-hostable, it
  provides tracing, prompt/version management, datasets/evals, and token/cost
  telemetry, and integrates with LangChain (callback handler), OpenTelemetry, the
  OpenAI SDK, and LiteLLM. It is the audit/telemetry backbone for the mesh.
- **LangSmith (NOT required)** — an optional alternative to Langfuse only. It is
  never a runtime dependency; the deployment manifest pins `langsmith_enabled: false`.

## Why Python for the core

- **The stack is Python-native.** LangChain, LangGraph, and Deep Agents are Python
  libraries; a Python core avoids a cross-language boundary on the hottest path.
- **LiteLLM-compatible gateway is Python-backed.** The model control plane
  (routing, cascades, budgets, token caps, Anthropic-direct + Vertex AI) is
  configured and extended in Python.
- **Official MCP Python SDK** supports servers, clients, and transports (including
  Streamable HTTP) with Pydantic structured output — the same Pydantic v2 models
  used for the task contract serve double duty as MCP tool schemas. Claude Desktop
  and Claude Code are first-class MCP clients.
- **Slack Bolt for Python** gives first-class Events API + signature handling.
- **One contract source of truth.** Pydantic v2 models define the task lifecycle,
  approvals, tool calls, evidence, AI-BOM, and budget events, and JSON Schema is
  *exported* from them (`agent_mesh.contracts.export_schemas`) so non-Python
  consumers (the Worker, MCP clients, dashboards) share the contract without
  duplicating definitions.

## Why TypeScript only at the edge

- The Cloudflare AI Gateway wrapper runs on the Workers runtime, where TS/JS is the
  supported language and Wrangler tooling expects it.
- The edge wrapper has a narrow job (forward model traffic, attach metadata) and
  consumes the JSON Schema exported from the Python contracts, so the language
  split does not fragment the contract.

## Pros / Cons

| | Python-first core (LangChain/LangGraph/Deep Agents/Langfuse) | Alternative: TS-first core |
| :-- | :-- | :-- |
| LangGraph orchestration | Native, no FFI | LangGraph.js exists but loses Deep Agents + Python ecosystem |
| Deep Agents | Native | No first-class equivalent; reimplement or bridge |
| Langfuse | Native SDK + LangChain callback | SDK exists; fine, but core would still be split |
| LiteLLM gateway | Native config/extension | Subprocess/HTTP bridge |
| MCP SDK | Official, Pydantic-integrated | TS SDK exists but loses Pydantic reuse |
| Slack | Bolt for Python | Bolt for JS (fine) |
| Contract reuse | Pydantic → JSON Schema export | Would still need schema export |
| Edge worker | TS (unavoidable) | TS (native) |

Trade-off accepted: a two-language repo. Mitigated by keeping the boundary thin
(only the edge worker is TS) and by exporting one canonical JSON Schema from the
Python contracts so both sides agree.

## Portability note

The stack is portable in principle across AWS/GCP/Azure: LangChain/LangGraph/Deep
Agents/Langfuse and the LiteLLM-compatible gateway are cloud-agnostic. The first
MVP/POC targets GCP (`australia-southeast1`) for durable stores; the platform/client
boundary keeps the cloud-specific pieces (Cloud Run, Cloud SQL, Pub/Sub, Secret
Manager) replaceable.

## Repo layout implication

```
src/agent_mesh/            # Python core (importable as `agent_mesh`)
  contracts/               # Pydantic models, enums, lifecycle, schema export
  services/                # repository, dispatch, sessions, task_service, approvals, self_improvement
  api/                     # FastAPI app, Slack verify, MCP server
  worker/                  # orchestrator (LangGraph + Deep Agents adapter), model_gateway, runner, budget, main
  observability.py         # Langfuse seam (callback handler, trace metadata)
  sandbox/                 # prompt-to-code executor
  tools/                   # tool gateway + tool-pack loader
  gui/                     # Streamlit admin/operator console (read-model helpers + app)
schemas/                   # exported JSON Schema (contracts/) + sample tool schemas
migrations/                # Cloud SQL Postgres + pgvector SQL
config/model_gateway.config.yaml # LiteLLM-compatible routing/budgets via Cloudflare AI Gateway
cloudflare/ai-gateway-wrapper/   # TS edge worker (the only TypeScript)
docker/                    # api / worker / code-executor / gui images
scripts/                   # idempotent gcloud + wrangler deploy scripts
tests/                     # contract, approval-gating, self-improvement, stack/toolpacks, import, slack-verify, smoke
```

The Python package installs with optional extras (`runtime`, `agents`, `gui`,
`dev`) so the contract/schema layer and tests run in a minimal environment while
the worker/ingress/GUI images install the full set. Heavy deps (`langchain`,
`langgraph`, `deepagents`, `langfuse`, `streamlit`, `google-cloud-pubsub`, `mcp`)
are lazy-imported and degrade to stubs so the package stays importable without them.
