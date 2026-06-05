"""Self-improvement loop (Option C: approval-gated, self-improving agents).

A reflection / governance agent may emit self-improvement *proposals* at the end
of a workflow. This module is the seam that turns those proposals into a governed
pipeline:

    reflect  -> create an inert SelfImprovementProposal from task telemetry
    evaluate -> run deterministic checks (or mark pending_evaluation)
    approve  -> a human approval decision (reuses the shared approval ledger)
    promote  -> the ONLY path that makes a proposal an active, versioned capability

Hard safety boundaries enforced here (POC):

* A proposal NEVER mutates an active system prompt, tool permission, routing
  rule, schema, or write policy by being created. It is an artifact only.
* Promotion is refused unless the proposal passed evaluation AND has an APPROVED
  approval record whose payload hash still matches the exact artifact.
* HIGH and CRITICAL risk proposals can never auto-promote — they always require
  an explicit human approval, regardless of evaluation outcome.
* There is no runtime application of the promoted artifact in the POC. Promotion
  records a versioned, AI-BOM-traceable, rollback-able entry; wiring the promoted
  config into the live system is a deliberate, separate, human-owned step.
"""

from __future__ import annotations

from datetime import UTC, datetime

from agent_mesh.contracts.enums import (
    NON_AUTO_PROMOTE_RISK,
    ApprovalDecision,
    ProposalRiskLevel,
    ProposalStatus,
    ProposalType,
)
from agent_mesh.contracts.models import (
    ApprovalRecord,
    ApprovalRequest,
    EvaluationResult,
    PromotionRecord,
    SelfImprovementProposal,
    TaskRecord,
)
from agent_mesh.services import approvals
from agent_mesh.services.repository import Repository

# Proposal types that touch active instructions, permissions, routing, schemas,
# or write policy. These are inherently at least HIGH risk: they always require
# explicit human approval and can never auto-promote.
SENSITIVE_TYPES = frozenset(
    {
        ProposalType.PROMPT_PATCH,
        ProposalType.TOOL_SCHEMA_PATCH,
        ProposalType.ROUTING_RULE_PATCH,
        ProposalType.BUDGET_POLICY_PATCH,
        ProposalType.SANDBOX_POLICY_PATCH,
    }
)


class PromotionRefused(RuntimeError):
    """Raised when a promotion is attempted without a passing evaluation and an
    approved approval record, or for a non-auto-promotable risk level."""


def _coerce_risk(value: ProposalRiskLevel | str) -> ProposalRiskLevel:
    return value if isinstance(value, ProposalRiskLevel) else ProposalRiskLevel(value)


def _coerce_type(value: ProposalType | str) -> ProposalType:
    return value if isinstance(value, ProposalType) else ProposalType(value)


def classify_risk(
    proposal_type: ProposalType | str,
    requested: ProposalRiskLevel | str | None = None,
) -> ProposalRiskLevel:
    """Resolve the effective risk level for a proposal.

    Sensitive types (prompt, tool schema, routing, budget, sandbox policy) are
    floored at HIGH so they can never auto-promote, even if a caller requested a
    lower level. Non-sensitive types default to LOW unless a higher level is
    explicitly requested."""
    ptype = _coerce_type(proposal_type)
    floor = ProposalRiskLevel.HIGH if ptype in SENSITIVE_TYPES else ProposalRiskLevel.LOW
    if requested is None:
        return floor
    requested = _coerce_risk(requested)
    order = [
        ProposalRiskLevel.LOW,
        ProposalRiskLevel.MEDIUM,
        ProposalRiskLevel.HIGH,
        ProposalRiskLevel.CRITICAL,
    ]
    return requested if order.index(requested) >= order.index(floor) else floor


def requires_approval(risk_level: ProposalRiskLevel | str) -> bool:
    """Every promotion requires an approval in the POC. This is always True and
    exists as an explicit, testable statement of the policy."""
    _coerce_risk(risk_level)
    return True


def can_auto_promote(risk_level: ProposalRiskLevel | str) -> bool:
    """HIGH and CRITICAL proposals can never auto-promote."""
    return _coerce_risk(risk_level) not in NON_AUTO_PROMOTE_RISK


