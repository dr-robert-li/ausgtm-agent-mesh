"""CycloneDX V1_7 ML-BOM generator from the deployment + tool-pack manifests
(SI-02 / SI-02a).

Default lane (creds-free): a pure manifest -> CycloneDX JSON transform that also
persists a structured ``AIBOMSnapshot`` for the durable audit record. The
function returns the new snapshot's id so 06-06 can fill
``PromotionRecord.ai_bom_snapshot_id``.

The library has NO ``ModelCard`` model (cyclonedx-python-lib #912), so the
promoted bundle's ML metadata (prompts / dataset-version / eval-result-id /
model-route-profile) is carried as namespaced CycloneDX ``Property`` entries on a
single ``machine-learning-model`` component (the D-11 "keep conformance
pragmatic" posture).
"""

from __future__ import annotations

import json

from agent_mesh.services.ai_bom import _build_ml_bom_json, generate_ml_bom
from agent_mesh.services.repository import InMemoryRepository


def _kwargs(**over):
    base = dict(
        promoted_version="v2",
        previous_version="v1",
        dataset_version="ds-2026-06-07",
        evaluation_id="eval-abc123",
        tenant_id="tenant-example",
        client_slug="example-client",
        route_profile="mixed-cascade",
    )
    base.update(over)
    return base


def test_build_ml_bom_json_is_valid_cyclonedx_1_7() -> None:
    """The builder emits a parseable CycloneDX 1.7 JSON document."""
    js = _build_ml_bom_json(**_kwargs())
    doc = json.loads(js)
    assert doc["specVersion"] == "1.7"
    assert doc["bomFormat"] == "CycloneDX"


def test_bom_has_exactly_one_machine_learning_model_component() -> None:
    """Exactly one machine-learning-model component represents the promoted bundle."""
    doc = json.loads(_build_ml_bom_json(**_kwargs()))
    ml = [c for c in doc.get("components", []) if c.get("type") == "machine-learning-model"]
    assert len(ml) == 1
    assert ml[0]["version"] == "v2"


def test_ml_component_carries_metadata_as_properties() -> None:
    """Prompts / dataset_version / eval_result_id / model_route_profile are carried
    as namespaced CycloneDX Property entries (ModelCard gap workaround #912)."""
    doc = json.loads(_build_ml_bom_json(**_kwargs()))
    ml = next(c for c in doc["components"] if c.get("type") == "machine-learning-model")
    props = {p["name"]: p.get("value") for p in ml.get("properties", [])}
    assert props.get("agentmesh:dataset_version") == "ds-2026-06-07"
    assert props.get("agentmesh:eval_result_id") == "eval-abc123"
    assert props.get("agentmesh:model_route_profile") == "mixed-cascade"
    # Prompts are sourced from the deployment manifest's model-route profiles and
    # carried as a property (non-empty for the shipped manifest).
    assert "agentmesh:prompts" in props


def test_tool_components_mapped_from_tool_pack() -> None:
    """Tool components from the tool-pack manifest appear alongside the ML model."""
    doc = json.loads(_build_ml_bom_json(**_kwargs()))
    names = {c["name"] for c in doc.get("components", [])}
    # A representative tool from the shipped tool-pack manifest.
    assert "hubspot_create_deal" in names


def test_generate_ml_bom_persists_snapshot_and_returns_id() -> None:
    """generate_ml_bom persists an AIBOMSnapshot and returns its id; the id reads
    back tenant-scoped (suitable for PromotionRecord.ai_bom_snapshot_id)."""
    repo = InMemoryRepository()
    snapshot_id = generate_ml_bom(repo, **_kwargs())
    assert isinstance(snapshot_id, str) and snapshot_id

    snap = repo.get_ai_bom(snapshot_id, "tenant-example")
    assert snap is not None
    assert snap.tenant_id == "tenant-example"
    assert snap.client_slug == "example-client"
    assert snap.version == "v2"
    # The structured snapshot mirrors the manifest-sourced fields the CycloneDX
    # components/properties were built from.
    assert snap.tools, "tool list should be populated from the tool-pack manifest"
    assert snap.model_routes, "model_routes should be populated from the deployment manifest"


def test_generate_ml_bom_persisted_snapshot_is_tenant_scoped() -> None:
    """A snapshot owned by tenant-example is never returned for another tenant."""
    repo = InMemoryRepository()
    snapshot_id = generate_ml_bom(repo, **_kwargs())
    assert repo.get_ai_bom(snapshot_id, "tenant-other") is None
