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
from typing import TYPE_CHECKING, Any

from agent_mesh.settings import Settings, get_settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from langchain_litellm import ChatLiteLLM as _ChatLiteLLMBase
else:  # resolved lazily inside _router_chat_litellm_cls so the POC stays importable
    _ChatLiteLLMBase = object

# Default config path for the in-process Router (model_list + cascades).
DEFAULT_CONFIG_PATH = "config/model_gateway.config.yaml"


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

# Underscore complexity tier -> hyphenated yaml ``model_name`` deployment id.
# CRITICAL: ``Router.completion(model=...)`` resolves the route by exact
# ``model_name``; passing the underscore tier key (or a raw provider id) 404s with
# "deployment not found" at call time. The stubbed-Router test cannot catch this
# (it accepts any kwargs), so this map is the single source of truth for the name
# handed to the Router.
TIER_TO_DEPLOYMENT: dict[str, str] = {
    "low_complexity": "low-complexity",
    "medium_complexity": "medium-complexity",
    "high_complexity": "high-complexity",
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


def build_router(config_path: str = DEFAULT_CONFIG_PATH):
    """Build an in-process ``litellm.Router`` from the gateway yaml (D-09).

    Loads ``model_list`` plus ``router_settings.fallbacks`` / ``num_retries`` /
    ``timeout`` so cascades and retries run IN-PROCESS — the durable budget ledger
    (not the config's inert ``max_budget``) is the sole budget enforcer. Lazy-imports
    ``yaml`` and ``litellm.Router`` so the POC stays importable without the runtime
    extra installed.
    """
    import yaml  # lazy: optional runtime dep
    from litellm import Router

    with open(config_path) as fh:
        cfg = yaml.safe_load(fh)
    router_settings = cfg.get("router_settings", {}) or {}
    return Router(
        model_list=cfg["model_list"],
        fallbacks=router_settings.get("fallbacks"),
        num_retries=router_settings.get("num_retries", 2),
        timeout=router_settings.get("timeout", 120),
    )


_ROUTER_CHAT_CLS: Any = None


def _router_chat_litellm_cls():
    """Return the ``RouterChatLiteLLM`` class, defining it lazily on first use.

    Defined inside a function because it subclasses ``langchain_litellm.ChatLiteLLM``,
    an optional runtime dependency. Importing this module must not require the stack;
    only constructing a ``RouterChatLiteLLM`` does. The class is cached so it has a
    single identity (``isinstance`` checks against ``model_gateway.RouterChatLiteLLM``
    hold).
    """
    global _ROUTER_CHAT_CLS
    if _ROUTER_CHAT_CLS is not None:
        return _ROUTER_CHAT_CLS
    from langchain_litellm import ChatLiteLLM
    from pydantic import PrivateAttr

    class RouterChatLiteLLM(ChatLiteLLM):
        """``ChatLiteLLM`` bound to a held ``litellm.Router`` (GW-01 seam).

        ``langchain_litellm`` clobbers any passed ``client`` at ``litellm.py:558``
        (``values["client"] = litellm``), so ``ChatLiteLLM(client=router)`` is
        silently ignored and the Router never runs. Overriding
        ``completion_with_retry`` / ``acompletion_with_retry`` to call
        ``self._router.completion`` / ``.acompletion`` is the fix: it routes through
        the Router (cascades, retries, budget wrapping) regardless of the clobber.
        ``Router.completion(model, messages, **kwargs)`` is signature-compatible with
        ``litellm.completion``.
        """

        # ChatLiteLLM is a pydantic-v2 model; the held Router is a private attribute
        # (not a validated field, so an arbitrary Router type is fine). Assigned
        # post-construction in get_chat_model / tests.
        _router: Any = PrivateAttr(default=None)

        def completion_with_retry(self, run_manager=None, **kwargs: Any) -> Any:
            return self._router.completion(**kwargs)

        async def acompletion_with_retry(self, run_manager=None, **kwargs: Any) -> Any:
            return await self._router.acompletion(**kwargs)

    _ROUTER_CHAT_CLS = RouterChatLiteLLM
    return RouterChatLiteLLM


# Module-level handle so tests/callers reference ``model_gateway.RouterChatLiteLLM``.
# Resolved on first attribute access via ``__getattr__`` to keep import lazy.
_ROUTER_CACHE: Any = None


def __getattr__(name: str):  # PEP 562 module-level lazy attribute
    if name == "RouterChatLiteLLM":
        return _router_chat_litellm_cls()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _get_cached_router(config_path: str = DEFAULT_CONFIG_PATH):
    """Process-cached Router (built once; reused across calls)."""
    global _ROUTER_CACHE
    if _ROUTER_CACHE is None:
        _ROUTER_CACHE = build_router(config_path)
    return _ROUTER_CACHE


def get_chat_model(tier: str = "high_complexity", settings: Settings | None = None):
    """Return a ``RouterChatLiteLLM`` backed by the process-cached in-process Router.

    The chat model's ``model=`` is the hyphenated yaml DEPLOYMENT name for the tier
    (e.g. ``"high-complexity"``), NOT a raw provider id — the Router resolves the
    actual provider/model + egress ``api_base`` per-route from its ``model_list``
    (D-06: ``api_base`` lives per-route in the yaml, never on the chat-model
    constructor here). Raises a clear error if the LangChain stack is absent."""
    settings = settings or get_settings()
    if tier not in TIER_TO_DEPLOYMENT:
        raise KeyError(f"unknown complexity tier {tier!r}")
    deployment = TIER_TO_DEPLOYMENT[tier]
    try:
        router_chat_cls = _router_chat_litellm_cls()
    except Exception as exc:  # pragma: no cover - needs the optional runtime stack
        raise RuntimeError(
            "LangChain model stack not installed; install the 'runtime' extra "
            "(langchain, langchain-litellm) to build live chat models. The POC "
            "runs the deterministic orchestrator stub without it."
        ) from exc

    # NOTE: api_base is deliberately NOT passed here — it is relocated per-route to
    # model_list[*].litellm_params.api_base in the yaml (D-06 chokepoint relocation).
    chat = router_chat_cls(
        model=deployment,
        max_tokens=settings.model_max_tokens,
    )
    chat._router = _get_cached_router()
    return chat