def reflect_on_task(
    repo: Repository,
    task: TaskRecord,
    *,
    proposal_type: ProposalType | str,
    title: str,
    rationale: str,
    proposed_patch: str,
    target_ref: str | None = None,
    agent_id: str = "reflection-agent",
    requested_risk: ProposalRiskLevel | str | None = None,
    evidence_pointers: list[str] | None = None,
) -> SelfImprovementProposal:
    """End-of-workflow reflection hook.

    Creates and persists an inert proposal derived from a completed task. The
    proposal is DRAFT and binds no behaviour: it cannot change the running system
    until it is evaluated, approved, and promoted."""
    ptype = _coerce_type(proposal_type)
    risk = classify_risk(ptype, requested_risk)
    proposal = SelfImprovementProposal(
        tenant_id=task.tenant_id,
        client_slug=task.client_slug,
        task_id=task.task_id,
        session_id=task.session_id,
        agent_id=agent_id,
        proposal_type=ptype,
        risk_level=risk,
        status=ProposalStatus.DRAFT,
        title=title,
        rationale=rationale,
        proposed_patch=proposed_patch,
        target_ref=target_ref,
        evidence_pointers=evidence_pointers or [],
        patch_hash=approvals.payload_hash({"proposed_patch": proposed_patch}),
    )
    return repo.upsert_proposal(proposal)


def evaluate_proposal(
    repo: Repository,
    proposal_id: str,
    *,
    deterministic_checks: list[dict] | None = None,
    can_run: bool = True,
) -> EvaluationResult:
    """Evaluate a proposal.

    Runs the supplied deterministic checks. When ``can_run`` is False (a real
    eval harness is needed but unavailable), the result is marked ``pending`` and
    the proposal moves to PENDING_EVALUATION rather than passing."""
    proposal = repo.get_proposal(proposal_id)
    if proposal is None:
        raise KeyError(f"unknown proposal {proposal_id}")

    if not can_run:
        result = EvaluationResult(
            proposal_id=proposal_id,
            tenant_id=proposal.tenant_id,
            passed=False,
            pending=True,
            checks=[],
            summary="evaluation harness unavailable; marked pending",
        )
        repo.upsert_evaluation(result)
        _set_status(repo, proposal, ProposalStatus.PENDING_EVALUATION)
        return result

    checks = deterministic_checks or [{"name": "non_empty_patch", "passed": True}]
    passed = bool(proposal.proposed_patch.strip()) and all(c.get("passed") for c in checks)
    result = EvaluationResult(
        proposal_id=proposal_id,
        tenant_id=proposal.tenant_id,
        passed=passed,
        pending=False,
        checks=checks,
        summary="passed" if passed else "failed deterministic checks",
    )
    repo.upsert_evaluation(result)
    _set_status(
        repo,
        proposal,
        ProposalStatus.EVALUATION_PASSED if passed else ProposalStatus.EVALUATION_FAILED,
    )
    return result


def open_promotion_approval(
    repo: Repository, proposal_id: str
) -> ApprovalRecord:
    """Open a pending approval for a proposal that passed evaluation.

    The approval is bound to the exact artifact via the proposal's patch hash, so
    an approval cannot be replayed against a mutated patch."""
    proposal = repo.get_proposal(proposal_id)
    if proposal is None:
        raise KeyError(f"unknown proposal {proposal_id}")
    if proposal.status != ProposalStatus.EVALUATION_PASSED.value:
        raise PromotionRefused(
            f"proposal {proposal_id} is {proposal.status}; must be evaluation_passed"
        )
    request = ApprovalRequest(
        task_id=proposal.task_id or proposal.proposal_id,
        tenant_id=proposal.tenant_id,
        requester_id=proposal.agent_id or "reflection-agent",
        summary=f"Promote self-improvement [{proposal.risk_level}] {proposal.title}",
        payload_hash=proposal.patch_hash or "",
        evidence_pointers=proposal.evidence_pointers,
    )
    record = approvals.open_approval(repo, request)
    updated = proposal.model_copy(
        update={
            "status": ProposalStatus.AWAITING_APPROVAL.value,
            "approval_record_id": record.approval_record_id,
            "updated_at": datetime.now(UTC),
        }
    )
    repo.upsert_proposal(updated)
    return record


