import pytest

from agent_mesh.contracts.enums import (
    ApprovalDecision,
    Entrypoint,
    ProposalRiskLevel,
    ProposalStatus,
    ProposalType,
)
from agent_mesh.contracts.models import CONTRACT_MODELS, TaskRecord
from agent_mesh.services import self_improvement as si


def _task(repo) -> TaskRecord:
    task = TaskRecord(
        tenant_id="t",
        client_slug="c",
        entrypoint=Entrypoint.API,
        requester={"requester_id": "u1", "entrypoint": "api"},
        session_id="s1",
        prompt="summarize the kickoff notes",
    )
    return repo.create_task(task)


def test_reflection_hook_creates_inert_draft_proposal(repo):
    task = _task(repo)
    proposal = si.reflect_on_task(
        repo,
        task,
        proposal_type=ProposalType.RUNBOOK_DOC_PATCH,
        title="clarify rollback step",
        rationale="operators missed it",
        proposed_patch="--- runbook\n+++ runbook\n+clarified",
    )
    assert proposal.status == ProposalStatus.DRAFT
    assert proposal.task_id == task.task_id
    assert proposal.patch_hash  # bound at creation
    # Proposal is inert: it is stored but changes no active state.
    assert repo.get_proposal(proposal.proposal_id) is not None


def test_sensitive_types_are_floored_to_high_risk(repo):
    task = _task(repo)
    for ptype in (
        ProposalType.PROMPT_PATCH,
        ProposalType.TOOL_SCHEMA_PATCH,
        ProposalType.ROUTING_RULE_PATCH,
        ProposalType.BUDGET_POLICY_PATCH,
        ProposalType.SANDBOX_POLICY_PATCH,
    ):
        proposal = si.reflect_on_task(
            repo,
            task,
            proposal_type=ptype,
            title="x",
            rationale="y",
            proposed_patch="patch",
            requested_risk=ProposalRiskLevel.LOW,  # caller cannot lower it
        )
        assert proposal.risk_level == ProposalRiskLevel.HIGH.value, ptype


def test_high_and_critical_cannot_auto_promote():
    assert not si.can_auto_promote(ProposalRiskLevel.HIGH)
    assert not si.can_auto_promote(ProposalRiskLevel.CRITICAL)
    assert si.can_auto_promote(ProposalRiskLevel.LOW)
    # Every promotion requires approval regardless of risk.
    assert si.requires_approval(ProposalRiskLevel.LOW)
    assert si.requires_approval(ProposalRiskLevel.CRITICAL)


def test_promotion_blocked_before_evaluation_and_approval(repo):
    task = _task(repo)
    proposal = si.reflect_on_task(
        repo,
        task,
        proposal_type=ProposalType.PROMPT_PATCH,
        title="reword planner prompt",
        rationale="reduce hallucination",
        proposed_patch="new prompt text",
    )
    # No evaluation, no approval -> refused.
    with pytest.raises(si.PromotionRefused):
        si.promote_proposal(repo, proposal.proposal_id, promoted_version="v2")


def test_opening_approval_requires_passing_evaluation(repo):
    task = _task(repo)
    proposal = si.reflect_on_task(
        repo,
        task,
        proposal_type=ProposalType.PROMPT_PATCH,
        title="reword",
        rationale="x",
        proposed_patch="text",
    )
    # Cannot open an approval before the proposal has passed evaluation.
    with pytest.raises(si.PromotionRefused):
        si.open_promotion_approval(repo, proposal.proposal_id)


def test_promotion_blocked_with_eval_but_no_approval(repo):
    task = _task(repo)
    proposal = si.reflect_on_task(
        repo,
        task,
        proposal_type=ProposalType.EVAL_CASE,
        title="add regression case",
        rationale="cover the bug",
        proposed_patch="def test_x(): assert True",
    )
    result = si.evaluate_proposal(repo, proposal.proposal_id)
    assert result.passed
    # Eval passed but no approval -> still refused.
    with pytest.raises(si.PromotionRefused):
        si.promote_proposal(repo, proposal.proposal_id, promoted_version="v2")


def test_promotion_allowed_after_eval_pass_and_approval(repo):
    task = _task(repo)
    proposal = si.reflect_on_task(
        repo,
        task,
        proposal_type=ProposalType.EVAL_CASE,
        title="add regression case",
        rationale="cover the bug",
        proposed_patch="def test_x(): assert True",
    )
    si.evaluate_proposal(repo, proposal.proposal_id)
    si.open_promotion_approval(repo, proposal.proposal_id)
    si.record_approval_decision(
        repo, proposal.proposal_id, ApprovalDecision.APPROVED, "human:1", "slack"
    )
    promotion = si.promote_proposal(
        repo, proposal.proposal_id, promoted_version="v2", previous_version="v1"
    )
    assert promotion.promoted_version == "v2"
    assert promotion.previous_version == "v1"
    assert repo.get_proposal(proposal.proposal_id).status == ProposalStatus.PROMOTED.value


