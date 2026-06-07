"""CycloneDX ML-BOM generation on promotion (SI-02 / SI-02a).

On promotion, the platform must snapshot the *approved capability bundle* — the
promoted model/prompt version plus the tools it may use — as a durable,
machine-readable Bill of Materials. This module emits an **ECMA-424 / CycloneDX
v1.7 ML-BOM** built purely from the deployment + tool-pack manifests (the same
manifests the Tool Gateway reads), and persists a structured
:class:`~agent_mesh.contracts.models.AIBOMSnapshot` as the durable audit record.

Design notes
------------
* **Pure manifest -> JSON transform.** No credentials, no network. The two
  manifest paths default to the fixed repo locations so the 06-06 promotion
  call site need not source them.
* **ModelCard gap (cyclonedx-python-lib #912).** The library has no ``ModelCard``
  model, so the promoted bundle's ML metadata (prompts / dataset-version /
  eval-result-id / model-route-profile) is carried as namespaced CycloneDX
  ``Property`` entries on a single ``machine-learning-model`` component. This is
  the D-11 "keep conformance pragmatic" posture.
* **Two outputs, two purposes.** ``_build_ml_bom_json`` returns the validated
  CycloneDX 1.7 JSON string (the conformance artifact asserted by tests).
  ``generate_ml_bom`` additionally persists the structured ``AIBOMSnapshot``
  (``AIBOMSnapshot`` has no free-form JSON column, so the structured fields — the
  same fields the CycloneDX components/properties are built from — are persisted)
  and returns its ``snapshot_id`` to fill ``PromotionRecord.ai_bom_snapshot_id``.

The ``cyclonedx`` import is lazy + feature-gated (mirroring ``observability.py``)
so the module imports without the ``[aibom]`` extra; the make-test env installs
it (06-01).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from agent_mesh.contracts.models import AIBOMSnapshot

if TYPE_CHECKING:  # pragma: no cover - typing only
    from agent_mesh.services.repository import Repository

# Namespace for the CycloneDX Property entries carrying ML metadata that has no
# first-class home in the v1.7 schema (ModelCard gap #912).
_PROP_NS = "agentmesh"

# Repo-root-anchored absolute defaults (WR-08): bare CWD-relative strings are a
# latent FileNotFoundError for any future caller that omits the path kwargs in a
# worker whose CWD is not the repo root. Anchor to this module's location
# (services -> agent_mesh -> src -> repo root), matching self_improvement.py.
_MODULE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _MODULE_DIR.parents[2]
_DEFAULT_DEPLOYMENT_MANIFEST = str(_REPO_ROOT / "manifests" / "deployment.manifest.yaml")
_DEFAULT_TOOL_PACK_MANIFEST = str(_REPO_ROOT / "manifests" / "tool_pack_manifest.yaml")


def cyclonedx_available() -> bool:
    """True when cyclonedx-python-lib (the ``[aibom]`` extra) is importable.

    Mirrors ``observability.langfuse_available`` so callers can gate the BOM
    generator the same way the orchestrator gates its optional stack."""
    try:
        import cyclonedx.model.bom  # noqa: F401

        return True
    except Exception:
        return False


def _load_manifest(path: str | Path) -> dict[str, Any]:
    """Read a YAML manifest (mirrors ``tools.gateway.load_tool_pack``)."""
    return yaml.safe_load(Path(path).read_text()) or {}


def _extract_prompts(deployment: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive a prompt-bundle descriptor list from the deployment manifest.

    The POC manifest does not carry per-agent prompt text; the model-route
    profiles are the closest versioned prompt/route bundle. Each profile becomes
    one prompt entry so the AI-BOM records *which* route bundle was promoted."""
    routes = deployment.get("model_routes", {}) or {}
    profiles = routes.get("profiles", {}) or {}
    return [{"name": name, "kind": "model_route_profile"} for name in sorted(profiles)]


def _extract_tools(tool_pack: dict[str, Any]) -> list[dict[str, Any]]:
    """Project the tool-pack manifest into the AI-BOM tool list."""
    tools: list[dict[str, Any]] = []
    for raw in tool_pack.get("tools", []) or []:
        tools.append(
            {
                "name": raw.get("name"),
                "provider": raw.get("provider", "unknown"),
                "category": raw.get("category"),
                "integration_style": raw.get("integration_style", "direct_api"),
                "approval_required": bool(raw.get("approval_required", False)),
            }
        )
    return tools


