"""Langfuse-centered observability seam.

Langfuse is the default required observability and LLM-engineering platform for
this variant: tracing, prompt/version management, datasets/evals, token/cost
telemetry, audit dashboards, trace links, and operator review. It is
open-source / self-hostable and integrates with LangChain, OpenTelemetry, the
OpenAI SDK, and LiteLLM. (LangSmith is NOT required; it is only an optional
alternative.)

OBS-01 / OBS-02 split (D-07):

* **OBS-01 — tracing TRANSPORT** is OTel-first. ``init_tracing()`` builds an OTel
  ``TracerProvider`` whose default consumer is Langfuse (Langfuse v4 is a thin
  layer over OTel). A parallel-SIEM exporter seam lets a second processor consume
  the same spans without dropping Langfuse. Model/tool/approval events emit spans
  carrying the shared request metadata (``trace_metadata()``) as span attributes.
* **OBS-02 — prompt/version + datasets/evals** is Langfuse-NATIVE; OTel does not
  cover it. ``get_prompt_with_fallback()`` pulls a versioned prompt from Langfuse
  when reachable and returns a trusted local default offline (the stub-fallback
  invariant that keeps ``make test`` green with no cloud deps).

This module stays importable without Langfuse OR OpenTelemetry installed: every
optional-dep import is lazy and degrades to a None/feature-gate return.

Cloudflare AI Gateway request/response decisions and LiteLLM token/cost metadata
are correlated into Langfuse via shared request metadata (tenant_id, client_slug,
task_id, session_id, requester_id, entrypoint, agent_role, model_route_profile,
approval_state). Observability *consumes* gateway decisions; it does not replace
gateway policy.
"""

from __future__ import annotations

from typing import Any

from agent_mesh.settings import Settings, get_settings

# Logical OTel resource name for spans emitted by the mesh worker.
_SERVICE_NAME = "agent-mesh-worker"

# Span-attribute keys carrying the shared request metadata. A single source of
# truth so the emit-side (set_span_metadata) and the assert-side (tests) agree.
_SPAN_METADATA_KEYS = (
    "tenant_id",
    "client_slug",
    "task_id",
    "session_id",
    "requester_id",
    "entrypoint",
    "agent_role",
    "model_route_profile",
    "approval_state",
)


def langfuse_available() -> bool:
    try:
        import langfuse  # noqa: F401

        return True
    except Exception:
        return False


def tracing_available() -> bool:
    """True when the OpenTelemetry SDK is importable.

    Mirrors :func:`langfuse_available` so callers gate the tracing transport the
    same way the orchestrator gates its stack. The default suite installs OTel
    (03-01 pins), but the module must stay importable without it."""
    try:
        import opentelemetry.sdk.trace  # noqa: F401

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


def init_tracing(settings: Settings | None = None, *, test_exporter: Any | None = None):
    """Build and return an OTel ``TracerProvider`` for the mesh worker (OBS-01).

    Returns the provider (so the caller — or a test — owns its lifetime) WITHOUT
    mutating the global ``set_tracer_provider`` state: running several tests in one
    process must each get their own isolated provider+exporter, and a global
    provider is install-once-per-process (the second install is silently ignored).
    Callers that want ambient context pass the provider's tracer explicitly.

    Exporter selection:

    * ``test_exporter`` passed (CI / unit tests): attach a ``SimpleSpanProcessor``
      around it (the in-memory exporter from conftest) — no server is contacted,
      and spans are visible synchronously via ``get_finished_spans()``.
    * else, when ``settings.otel_exporter_otlp_endpoint`` is set: attach a
      ``BatchSpanProcessor(OTLPSpanExporter(endpoint=...))`` — Langfuse is the
      default OTLP consumer (the endpoint value is an operator/live-lane runtime
      decision, NOT hardcoded here; e.g. ``{host}/api/public/otel/v1/traces``).
    * else: no exporter is attached (default-suite-safe — spans go nowhere).

    PARALLEL-SIEM SEAM (D-07): a second exporter/processor can be added below the
    primary one WITHOUT dropping Langfuse — spans fan out to every registered
    processor. The seam is commented inline so a deployment can wire a SIEM
    exporter (e.g. an OTLP endpoint to a security data lake) alongside Langfuse.
    """
    settings = settings or get_settings()
    if not tracing_available():
        return None

    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        SimpleSpanProcessor,
    )

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": _SERVICE_NAME,
                "deployment.environment": settings.tenant_id,
            }
        )
    )

    if test_exporter is not None:
        # CI / unit: synchronous, in-memory, no network.
        provider.add_span_processor(SimpleSpanProcessor(test_exporter))
    elif settings.otel_exporter_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
            )
        )
        # --- PARALLEL-SIEM SEAM (D-07) -------------------------------------
        # A second, independent exporter can consume the SAME spans here
        # WITHOUT displacing the Langfuse OTLP exporter above. Spans fan out to
        # every registered processor, so a deployment that wants its security
        # data lake to receive a copy of the audit trace adds, e.g.:
        #
        #   provider.add_span_processor(
        #       BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.siem_otlp_endpoint))
        #   )
        #
        # Langfuse stays the default consumer; the SIEM is additive, never a
        # replacement. Left unwired in the POC (no SIEM endpoint setting yet).
        # -------------------------------------------------------------------
    return provider


