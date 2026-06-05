# Self-Improvement Loop (Option C)

> **POC safety warning — read first.** This POC performs **no runtime autonomous
> self-modification of active instructions.** Agents never silently mutate a live
> system prompt, tool permission, routing rule, schema, or write policy. Every
> self-improvement is an **inert proposal** that must be stored, evaluated,
> approved by a human, promoted, and versioned before it can affect anything —
> and even then, wiring a promoted artifact into the running system is a
> deliberate, separate, human-owned step that the POC does not automate.

This document records the design decision for how the agent mesh improves itself
over time, why **Option C** was selected, how it maps onto AG2, and the safety
boundaries, approval-gated promotion, rollback, and AI-BOM implications.

It is the normative reference for the scaffolded implementation in
`src/agent_mesh/services/self_improvement.py`, the contract models in
`src/agent_mesh/contracts/`, and the migration in
`migrations/0002_self_improvement.sql`.

## 1. The options considered

| Option | Description | Verdict |
| :--- | :--- | :--- |
| **A — No self-improvement** | Agents never propose changes to themselves. Improvements are entirely manual, made by engineers editing prompts/tools/routes. | Safe but slow; discards the signal agents have about their own failures. Rejected as the long-term posture. |
| **B — Suggestion-only (out-of-band)** | Agents log free-text suggestions to a channel/doc for humans to read. No structured artifact, no pipeline, no versioning. | Low risk, low value. Suggestions rot, are unstructured, and are not auditable or traceable to a deployment version. Rejected. |
| **C — Self-improving agents with approval-gated patches** *(selected)* | At the end of a workflow, a reflection/governance agent emits **structured, inert proposal artifacts**. Each proposal is evaluated, then requires **human approval** before being **promoted** to a **versioned** capability reflected in the AI-BOM. High/critical changes can never auto-promote. | Captures the agent's self-knowledge as governed, auditable, reversible change. **Selected.** |
| **D — Fully autonomous self-modification** | Agents rewrite their own prompts/tools/routing at runtime without human approval. | Unbounded blast radius: a bad self-edit can silently degrade or escalate the whole fleet, defeat the approval model, and break auditability. **Explicitly rejected** for this architecture. |

## 2. Why Option C

Option C is the only choice consistent with the rest of this architecture, which
already insists that:

- **Write actions require approval** (Tool Gateway approval ledger). A change to a
  prompt, tool schema, routing rule, or write policy *is itself a write* against
  the running system, so it belongs under the same gate.
- **Prompt-to-code produces proposed patches, not applied changes.** Self-
  improvement is the same shape: propose an artifact, gate its application.
- **The AI-BOM is the source of truth** for the approved capability bundle.
  Every promoted improvement must be versioned and reflected there.
- **Nothing is production-ready by default.** Autonomous self-modification (Option
  D) cannot be made safe within a POC, so it is excluded by construction.

Option C lets the mesh learn from its own run telemetry without ever ceding the
control plane: humans stay in the loop on anything that changes behaviour, and
every change is evaluated, versioned, and reversible.

## 3. AG2 compatibility

**Option C is compatible with AG2 and maps cleanly onto AG2's primitives.** It is
implemented as a *workflow pattern* on top of AG2 rather than requiring any AG2
internals to change.

AG2 provides the building blocks Option C needs:

- **Group chat / tool functions / context variables and target handoffs** — a
  dedicated **reflection / governance agent** participates in the group chat and,
  at the end of a run, emits a structured proposal via a tool function, then
  **hands off** to the evaluation/approval/promotion components.
- **Human-in-the-loop hooks** (AG2 Beta) — the approval gate is exactly an HITL
  pause: the proposal sits in `awaiting_approval` until a human decides, mirroring
  how the mesh already pauses write actions.
- **Structured output** — proposals are emitted as structured artifacts
  (`SelfImprovementProposal`), not free text, so they are machine-checkable and
  auditable.
- **OpenTelemetry tracing** — reflection, evaluation, approval, and promotion are
  spans, joinable with the originating task/session/agent for audit.
- **Persistent backends for history/streams + knowledge store / persistent
  memory + state externalization** — proposals, evaluations, and promotions are
  externalized to Postgres (`migrations/0002_self_improvement.sql`), so the loop
  survives restarts and is durable for the 12-month retention profile.
- **Middleware for retries / token limits / history management** — evaluation and
  promotion are ordinary steps that inherit the same middleware budget/retry
  controls as the rest of the mesh.

Mapping summary:

```
AG2 group chat run
  └─ reflection/governance agent (AG2 agent + tool function)
        emits → SelfImprovementProposal   (structured output; inert artifact)
        hand off →
            evaluate_proposal()            (deterministic checks / eval harness)
            open_promotion_approval()      (AG2 HITL hook → shared approval ledger)
            promote_proposal()             (versioned, AI-BOM-traceable, rollback-able)
```

