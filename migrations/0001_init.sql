-- Agent Mesh POC — initial schema for Cloud SQL for PostgreSQL + pgvector.
-- Region: australia-southeast1 (durable store stays in Australia).
--
-- Design principles enforced here:
--   * Tenant partitioning: every table carries tenant_id (and client_slug where
--     relevant) so one schema backs many redeployments without mixing contexts.
--   * Separation of concerns: retrieval/evidence chunks live in their own tables
--     (retrieval_document_chunks, tool_evidence_chunks), kept apart from session
--     summaries (session_summaries) and task metadata (task_metadata).
--   * Audit trail: task_events is append-only; approvals, tool calls, budget, and
--     gateway events are durable for the 12-month retention profile.
--
-- This migration is idempotent: it uses IF NOT EXISTS so it can be re-applied.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- gen_random_uuid()

-- Embedding dimension. 768 suits Vertex text-embedding / Gemini embedding output.
-- Change here if a different embedding model is selected per deployment.

-- ---------------------------------------------------------------------------
-- Tasks and lifecycle
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    task_id             TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    client_slug         TEXT NOT NULL,
    entrypoint          TEXT NOT NULL,
    session_id          TEXT NOT NULL,
    requester_id        TEXT NOT NULL,
    requester           JSONB NOT NULL DEFAULT '{}'::jsonb,
    prompt              TEXT NOT NULL,
    state               TEXT NOT NULL DEFAULT 'received',
    model_route_profile TEXT NOT NULL DEFAULT 'mixed-cascade',
    result_summary      TEXT,
    error               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tasks_tenant_state ON tasks (tenant_id, state);
CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks (session_id);

-- Operational metadata for a task, kept separate from retrieval evidence.
CREATE TABLE IF NOT EXISTS task_metadata (
    task_id     TEXT NOT NULL REFERENCES tasks (task_id) ON DELETE CASCADE,
    tenant_id   TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (task_id, key)
);

-- Append-only lifecycle events (audit trail).
CREATE TABLE IF NOT EXISTS task_events (
    event_id    TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL REFERENCES tasks (task_id) ON DELETE CASCADE,
    tenant_id   TEXT NOT NULL,
    state       TEXT NOT NULL,
    note        TEXT,
    payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events (task_id, created_at);

-- ---------------------------------------------------------------------------
-- Sessions (operational conversation state) — separate from evidence
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    session_id      TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    client_slug     TEXT NOT NULL,
    entrypoint      TEXT NOT NULL,
    requester_id    TEXT NOT NULL,
    active_task_id  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS session_summaries (
    summary_id  TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    session_id  TEXT NOT NULL REFERENCES sessions (session_id) ON DELETE CASCADE,
    tenant_id   TEXT NOT NULL,
    summary     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Memory and evidence — DELIBERATELY SEPARATE TABLES
-- ---------------------------------------------------------------------------
-- Reusable semantic memory / routines / learnings (summarized agent memory).
CREATE TABLE IF NOT EXISTS memory_chunks (
    memory_id   TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    tenant_id   TEXT NOT NULL,
    client_slug TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'note',
    content     TEXT NOT NULL,
    embedding   vector(768),
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_memory_tenant ON memory_chunks (tenant_id);

-- Retrieval documents (ingested source documents).
CREATE TABLE IF NOT EXISTS retrieval_document_chunks (
    evidence_id  TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    tenant_id    TEXT NOT NULL,
    client_slug  TEXT NOT NULL,
    source       TEXT NOT NULL,
    source_ref   TEXT,
    content      TEXT NOT NULL,
    embedding    vector(768),
    freshness_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    task_id      TEXT,
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_retrieval_tenant ON retrieval_document_chunks (tenant_id);

-- Tool-derived evidence (results captured from tool calls).
CREATE TABLE IF NOT EXISTS tool_evidence_chunks (
    evidence_id  TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    tenant_id    TEXT NOT NULL,
    client_slug  TEXT NOT NULL,
    source       TEXT NOT NULL,
    source_ref   TEXT,
    content      TEXT NOT NULL,
    embedding    vector(768),
    freshness_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    task_id      TEXT,
    tool_call_id TEXT,
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tool_evidence_tenant ON tool_evidence_chunks (tenant_id);

-- ---------------------------------------------------------------------------
-- Tool calls and approvals
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tool_calls (
    tool_call_id        TEXT PRIMARY KEY,
    task_id             TEXT NOT NULL REFERENCES tasks (task_id) ON DELETE CASCADE,
    tenant_id           TEXT NOT NULL,
    tool_name           TEXT NOT NULL,
    category            TEXT NOT NULL,
    approval_required   BOOLEAN NOT NULL DEFAULT false,
    status              TEXT NOT NULL DEFAULT 'requested',
    parameters          JSONB NOT NULL DEFAULT '{}'::jsonb,
    result              JSONB,
    requester_id        TEXT NOT NULL,
    model_route         TEXT,
    approval_record_id  TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tool_calls_task ON tool_calls (task_id);

CREATE TABLE IF NOT EXISTS approval_records (
    approval_record_id   TEXT PRIMARY KEY,
    approval_request_id  TEXT NOT NULL,
    task_id              TEXT NOT NULL REFERENCES tasks (task_id) ON DELETE CASCADE,
    tenant_id            TEXT NOT NULL,
    tool_call_id         TEXT,
    decision             TEXT NOT NULL DEFAULT 'pending',
    approver_id          TEXT,
    channel              TEXT,
    payload_hash         TEXT NOT NULL,
    decided_at           TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_approvals_task ON approval_records (task_id);

-- ---------------------------------------------------------------------------
-- Prompt-to-code artifacts (proposed patches, not applied until approved)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS proposed_patches (
    patch_id          TEXT PRIMARY KEY,
    task_id           TEXT NOT NULL REFERENCES tasks (task_id) ON DELETE CASCADE,
    tenant_id         TEXT NOT NULL,
    description       TEXT NOT NULL,
    diff              TEXT NOT NULL,
    artifact_paths    JSONB NOT NULL DEFAULT '[]'::jsonb,
    approval_required BOOLEAN NOT NULL DEFAULT true,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Governance: AI-BOM, budget, gateway correlation
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_bom_snapshots (
    snapshot_id   TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    client_slug   TEXT NOT NULL,
    version       TEXT NOT NULL,
    agents        JSONB NOT NULL DEFAULT '[]'::jsonb,
    tools         JSONB NOT NULL DEFAULT '[]'::jsonb,
    skills        JSONB NOT NULL DEFAULT '[]'::jsonb,
    prompts       JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_routes  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS budget_ledger (
    budget_event_id     TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    client_slug         TEXT NOT NULL,
    budget_owner        TEXT NOT NULL,
    task_id             TEXT,
    model               TEXT NOT NULL,
    prompt_tokens       INTEGER NOT NULL DEFAULT 0,
    completion_tokens   INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd  NUMERIC(12, 6) NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_budget_owner_month
    ON budget_ledger (tenant_id, budget_owner, created_at);

CREATE TABLE IF NOT EXISTS gateway_events (
    gateway_event_id   TEXT PRIMARY KEY,
    tenant_id          TEXT NOT NULL,
    client_slug        TEXT NOT NULL,
    task_id            TEXT,
    cf_aig_request_id  TEXT,
    litellm_request_id TEXT,
    provider           TEXT,
    model_route        TEXT,
    provider_status    INTEGER,
    dlp_action         TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_gateway_task ON gateway_events (task_id);