def set_span_metadata(span, metadata: dict) -> None:
    """Set the shared-metadata dict as span attributes on ``span`` (OBS-01).

    Only the known ``trace_metadata()`` keys are written, and ``None`` values are
    skipped (OTel rejects ``None`` attribute values). NEVER write raw credentials
    or full prompt bodies here (T-03-03-02): the caller passes ``trace_metadata()``
    output, which is correlation keys only."""
    if span is None or not metadata:
        return
    for key in _SPAN_METADATA_KEYS:
        value = metadata.get(key)
        if value is not None:
            span.set_attribute(key, value)


def extract_otel_context(traceparent: str | None):
    """Build an OTel parent ``Context`` from an inbound W3C ``traceparent`` header.

    Returns ``None`` when no traceparent is present or OTel is unavailable, so the
    worker starts a FRESH root trace (no crash). A malformed traceparent yields an
    empty/invalid context that the propagator ignores — telemetry-only, never a
    trust signal (T-03-03-06)."""
    if not traceparent or not tracing_available():
        return None
    try:
        from opentelemetry.trace.propagation.tracecontext import (
            TraceContextTextMapPropagator,
        )

        return TraceContextTextMapPropagator().extract({"traceparent": traceparent})
    except Exception:  # pragma: no cover - defensive; malformed header
        return None


def span_trace_id(span) -> str | None:
    """Return the 32-hex-char trace id of ``span``'s context, or ``None``.

    Used to populate ``OrchestrationResult.trace_id`` from the SAME span the
    worker roots its run under, so ``trace_id`` and the exported spans share one
    id (not a free-standing minted id)."""
    if span is None:
        return None
    try:
        ctx = span.get_span_context()
        if ctx is None or not ctx.trace_id:
            return None
        return format(ctx.trace_id, "032x")
    except Exception:  # pragma: no cover - defensive
        return None


def get_langchain_callback(settings: Settings | None = None):
    """Return a Langfuse LangChain CallbackHandler, or None if unavailable.

    Attach the returned handler to LangGraph / LangChain runs
    (``config={"callbacks": [handler]}``) so spans, token usage, and cost land in
    Langfuse. Returns None when Langfuse is not installed so callers can run
    without remote tracing.

    Langfuse v4 is OTel-native; the CallbackHandler lives at
    ``langfuse.langchain`` (the v2 ``langfuse.callback`` path is DEAD under 4.x and
    raises ``ModuleNotFoundError``)."""
    settings = settings or get_settings()
    if not langfuse_available():
        return None
    try:  # pragma: no cover - needs langfuse + keys
        # v4 path. NOT ``from langfuse.callback import CallbackHandler`` (v2, dead).
        from langfuse.langchain import CallbackHandler

        return CallbackHandler()
    except Exception:  # pragma: no cover
        return None


def get_prompt_with_fallback(name: str, local_default: str) -> str:
    """Return a Langfuse-managed versioned prompt, or ``local_default`` offline (OBS-02).

    Pulls the named prompt from Langfuse when reachable (operator-curated,
    versioned). When Langfuse is uninstalled/unreachable/unconfigured, returns the
    trusted ``local_default`` — keeping ``make test`` green with no cloud deps
    (the stub-fallback invariant) and avoiding prompt-injection from an
    unreachable remote (T-03-03-04: the local default is trusted).
    """
    if not langfuse_available():
        return local_default
    try:  # pragma: no cover - needs langfuse + keys + reachable host
        from langfuse import Langfuse

        settings = get_settings()
        client = Langfuse(
            public_key=settings.langfuse_public_key or None,
            secret_key=settings.langfuse_secret_key or None,
            host=settings.langfuse_host or None,
        )
        prompt = client.get_prompt(name)
        return prompt.prompt
    except Exception:  # pragma: no cover - unreachable/unconfigured -> trusted default
        return local_default
