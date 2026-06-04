import importlib

import pytest

MODULES = [
    "agent_mesh",
    "agent_mesh.contracts",
    "agent_mesh.contracts.models",
    "agent_mesh.contracts.lifecycle",
    "agent_mesh.contracts.export_schemas",
    "agent_mesh.settings",
    "agent_mesh.services.task_service",
    "agent_mesh.services.repository",
    "agent_mesh.services.dispatch",
    "agent_mesh.services.approvals",
    "agent_mesh.services.sessions",
    "agent_mesh.tools.gateway",
    "agent_mesh.worker.runner",
    "agent_mesh.worker.orchestrator",
    "agent_mesh.worker.budget",
    "agent_mesh.worker.main",
    "agent_mesh.sandbox.executor",
    "agent_mesh.api.app",
    "agent_mesh.api.slack_verify",
    "agent_mesh.api.mcp_server",
]


@pytest.mark.parametrize("module", MODULES)
def test_module_imports(module):
    """Whole package must import without optional heavy deps (ag2, pubsub, mcp)."""
    importlib.import_module(module)


def test_tool_pack_manifest_loads():
    from pathlib import Path

    from agent_mesh.tools.gateway import load_tool_pack

    manifest = Path(__file__).resolve().parents[1] / "manifests" / "tool_pack_manifest.yaml"
    specs = load_tool_pack(manifest)
    assert any(s.category.value == "write" and s.approval_required for s in specs)
    assert any(s.category.value == "read" and not s.approval_required for s in specs)
