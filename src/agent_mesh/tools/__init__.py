"""Tool Gateway.

Loads per-client tool pack manifests and exposes only approved tools to the
agents. Write-category tools are gated behind the approval ledger; the gateway
resolves credentials at execution time so agents never see raw secrets. The POC
ships stub adapters — real SaaS integrations are deliberately out of scope.
"""

from agent_mesh.tools.gateway import ToolGateway, ToolSpec, load_tool_pack

__all__ = ["ToolGateway", "ToolSpec", "load_tool_pack"]
