"""Pure read-model helpers for the admin/operator console.

These functions build the data the Streamlit GUI renders. They are deliberately
free of any Streamlit import so they can be unit-tested and reused by the CLI.
Each helper answers one operator question and returns plain dicts/lists.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_mesh.settings import Settings, get_settings
from agent_mesh.tools.gateway import ToolSpec, load_tool_pack

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class AdminSection:
    key: str
    title: str
    description: str


# The operator console covers exactly these surfaces (acceptance criteria).
ADMIN_SECTIONS: list[AdminSection] = [
    AdminSection("tasks", "Task monitoring", "Live task lifecycle, states, and run history."),
    AdminSection("approvals", "Approvals", "Pending/decided write approvals (HITL ledger)."),
    AdminSection("toolpacks", "Toolpack registry", "Loaded tools, categories, approval flags."),
    AdminSection("mcp", "MCP server registry", "Registered MCP servers and client entries."),
    AdminSection("aibom", "AI-BOM", "Agents, prompts, tools, skills, model routes, versions."),
    AdminSection("budget", "Budget & routing", "Model budget ledger and routing-profile config."),
    AdminSection("memory", "Memory / context", "Memory chunks, evidence chunks, sessions."),
    AdminSection("improve", "Self-improvement", "Proposals: evaluate, approve, promote, rollback."),
    AdminSection("deploy", "Deployment checks", "Manifest validity, schema export, migrations."),
    AdminSection("observability", "Langfuse", "Trace links, health, token/cost telemetry."),
]


def model_routing_view(settings: Settings | None = None) -> dict:
    """Routing profile + provider posture for the Budget & routing section."""
    from agent_mesh.worker.model_gateway import DEFAULT_PROFILE

    settings = settings or get_settings()
    return {
        "route_profile": settings.model_route_profile,
        "provider_mode": settings.model_provider_mode,
        "gateway_base_url": settings.model_gateway_base_url,
        "monthly_budget_usd": settings.model_monthly_budget_usd,
        "max_tokens": settings.model_max_tokens,
        "routes": {tier: {"model": r.model, "provider": r.provider}
                   for tier, r in DEFAULT_PROFILE.items()},
    }


def observability_view(settings: Settings | None = None) -> dict:
    """Langfuse health/config for the observability section."""
    from agent_mesh.observability import langfuse_available

    settings = settings or get_settings()
    return {
        "platform": "langfuse",
        "available": langfuse_available(),
        "host": settings.langfuse_host,
        "configured": bool(settings.langfuse_public_key and settings.langfuse_secret_key),
        "langsmith": "optional-alternative-only (not required)",
    }


def toolpack_view(manifest_path: str | Path | None = None) -> list[dict]:
    """Toolpack registry rows for the toolpacks section."""
    default = REPO_ROOT / "manifests" / "tool_pack_manifest.yaml"
    path = Path(manifest_path) if manifest_path else default
    specs: list[ToolSpec] = load_tool_pack(path)
    return [
        {
            "name": s.name,
            "provider": s.provider,
            "category": s.category.value,
            "approval_required": s.approval_required,
        }
        for s in specs
    ]


def stack_view() -> dict:
    """The default required stack summary shown on the console home."""
    return {
        "agent_framework": "LangChain + LangGraph + Deep Agents (REQUIRED)",
        "observability": "Langfuse (REQUIRED)",
        "model_gateway": "LiteLLM-compatible (Anthropic direct + Vertex AI)",
        "cloudflare_ai_gateway": "integration-ready (model-traffic governance)",
        "langsmith": "optional alternative only (not required)",
    }
