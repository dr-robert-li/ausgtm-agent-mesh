"""Architecture-validation tests for the LangChain/LangGraph/Deep Agents/Langfuse
variant: required default stack, required toolpacks, model-gateway routing posture,
and the GUI admin read-model. These guard the design contract, not live behaviour.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from agent_mesh.gui.admin_console import (
    ADMIN_SECTIONS,
    model_routing_view,
    observability_view,
    stack_view,
    toolpack_view,
)
from agent_mesh.worker.model_gateway import DEFAULT_PROFILE, resolve_route

REPO_ROOT = Path(__file__).resolve().parents[1]

# Toolpacks the variant must ship (extensible later).
REQUIRED_PROVIDERS = {
    "xero",
    "hubspot",
    "webflow",
    "bitscale",
    "calcom",
    "clockify",
    "beehiiv",
    "google_workspace",
}


def _manifest() -> dict:
    path = REPO_ROOT / "manifests" / "tool_pack_manifest.yaml"
    return yaml.safe_load(path.read_text())


def test_required_toolpack_providers_present():
    providers = {t["provider"] for t in _manifest()["tools"]}
    missing = REQUIRED_PROVIDERS - providers
    assert not missing, f"missing required toolpack providers: {sorted(missing)}"


def test_write_class_tools_require_approval():
    write_like = {"write", "external_send", "financial", "publishing", "admin"}
    for tool in _manifest()["tools"]:
        if tool["category"] in write_like:
            assert tool.get("approval_required") is True, (
                f"{tool['name']} is {tool['category']} but not approval-gated"
            )


def test_every_tool_declares_an_integration_style():
    allowed = {"direct_api", "mcp_server", "aggregate_mcp", "nango_aggregator"}
    for tool in _manifest()["tools"]:
        assert tool.get("integration_style") in allowed, (
            f"{tool['name']} has an unknown integration_style"
        )


def test_deployment_manifest_declares_required_stack():
    manifest = yaml.safe_load(
        (REPO_ROOT / "manifests" / "deployment.manifest.yaml").read_text()
    )
    stack = manifest["stack"]
    assert "langgraph" in stack["agent_framework"]
    assert "deepagents" in stack["agent_framework"]
    assert stack["observability"] == "langfuse"
    # LangSmith must be optional only, never required.
    assert "optional" in stack["langsmith"]


def test_model_gateway_supports_anthropic_and_vertex():
    providers = {r.provider for r in DEFAULT_PROFILE.values()}
    assert "anthropic" in providers
    assert "vertex_ai" in providers
    assert resolve_route("high_complexity").provider == "anthropic"


def test_stack_view_marks_required_components():
    view = stack_view()
    assert "REQUIRED" in view["agent_framework"]
    assert "REQUIRED" in view["observability"]
    assert "not required" in view["langsmith"]


def test_admin_console_covers_required_sections():
    keys = {s.key for s in ADMIN_SECTIONS}
    for required in {
        "tasks", "approvals", "toolpacks", "mcp", "aibom",
        "budget", "memory", "improve", "deploy", "observability",
    }:
        assert required in keys


def test_admin_console_views_build():
    assert model_routing_view()["provider_mode"]
    assert observability_view()["platform"] == "langfuse"
    rows = toolpack_view()
    assert any(r["approval_required"] for r in rows)
    assert any(not r["approval_required"] for r in rows)