def _build_ml_bom_json(
    *,
    promoted_version: str,
    previous_version: str | None,
    dataset_version: str | None,
    evaluation_id: str | None,
    tenant_id: str,
    client_slug: str,
    route_profile: str | None,
    deployment_manifest_path: str = _DEFAULT_DEPLOYMENT_MANIFEST,
    tool_pack_manifest_path: str = _DEFAULT_TOOL_PACK_MANIFEST,
) -> str:
    """Build the CycloneDX v1.7 ML-BOM JSON string from the manifests.

    Pure transform: one ``machine-learning-model`` component for the promoted
    bundle (with ML metadata carried as namespaced ``Property`` entries — #912),
    plus one component per tool in the tool-pack manifest. Returns the serialized
    CycloneDX 1.7 JSON document (the conformance artifact)."""
    # Lazy, feature-gated import (EXACT paths confirmed in the 06-01 SUMMARY).
    from cyclonedx.model import Property
    from cyclonedx.model.bom import Bom
    from cyclonedx.model.component import Component, ComponentType
    from cyclonedx.output import make_outputter
    from cyclonedx.schema import OutputFormat, SchemaVersion

    deployment = _load_manifest(deployment_manifest_path)
    tool_pack = _load_manifest(tool_pack_manifest_path)

    prompts = _extract_prompts(deployment)
    tools = _extract_tools(tool_pack)

    bom = Bom()

    # The promoted model/prompt bundle as a single machine-learning-model
    # component. ML metadata rides as namespaced Property entries (no ModelCard).
    props: list[Property] = [
        Property(name=f"{_PROP_NS}:tenant_id", value=tenant_id),
        Property(name=f"{_PROP_NS}:client_slug", value=client_slug),
        Property(name=f"{_PROP_NS}:prompts", value=json.dumps(prompts)),
    ]
    if previous_version is not None:
        props.append(Property(name=f"{_PROP_NS}:previous_version", value=previous_version))
    if dataset_version is not None:
        props.append(Property(name=f"{_PROP_NS}:dataset_version", value=dataset_version))
    if evaluation_id is not None:
        props.append(Property(name=f"{_PROP_NS}:eval_result_id", value=evaluation_id))
    if route_profile is not None:
        props.append(Property(name=f"{_PROP_NS}:model_route_profile", value=route_profile))

    ml_component = Component(
        name=f"{client_slug}-promoted-bundle",
        type=ComponentType.MACHINE_LEARNING_MODEL,
        version=promoted_version,
        description="Promoted self-improvement capability bundle (model + prompt routes).",
        properties=props,
    )
    bom.components.add(ml_component)

    # Each approved tool becomes a component so the BOM enumerates the approved
    # capability surface the promoted bundle may exercise.
    for tool in tools:
        if not tool.get("name"):
            continue
        bom.components.add(
            Component(
                name=tool["name"],
                type=ComponentType.APPLICATION,
                description=f"{tool['provider']} tool ({tool['category']}, "
                f"{tool['integration_style']}).",
                properties=[
                    Property(name=f"{_PROP_NS}:provider", value=str(tool["provider"])),
                    Property(name=f"{_PROP_NS}:category", value=str(tool["category"])),
                    Property(
                        name=f"{_PROP_NS}:integration_style",
                        value=str(tool["integration_style"]),
                    ),
                    Property(
                        name=f"{_PROP_NS}:approval_required",
                        value=str(tool["approval_required"]).lower(),
                    ),
                ],
            )
        )

    return make_outputter(bom, OutputFormat.JSON, SchemaVersion.V1_7).output_as_string()


def generate_ml_bom(
    repo: Repository,
    *,
    promoted_version: str,
    previous_version: str | None,
    dataset_version: str | None,
    evaluation_id: str | None,
    tenant_id: str,
    client_slug: str,
    route_profile: str | None,
    deployment_manifest_path: str = _DEFAULT_DEPLOYMENT_MANIFEST,
    tool_pack_manifest_path: str = _DEFAULT_TOOL_PACK_MANIFEST,
) -> str:
    """Generate the CycloneDX v1.7 ML-BOM and persist it as an ``AIBOMSnapshot``.

    Builds the conformant CycloneDX JSON (validated via ``_build_ml_bom_json``),
    then persists a structured ``AIBOMSnapshot`` (the durable audit record;
    ``AIBOMSnapshot`` has no free-form JSON column, so the manifest-sourced
    structured fields — the same fields the CycloneDX components/properties were
    built from — are persisted) via ``repo.upsert_ai_bom`` (the method added in
    06-01). Returns the new ``snapshot_id`` so 06-06 can fill
    ``PromotionRecord.ai_bom_snapshot_id``.

    Pure transform — no live credentials, no network call."""
    # Validate-by-construction: build the CycloneDX 1.7 document. (cyclonedx-python-lib
    # guarantees a valid V1_7 structure — T-06-15.)
    _build_ml_bom_json(
        promoted_version=promoted_version,
        previous_version=previous_version,
        dataset_version=dataset_version,
        evaluation_id=evaluation_id,
        tenant_id=tenant_id,
        client_slug=client_slug,
        route_profile=route_profile,
        deployment_manifest_path=deployment_manifest_path,
        tool_pack_manifest_path=tool_pack_manifest_path,
    )

    deployment = _load_manifest(deployment_manifest_path)
    tool_pack = _load_manifest(tool_pack_manifest_path)

    snapshot = AIBOMSnapshot(
        tenant_id=tenant_id,
        client_slug=client_slug,
        version=promoted_version,
        agents=[],
        tools=_extract_tools(tool_pack),
        skills=[],
        prompts=_extract_prompts(deployment),
        model_routes=deployment.get("model_routes", {}) or {},
    )
    persisted = repo.upsert_ai_bom(snapshot)
    return persisted.snapshot_id
