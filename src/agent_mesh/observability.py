"""Langfuse-centered observability seam.

Langfuse is the default required observability and LLM-engineering platform for
this variant: tracing, prompt/version management, datasets/evals, token/cost
telemetry, audit dashboards, trace links, and operator review. It is
open-source / self-hostable and integrates with LangChain, OpenTelemetry, the
OpenAI SDK, and LiteLLM. (LangSmith is NOT required; it is only an optional
alternative.)

This module exposes two thin, importable-without-Langfuse helpers:

  * ``langfuse_available()`` — feature gate, like the orchestrator stack gates.
  * ``get_langchain_callback()`` — returns the Langfuse ``CallbackHandler`` to
    attach to LangChain/LangGraph runs, or ``None`` when Langfuse is not
    installed/configured (the POC then runs without remote tracing).

Cloudflare AI Gateway request/response decisions and LiteLLM token/cost metadata
are correlated into Langfuse via shared request metadata (tenant_id, client_slug,
task_id, session_id, requester_id, entrypoint, agent_role, model_route_profile,
approval_state). Observability *consumes* gateway decisions; it does not replace
gateway policy.
"""

from __future__ import annotations

from agent_mesh.settings import Settings, get_settings


def langfuse_available() -> bool:
    try:
        import langfuse  # noqa: F401

        return True
    except Exception:
        return False


def trace_metadata(
    *,
    tenant_id: str,
    client_slug: str,
    task_id: str,
    session_id: str | None,
    requester_id: str,
    entrypoint: str,
    agent_role: str | None = None,
    model_route_profile: str | None = None,
    approval_state: str | None = None,
) -> dict:
    """Build the shared request metadata attached to every model call / trace."""
    settings = get_settings()
    return {
        "tenant_id": tenant_id,
        "client_slug": client_slug,
        "task_id": task_id,
        "session_id": session_id,
        "requester_id": requester_id,
        "entrypoint": entrypoint,
        "agent_role": agent_role,
        "model_route_profile": model_route_profile or settings.model_route_profile,
        "approval_state": approval_state,
    }


def get_langchain_callback(settings: Settings | None = None):
    """Return a Langfuse LangChain CallbackHandler, or None if unavailable.

    Attach the returned handler to LangGraph / LangChain runs
    (``config={"callbacks": [handler]}``) so spans, token usage, and cost land in
    Langfuse. Returns None when Langfuse is not installed so callers can run
    without remote tracing."""
    settings = settings or get_settings()
    if not langfuse_available():
        return None
    try:  # pragma: no cover - needs langfuse + keys
        from langfuse.callback import CallbackHandler

        return CallbackHandler(
            public_key=settings.langfuse_public_key or None,
            secret_key=settings.langfuse_secret_key or None,
            host=settings.langfuse_host or None,
        )
    except Exception:  # pragma: no cover
        return None
