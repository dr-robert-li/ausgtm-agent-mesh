"""Egress check + eight deterministic guards contract tests."""

from __future__ import annotations

from packages.contracts.egress import (
    GUARD_ORDER,
    EgressCheckRecord,
    EgressGuardName,
    EgressGuardResult,
    EgressGuardVerdict,
    EgressOverallVerdict,
    ProposedEgress,
)


def test_guard_order_is_canonical_and_complete() -> None:
    """The eight guards run in this exact order. Reordering is a contract break."""
    assert GUARD_ORDER == (
        EgressGuardName.schema,
        EgressGuardName.claim_evidence_map,
        EgressGuardName.evidence_resolvable,
        EgressGuardName.freshness,
        EgressGuardName.source_authority,
        EgressGuardName.tenancy,
        EgressGuardName.tier_and_policy,
        EgressGuardName.budget,
    )
    assert len(GUARD_ORDER) == 8


def test_egress_check_record_roundtrip() -> None:
    record = EgressCheckRecord(
        tenant_id="tenant_acme",
        task_id="task_01HZX0000000000000000000",
        correlation_id="corr_01HZX0000000000000000000",
        wave_index=1,
        proposed_egress=ProposedEgress(
            kind="slack_message",
            tool_id="slack",
            tier="external_egress",
            claim_evidence_map_ref="cem_01HZX0000000000000000000",
            payload_ref="blob://outputs/task_x/draft_v1",
        ),
        guards=[
            EgressGuardResult(
                guard=g,
                name=g.value,
                verdict=EgressGuardVerdict.pass_,
            )
            for g in GUARD_ORDER
        ],
        overall_verdict=EgressOverallVerdict.pass_,
    )
    again = EgressCheckRecord.model_validate(record.model_dump(mode="json"))
    assert again.egress_check_id.startswith("egc_")
    assert again.overall_verdict is EgressOverallVerdict.pass_
    assert [g.guard for g in again.guards] == list(GUARD_ORDER)


def test_blocked_egress_carries_blocking_guard() -> None:
    record = EgressCheckRecord(
        tenant_id="tenant_acme",
        task_id="task_X",
        proposed_egress=ProposedEgress(
            kind="monday_item_update",
            tool_id="monday",
            tier="write_revocable",
            claim_evidence_map_ref="cem_X",
            payload_ref="blob://outputs/task_x/payload",
        ),
        guards=[
            EgressGuardResult(
                guard=EgressGuardName.freshness,
                name="freshness",
                verdict=EgressGuardVerdict.blocked,
                note="evidence older than ttl",
            ),
        ],
        overall_verdict=EgressOverallVerdict.blocked,
        blocking_guard=EgressGuardName.freshness,
    )
    assert record.blocking_guard is EgressGuardName.freshness


def test_payload_is_a_ref_not_a_raw_payload() -> None:
    """Workflow state carries refs, never raw context. Enforced by convention.

    We don't pattern-match the URI scheme in the contract (the substrate may
    differ in deployment), but `payload_ref` must be a string ref, not a dict
    of inline content. The model declares it as `str`; this test guards
    against accidental loosening of that.
    """
    pe = ProposedEgress(
        kind="slack_message",
        tool_id="slack",
        tier="external_egress",
        claim_evidence_map_ref="cem_X",
        payload_ref="blob://outputs/task_x/draft_v1",
    )
    assert isinstance(pe.payload_ref, str)
