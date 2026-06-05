"""Model gateway seam: provider-agnostic chat model resolution.

The mesh never calls model providers directly. All model access flows through a
LiteLLM-compatible gateway so LangChain / LangGraph / Deep Agents can route to:

  * **Anthropic Claude direct** (``anthropic/claude-*``), or
  * **GCP Vertex AI** Gemini / partner endpoints (``vertex_ai/gemini-*``,
    ``vertex_ai/claude-*``), or
  * any other provider LiteLLM supports,

without rewriting agent logic. The gateway owns the model *control plane*:
routing, cascades/fallbacks, per-user/per-task budgets, token caps, and provider
abstraction. Cloudflare AI Gateway (when configured upstream of LiteLLM) owns the
model-traffic *governance* plane (logging, DLP, query blocking, guardrails); this
module consumes those gateway decisions rather than replacing them.

Importable without LangChain installed: ``get_chat_model`` lazy-imports the
LangChain integration and raises a clear error only when actually called without
the stack present.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_mesh.settings import Settings, get_settings


@dataclass(frozen=True)
class ModelRoute:
    """A single resolved route within a routing profile."""

    tier: str  # low_complexity | medium_complexity | high_complexity
    model: str  # LiteLLM model id, e.g. "anthropic/claude-sonnet-4-6"
    provider: str  # "anthropic" | "vertex_ai" | ...


# Default mixed cascade. Mirrors config/model_gateway.yaml and the deployment
# manifest's model_routes. Anthropic-direct and Vertex AI paths are both first
# class — swap the ``model`` strings per deployment without touching agent code.
DEFAULT_PROFILE: dict[str, ModelRoute] = {
    "low_complexity": ModelRoute("low_complexity", "vertex_ai/gemini-1.5-flash", "vertex_ai"),
    "medium_complexity": ModelRoute("medium_complexity", "vertex_ai/gemini-1.5-pro", "vertex_ai"),
    "high_complexity": ModelRoute("high_complexity", "anthropic/claude-sonnet-4-6", "anthropic"),
}


def resolve_route(tier: str, settings: Settings | None = None) -> ModelRoute:
    """Resolve the model route for a complexity tier under the active profile."""
    settings = settings or get_settings()
    route = DEFAULT_PROFILE.get(tier)
    if route is None:
        raise KeyError(f"unknown complexity tier {tier!r}")
    return route


def langchain_available() -> bool:
    try:
        import langchain_core  # noqa: F401

        return True
    except Exception:
        return False


def get_chat_model(tier: str = "high_complexity", settings: Settings | None = None):
    """Return a LangChain chat model routed through the LiteLLM gateway.

    Uses ``langchain_litellm.ChatLiteLLM`` so the same call site reaches Anthropic
    direct or Vertex AI depending only on the resolved route's model id and the
    gateway's ``api_base``. Raises a clear error if the LangChain stack is not
    installed (the importable POC degrades to the orchestrator stub instead)."""
    settings = settings or get_settings()
    route = resolve_route(tier, settings)
    try:  # pragma: no cover - needs the optional runtime stack
        from langchain_litellm import ChatLiteLLM
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "LangChain model stack not installed; install the 'runtime' extra "
            "(langchain, langchain-litellm) to build live chat models. The POC "
            "runs the deterministic orchestrator stub without it."
        ) from exc

    return ChatLiteLLM(  # pragma: no cover - needs creds
        model=route.model,
        api_base=settings.model_gateway_base_url,
        max_tokens=settings.model_max_tokens,
    )