Because the proposal is just structured output handed off to governance
components, **no AG2 feature is bypassed or overridden** — the loop is additive.

## 4. The pipeline and its states

`ProposalStatus` lifecycle (see `src/agent_mesh/contracts/enums.py`):

```
DRAFT
  → PENDING_EVALUATION            (eval harness unavailable; cannot pass yet)
  → EVALUATION_PASSED | EVALUATION_FAILED
  → AWAITING_APPROVAL
  → APPROVED | REJECTED
  → PROMOTED
  → ROLLED_BACK                   (post-promotion reversal)
```

Functions in `src/agent_mesh/services/self_improvement.py`:

| Step | Function | Guarantee |
| :--- | :--- | :--- |
| Reflect | `reflect_on_task(...)` | Creates an **inert** `DRAFT` proposal from task telemetry. Binds a `patch_hash` of the exact artifact. Changes no active state. |
| Evaluate | `evaluate_proposal(...)` | Runs deterministic checks, or marks `pending` when a real harness is unavailable. A proposal cannot pass while pending. |
| Approve | `open_promotion_approval(...)` + `record_approval_decision(...)` | Opens a pending approval in the **shared approval ledger** and records the human decision. |
| Promote | `promote_proposal(...)` | **Refuses** unless there is a passing evaluation **and** an `APPROVED` approval whose hash still matches the artifact. Produces a versioned `PromotionRecord`. |
| Roll back | `rollback_promotion(...)` | Marks the promotion rolled back and returns the proposal to `ROLLED_BACK`; `previous_version` is the restore target. |

## 5. Proposal types and risk

`ProposalType` covers the change surfaces a reflection agent might target:

`prompt_patch`, `tool_schema_patch`, `routing_rule_patch`, `eval_case`,
`runbook_doc_patch`, `budget_policy_patch`, `field_mapping_patch`,
`sandbox_policy_patch`.

`ProposalRiskLevel` is `low` / `medium` / `high` / `critical`. **Every** promotion
requires approval. The **sensitive types** — `prompt_patch`, `tool_schema_patch`,
`routing_rule_patch`, `budget_policy_patch`, `sandbox_policy_patch` — are
**floored to `high`** by `classify_risk(...)`, so a caller cannot request a lower
level for a change that touches active instructions, permissions, routing, budget,
or sandbox policy. **`high` and `critical` can never auto-promote**
(`NON_AUTO_PROMOTE_RISK`): they always require an explicit human approval,
regardless of how the evaluation went.

## 6. Safety boundaries (enforced in code)

1. **No runtime autonomous self-modification.** Creating a proposal mutates nothing
   live. Only `promote_proposal` records a versioned change, and even that does not
   hot-swap the running config in the POC.
2. **Promotion is the single chokepoint.** It is refused without (a) a passing,
   non-pending evaluation and (b) an `APPROVED` approval record.
3. **Approval is bound to the exact artifact.** `promote_proposal` re-checks the
   approval against the current `proposed_patch` via the same payload-hash binding
   used for tool-call approvals. Editing the patch after approval invalidates it
   (tested in `tests/test_self_improvement.py`).
4. **High/critical require a human.** No code path auto-promotes them.
5. **Inert artifacts only.** Proposals carry a diff / new content / config
   fragment as text; nothing executes on creation.

## 7. Rollback

Every `PromotionRecord` stores `previous_version` and supports
`rolled_back` / `rollback_reason`. `rollback_promotion(...)` flips the promotion to
rolled-back and returns the proposal to `ROLLED_BACK`. Restoring the previous
version of the underlying capability (prompt, route, schema) is the human-owned
step the `previous_version` pointer enables. A future production build would tie
this to the AI-BOM snapshot that preceded the promotion.

## 8. AI-BOM implications

A promoted proposal is a change to the **approved capability bundle**, so it must
appear in the AI-BOM:

- `PromotionRecord.promoted_version` / `previous_version` version the capability.
- `PromotionRecord.ai_bom_snapshot_id` links a promotion to the AI-BOM snapshot
  that reflects it, so the AI-BOM always answers "what is approved and live, and
  which self-improvement promoted it?"
- Proposals, evaluations, and promotions are durable (`0002_self_improvement.sql`)
  for the 12-month retention profile, giving a full audit trail from task
  telemetry → proposal → evaluation → approval → promotion → (rollback).

## 9. What is NOT in this POC

- No hot reload of prompts/tools/routes from a promoted artifact at runtime.
- No real eval harness — `evaluate_proposal` runs simple deterministic checks or
  marks `pending`. Production needs a real evaluation/eval-set harness.
- No automatic AI-BOM snapshot generation on promotion (the link field exists; the
  generator is future work, tracked alongside the existing AI-BOM roadmap item).
- No live AG2 reflection agent — the orchestration stub does not yet emit
  proposals automatically; `reflect_on_task` is the seam a real AG2 reflection
  agent calls. See [production-readiness-caveats.md](./production-readiness-caveats.md).
