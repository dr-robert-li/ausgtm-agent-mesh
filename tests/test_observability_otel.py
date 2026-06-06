"""OBS-01: OTel tracing transport — init_tracing wiring + (Task 2) span emission.

Task 1 covers init_tracing: it must build a TracerProvider wired to the in-memory
exporter with NO OTLP server contacted in CI, and the module must stay importable
with the v4 langfuse path (the dead v2 import gone). Task 2 extends this file with
span-emission + trace_id assertions.
"""

from __future__ import annotations

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import agent_mesh.observability as obs
from agent_mesh.settings import Settings


def test_module_uses_v4_callback_import_and_exposes_init_tracing():
    # The v4 path is present; init_tracing/tracing_available are exported.
    assert hasattr(obs, "init_tracing")
    assert hasattr(obs, "tracing_available")
    assert obs.tracing_available() is True


def test_init_tracing_wires_in_memory_exporter_without_otlp_server(span_exporter):
    # CI lane: passing test_exporter attaches a SimpleSpanProcessor around the
    # in-memory exporter; no OTLP endpoint is contacted.
    settings = Settings()
    provider = obs.init_tracing(settings, test_exporter=span_exporter)
    assert provider is not None

    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("probe") as span:
        span.set_attribute("k", "v")

    finished = span_exporter.get_finished_spans()
    assert any(s.name == "probe" for s in finished)


def test_init_tracing_no_exporter_when_endpoint_unset(span_exporter):
    # With no test_exporter and no OTLP endpoint, no exporter is attached and no
    # network is touched — default-suite-safe. A provider is still returned.
    settings = Settings(otel_exporter_otlp_endpoint="")
    provider = obs.init_tracing(settings)
    assert provider is not None
    # Sanity: a fresh in-memory exporter wired by the test sees the span, proving
    # the provider works without any OTLP endpoint configured.
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    mem = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(mem))
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("noendpoint"):
        pass
    assert any(s.name == "noendpoint" for s in mem.get_finished_spans())


def test_set_span_metadata_skips_none_and_writes_known_keys(span_exporter):
    settings = Settings()
    provider = obs.init_tracing(settings, test_exporter=span_exporter)
    tracer = provider.get_tracer("test")
    meta = obs.trace_metadata(
        tenant_id="t1",
        client_slug="c1",
        task_id="task-123",
        session_id=None,  # must be skipped (OTel rejects None)
        requester_id="r1",
        entrypoint="api",
    )
    with tracer.start_as_current_span("meta") as span:
        obs.set_span_metadata(span, meta)

    spans = {s.name: s for s in span_exporter.get_finished_spans()}
    attrs = dict(spans["meta"].attributes)
    assert attrs["tenant_id"] == "t1"
    assert attrs["task_id"] == "task-123"
    assert "session_id" not in attrs  # None skipped
