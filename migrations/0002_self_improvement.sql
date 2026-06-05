-- Agent Mesh POC — self-improvement loop schema (Option C).
-- Region: australia-southeast1 (durable store stays in Australia).
--
-- Option C: self-improving agents with approval-gated patches. A reflection /
-- governance agent may emit self-improvement *proposals* at the end of a
-- workflow. Proposals are inert artifacts: they never mutate active system
-- prompts, tool permissions, routing rules, schemas, or write policies on their
-- own. A proposal only takes effect through the evaluate -> approve -> promote
-- pipeline, which versions it and reflects it in the AI-BOM/audit records.
--
-- These tables mirror the contract models in
-- src/agent_mesh/contracts/models.py (SelfImprovementProposal, EvaluationResult,
-- PromotionRecord) and follow the same conventions as 0001_init.sql:
--   * Tenant partitioning via tenant_id / client_slug.
--   * Append-only governance records for the 12-month retention profile.
--   * Idempotent: IF NOT EXISTS so it can be re-applied.

-- ---------------------------------------------------------------------------
-- Self-improvement proposals (emitted by reflection/governance agents)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS self_improvement_proposals (
    proposal_id         TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    client_slug         TEXT NOT NULL,
    task_id             TEXT,
    session_id          TEXT,
    agent_id            TEXT,
    proposal_type       TEXT NOT NULL,
    risk_level          TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'draft',
    title               TEXT NOT NULL,
    rationale           TEXT NOT NULL,
    proposed_patch      TEXT NOT NULL,
    target_ref          TEXT,
    evidence_pointers   JSONB NOT NULL DEFAULT '[]'::jsonb,
    patch_hash          TEXT,
    approval_record_id  TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_si_proposals_tenant_status
    ON self_improvement_proposals (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_si_proposals_task
    ON self_improvement_proposals (task_id);

-- ---------------------------------------------------------------------------
-- Evaluations (deterministic checks / eval harness output per proposal)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS self_improvement_evaluations (
    evaluation_id   TEXT PRIMARY KEY,
    proposal_id     TEXT NOT NULL REFERENCES self_improvement_proposals (proposal_id)
                        ON DELETE CASCADE,
    tenant_id       TEXT NOT NULL,
    passed          BOOLEAN NOT NULL DEFAULT false,
    pending         BOOLEAN NOT NULL DEFAULT false,
    checks          JSONB NOT NULL DEFAULT '[]'::jsonb,
    evaluator       TEXT NOT NULL DEFAULT 'deterministic-stub',
    summary         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_si_evaluations_proposal
    ON self_improvement_evaluations (proposal_id, created_at);

-- ---------------------------------------------------------------------------
-- Promotions (the only path by which a proposal becomes an active version)
-- ---------------------------------------------------------------------------
-- A promotion requires a passing evaluation AND an APPROVED approval record.
-- previous_version + rolled_back/rollback_reason make the change reversible and
-- AI-BOM-traceable.
CREATE TABLE IF NOT EXISTS self_improvement_promotions (
    promotion_id        TEXT PRIMARY KEY,
    proposal_id         TEXT NOT NULL REFERENCES self_improvement_proposals (proposal_id)
                            ON DELETE CASCADE,
    tenant_id           TEXT NOT NULL,
    client_slug         TEXT NOT NULL,
    approval_record_id  TEXT NOT NULL,
    evaluation_id       TEXT NOT NULL,
    promoted_version    TEXT NOT NULL,
    previous_version    TEXT,
    patch_hash          TEXT NOT NULL,
    ai_bom_snapshot_id  TEXT,
    rolled_back         BOOLEAN NOT NULL DEFAULT false,
    rollback_reason     TEXT,
    promoted_by         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_si_promotions_proposal
    ON self_improvement_promotions (proposal_id);
