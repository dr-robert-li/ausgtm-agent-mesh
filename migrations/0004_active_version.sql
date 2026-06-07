-- Agent Mesh POC — self-improvement active-version pointer + AI-BOM snapshots.
-- Region: australia-southeast1 (durable store stays in Australia).
--
-- Two tables land here (the migration ordinal 0004 is load-bearing, not the
-- filename). Both follow the 0001/0002 conventions:
--   * Tenant partitioning via tenant_id.
--   * Append-only governance records for the 12-month retention profile.
--   * Idempotent: IF NOT EXISTS so it can be re-applied.
--
-- Plain DDL only: no dollar-quoted bodies, no double-dash inside string
-- literals (the test migration applier strips comments by cutting at the first
-- double-dash on each line, then splits statements on the semicolon).

-- ---------------------------------------------------------------------------
-- Active-version pointer (SI-02b). One row per tenant naming the currently
-- active version. The non-hot boot loader reads it at start/deploy; promote and
-- rollback re-point it. It NEVER mutates active instructions at runtime — the
-- pointer is only re-pointed through the approval-gated promote/rollback path.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS self_improvement_active_version (
    tenant_id       TEXT PRIMARY KEY,
    active_version  TEXT NOT NULL,
    promotion_id    TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- AI-BOM snapshots (SI-02 persistence target; written/read back by 06-05).
-- Mirrors the AIBOMSnapshot contract model: rich fields are stored as JSONB
-- (agents/tools/skills/prompts as JSONB lists, model_routes as a JSONB dict).
-- Not a normalized schema by design — one snapshot row is the approved
-- capability bundle for a deployment at a point in time.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_bom_snapshots (
    snapshot_id     TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    client_slug     TEXT NOT NULL,
    version         TEXT NOT NULL,
    agents          JSONB NOT NULL DEFAULT '[]',
    tools           JSONB NOT NULL DEFAULT '[]',
    skills          JSONB NOT NULL DEFAULT '[]',
    prompts         JSONB NOT NULL DEFAULT '[]',
    model_routes    JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ai_bom_snapshots_tenant
    ON ai_bom_snapshots (tenant_id);