def test_high_risk_prompt_change_promotes_only_with_human_approval(repo):
    task = _task(repo)
    proposal = si.reflect_on_task(
        repo,
        task,
        proposal_type=ProposalType.PROMPT_PATCH,
        title="rewrite system prompt",
        rationale="improve tone",
        proposed_patch="brand new system prompt",
    )
    assert proposal.risk_level == ProposalRiskLevel.HIGH.value
    si.evaluate_proposal(repo, proposal.proposal_id)
    si.open_promotion_approval(repo, proposal.proposal_id)
    # Rejected -> cannot promote.
    si.record_approval_decision(
        repo, proposal.proposal_id, ApprovalDecision.REJECTED, "human:1", "slack"
    )
    with pytest.raises(si.PromotionRefused):
        si.promote_proposal(repo, proposal.proposal_id, promoted_version="v2")
    assert repo.get_proposal(proposal.proposal_id).status == ProposalStatus.REJECTED.value


def test_promotion_refused_if_artifact_mutated_after_approval(repo):
    """Payload-hash binding: editing the patch after approval invalidates it."""
    task = _task(repo)
    proposal = si.reflect_on_task(
        repo,
        task,
        proposal_type=ProposalType.RUNBOOK_DOC_PATCH,
        title="doc tweak",
        rationale="x",
        proposed_patch="original",
    )
    si.evaluate_proposal(repo, proposal.proposal_id)
    si.open_promotion_approval(repo, proposal.proposal_id)
    si.record_approval_decision(
        repo, proposal.proposal_id, ApprovalDecision.APPROVED, "human:1", "slack"
    )
    # Tamper with the artifact (keep stale patch_hash) after approval.
    tampered = repo.get_proposal(proposal.proposal_id).model_copy(
        update={"proposed_patch": "swapped-in malicious content"}
    )
    repo.upsert_proposal(tampered)
    with pytest.raises(si.PromotionRefused):
        si.promote_proposal(repo, proposal.proposal_id, promoted_version="v2")


def test_promote_refused_for_rolled_back_proposal(repo):
    """CR-01: a rolled-back proposal cannot be re-promoted without fresh approval.

    The passing evaluation and APPROVED approval record both survive a rollback, so
    without a status guard ``promote_proposal`` would silently re-advance the active
    version — bypassing the single human-gated chokepoint. The status guard refuses
    it because the proposal is now ROLLED_BACK, not APPROVED.
    """
    task = _task(repo)
    proposal = si.reflect_on_task(
        repo,
        task,
        proposal_type=ProposalType.RUNBOOK_DOC_PATCH,
        title="doc tweak",
        rationale="x",
        proposed_patch="content",
    )
    si.evaluate_proposal(repo, proposal.proposal_id)
    si.open_promotion_approval(repo, proposal.proposal_id)
    si.record_approval_decision(
        repo, proposal.proposal_id, ApprovalDecision.APPROVED, "human:1", "slack"
    )
    promotion = si.promote_proposal(
        repo, proposal.proposal_id, promoted_version="v2", previous_version="v1"
    )
    si.rollback_promotion(repo, promotion.promotion_id, reason="regression")
    assert (
        repo.get_proposal(proposal.proposal_id).status
        == ProposalStatus.ROLLED_BACK.value
    )
    # Re-promotion with NO fresh approval must be refused.
    with pytest.raises(si.PromotionRefused):
        si.promote_proposal(repo, proposal.proposal_id, promoted_version="v3")


def test_pending_evaluation_does_not_pass(repo):
    task = _task(repo)
    proposal = si.reflect_on_task(
        repo,
        task,
        proposal_type=ProposalType.EVAL_CASE,
        title="needs real harness",
        rationale="x",
        proposed_patch="case",
    )
    result = si.evaluate_proposal(repo, proposal.proposal_id, can_run=False)
    assert result.pending
    assert not result.passed
    assert (
        repo.get_proposal(proposal.proposal_id).status
        == ProposalStatus.PENDING_EVALUATION.value
    )


def test_rollback_marks_promotion_and_proposal(repo):
    task = _task(repo)
    proposal = si.reflect_on_task(
        repo,
        task,
        proposal_type=ProposalType.RUNBOOK_DOC_PATCH,
        title="doc tweak",
        rationale="x",
        proposed_patch="content",
    )
    si.evaluate_proposal(repo, proposal.proposal_id)
    si.open_promotion_approval(repo, proposal.proposal_id)
    si.record_approval_decision(
        repo, proposal.proposal_id, ApprovalDecision.APPROVED, "human:1", "slack"
    )
    promotion = si.promote_proposal(
        repo, proposal.proposal_id, promoted_version="v2", previous_version="v1"
    )
    rolled = si.rollback_promotion(repo, promotion.promotion_id, reason="regression")
    assert rolled.rolled_back
    assert rolled.rollback_reason == "regression"
    assert (
        repo.get_proposal(proposal.proposal_id).status
        == ProposalStatus.ROLLED_BACK.value
    )


def test_self_improvement_models_registered_for_schema_export():
    for name in ("SelfImprovementProposal", "EvaluationResult", "PromotionRecord"):
        assert name in CONTRACT_MODELS, name
        schema = CONTRACT_MODELS[name].model_json_schema()
        assert schema["type"] == "object"
        assert "properties" in schema
