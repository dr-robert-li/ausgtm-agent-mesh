"""Knowledge Layer + claim/evidence sidecar contract tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from packages.contracts.knowledge_layer import (
    SCHEMA_VERSION,
    Claim,
    ClaimEvidenceMap,
    Evidence,
    EvidenceKind,
    EvidencePointer,
    Freshness,
    FreshnessVerdict,
    KnowledgeLayerEntry,
)
from pydantic import ValidationError


def _kl_entry() -> KnowledgeLayerEntry:
    return KnowledgeLayerEntry(
        entry_id="kl:tenant_acme:monday/items/1234567890#v17",
        tenant_id="tenant_acme",
        source_system="monday",
        source_id="items/1234567890",
        content_hash="sha256:deadbeef",
        claim="Q3 pipeline coverage is 2.3x",
        evidence_pointer=EvidencePointer(
            kind=EvidenceKind.system_of_record,
            tool_id="monday",
            lookup_key="items/1234567890",
            url="https://acme.monday.com/items/1234567890",
        ),
        fetched_at=datetime.now(UTC),
        freshness=Freshness(
            verdict=FreshnessVerdict.fresh,
            freshness_ttl_seconds=3600,
        ),
        is_authoritative_for=["pipeline_coverage_q3"],
        version=17,
    )


def test_knowledge_layer_entry_roundtrip() -> None:
    e = _kl_entry()
    again = KnowledgeLayerEntry.model_validate(e.model_dump(mode="json"))
    assert again.entry_id == e.entry_id
    assert again.schema_version == SCHEMA_VERSION
    assert again.evidence_pointer.tool_id == "monday"


def test_kl_entry_id_format_is_reference_arch_shape() -> None:
    """Entry IDs follow `kl:{tenant}:{source}/{path}#v{n}`.

    We do not enforce this with a regex in the contract (would over-fit),
    but the sample shape must round-trip and stay parseable.
    """
    e = _kl_entry()
    assert e.entry_id.startswith("kl:")
    assert "#v" in e.entry_id


def test_claim_evidence_map_roundtrip() -> None:
    e = _kl_entry()
    cem = ClaimEvidenceMap(
        claim_evidence_map_ref="cem_01HZX0000000000000000000",
        tenant_id="tenant_acme",
        task_id="task_01HZX0000000000000000000",
        correlation_id="corr_01HZX0000000000000000000",
        claims=[
            Claim(
                claim_id="c1",
                subject="acme",
                predicate="pipeline_coverage_q3",
                value=2.3,
                evidence=[
                    Evidence(
                        kind=EvidenceKind.knowledge_layer_entry,
                        ref=e.entry_id,
                        freshness=e.freshness,
                        fetched_at=e.fetched_at,
                        is_authoritative_for=e.is_authoritative_for,
                    )
                ],
            )
        ],
    )
    again = ClaimEvidenceMap.model_validate(cem.model_dump(mode="json"))
    assert again.schema_version == SCHEMA_VERSION
    assert again.claims[0].evidence[0].ref == e.entry_id


def test_kl_entry_rejects_unknown_fields() -> None:
    payload = _kl_entry().model_dump(mode="json")
    payload["rogue"] = True
    with pytest.raises(ValidationError):
        KnowledgeLayerEntry.model_validate(payload)