def promote_proposal(
    repo: Repository,
    proposal_id: str,
    *,
    promoted_version: str,
    previous_version: str | None = None,
    ai_bom_snapshot_id: str | None = None,
    promoted_by: str | None = None,
) -> PromotionRecord:
    """Promote a proposal — the ONLY path by which it becomes an active version.

    Refused unless:
      * an evaluation for the proposal passed, and
      * an APPROVED approval record exists whose payload hash still matches the
        proposal's patch hash.
    HIGH/CRITICAL never auto-promote: they still require the same APPROVED
    record, which only a human can supply. No runtime mutation happens here; the
    promotion is a versioned, rollback-able, AI-BOM-traceable record."""
    proposal = repo.get_proposal(proposal_id)
    if proposal is None:
        raise KeyError(f"unknown proposal {proposal_id}")

    evaluations = repo.list_evaluations(proposal_id, proposal.tenant_id)
    passing = next((e for e in evaluations if e.passed and not e.pending), None)
    if passing is None:
        raise PromotionRefused(
            f"proposal {proposal_id} has no passing evaluation; promotion refused"
        )

    if proposal.approval_record_id is None:
        raise PromotionRefused(
            f"proposal {proposal_id} has no approval record; promotion refused"
        )
    record = repo.get_approval(proposal.approval_record_id)
    if record is None:
        raise PromotionRefused(f"approval record for {proposal_id} not found")

    # Bind the approval to the exact artifact (payload-hash check), mirroring the
    # tool-call approval gate.
    if not approvals.is_approved(record, {"proposed_patch": proposal.proposed_patch}):
        raise PromotionRefused(
            f"proposal {proposal_id} is not approved for its current artifact; "
            "promotion refused"
        )

    promotion = PromotionRecord(
        proposal_id=proposal_id,
        tenant_id=proposal.tenant_id,
        client_slug=proposal.client_slug,
        approval_record_id=record.approval_record_id,
        evaluation_id=passing.evaluation_id,
        promoted_version=promoted_version,
        previous_version=previous_version,
        patch_hash=proposal.patch_hash or "",
        ai_bom_snapshot_id=ai_bom_snapshot_id,
        promoted_by=promoted_by,
    )
    repo.upsert_promotion(promotion)
    _set_status(repo, proposal, ProposalStatus.PROMOTED)
    return promotion


def rollback_promotion(
    repo: Repository, promotion_id: str, *, reason: str
) -> PromotionRecord:
    """Mark a promotion rolled back and return the proposal to ROLLED_BACK.

    Reversibility is a first-class part of Option C: the previous_version pointer
    on the promotion is the target to restore."""
    promotion = repo.get_promotion(promotion_id)
    if promotion is None:
        raise KeyError(f"unknown promotion {promotion_id}")
    updated = promotion.model_copy(
        update={"rolled_back": True, "rollback_reason": reason}
    )
    repo.upsert_promotion(updated)
    proposal = repo.get_proposal(promotion.proposal_id)
    if proposal is not None:
        _set_status(repo, proposal, ProposalStatus.ROLLED_BACK)
    return updated


def _set_status(
    repo: Repository, proposal: SelfImprovementProposal, status: ProposalStatus
) -> SelfImprovementProposal:
    updated = proposal.model_copy(
        update={"status": status.value, "updated_at": datetime.now(UTC)}
    )
    return repo.upsert_proposal(updated)


def record_approval_decision(
    repo: Repository,
    proposal_id: str,
    decision: ApprovalDecision,
    approver_id: str,
    channel: str,
) -> ApprovalRecord:
    """Record a human decision on a promotion approval and reflect it on the
    proposal status (APPROVED or REJECTED)."""
    proposal = repo.get_proposal(proposal_id)
    if proposal is None:
        raise KeyError(f"unknown proposal {proposal_id}")
    if proposal.approval_record_id is None:
        raise PromotionRefused(f"proposal {proposal_id} has no open approval")
    record = approvals.record_decision(
        repo, proposal.approval_record_id, decision, approver_id, channel
    )
    if decision == ApprovalDecision.APPROVED:
        _set_status(repo, proposal, ProposalStatus.APPROVED)
    elif decision == ApprovalDecision.REJECTED:
        _set_status(repo, proposal, ProposalStatus.REJECTED)
    return record
