"""OBS-01 cross-process trace correlation: REAL ingress store -> worker restore.

OTel ambient context does NOT cross the Pub/Sub boundary (DUR-03): the worker's
model/tool spans fire in a separate process from the API ingress that started the
trace. So the inbound W3C ``traceparent`` HTTP header must be:

  1. read at the REAL ingress (``POST /v1/tasks`` in api/app.py) and stored on
     ``TaskRequest.metadata["traceparent"]`` BEFORE ``create_task()`` — which the
     shared TaskService copies onto the durable ``TaskRecord.metadata``; and
  2. restored in the worker (orchestrator) before opening the per-task root span,
     so the worker's spans join the trace started at ingress.

This proves the STORE path via a real TestClient POST (the persisted record carries
the header value) and the RESTORE path via the orchestrator rooting its span under
that exact trace — NOT a pre-populated in-process metadata dict.
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

import agent_mesh.observability as obs
from agent_mesh.contracts.enums import Entrypoint
from agent_mesh.contracts.models import RequesterIdentity, TaskRecord

# A well-formed W3C traceparent: version-traceid-spanid-flags.
_TRACEID = "0af7651916cd43dd8448eb211c80319c"
_TRACEPARENT = f"00-{_TRACEID}-b7ad6b7169203331-01"


@pytest.fixture
def tracer_provider(span_exporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    obs.set_tracer_provider_override(provider)
    try:
        yield provider
    finally:
        obs.set_tracer_provider_override(None)


def _client():
    from fastapi.testclient import TestClient

    from agent_mesh.api import app as app_module

    return TestClient(app_module.app), app_module


def _task_request_body() -> dict:
    return {
        "tenant_id": "t1",
        "client_slug": "c1",
        "entrypoint": "api",
        "requester": {"requester_id": "r1", "entrypoint": "api"},
        "prompt": "summarise the meeting notes",
    }


def test_ingress_persists_inbound_traceparent_on_task_record():
    """STORE side: a POST /v1/tasks with a traceparent header persists that exact
    value onto the durable TaskRecord.metadata (proves the real ingress write)."""
    client, app_module = _client()
    resp = client.post(
        "/v1/tasks", json=_task_request_body(), headers={"traceparent": _TRACEPARENT}
    )
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    record = app_module._service.repo.get_task(task_id)
    assert record is not None
    assert record.metadata.get("traceparent") == _TRACEPARENT


def test_worker_restores_traceparent_and_joins_ingress_trace(
    tracer_provider, span_exporter
):
    """RESTORE side: the worker reads the stored traceparent and roots its spans
    under that SAME trace id (cross-Pub/Sub correlation, not in-process)."""
    from agent_mesh.worker import orchestrator

    task = TaskRecord(
        tenant_id="t1",
        client_slug="c1",
        entrypoint=Entrypoint.API,
        requester=RequesterIdentity(requester_id="r1", entrypoint=Entrypoint.API),
        session_id="s1",
        prompt="summarise the meeting notes",
        metadata={"traceparent": _TRACEPARENT},
    )
    result = orchestrator.run_mesh(task)

    spans = span_exporter.get_finished_spans()
    assert spans, "expected the worker root span"
    root = spans[-1]
    # The worker's span must carry the SAME trace id as the inbound header.
    assert format(root.context.trace_id, "032x") == _TRACEID
    assert result.trace_id == _TRACEID


def test_store_then_restore_end_to_end_via_real_persisted_record(
    tracer_provider, span_exporter
):
    """Full chain in ONE flow: POST /v1/tasks with a traceparent header -> read the
    REAL persisted TaskRecord back from the repo -> run the worker on THAT record ->
    the worker span roots under the inbound trace. This proves store AND restore
    compose over the durable record, NOT a hand-built in-process metadata dict."""
    from agent_mesh.worker import orchestrator

    client, app_module = _client()
    resp = client.post(
        "/v1/tasks", json=_task_request_body(), headers={"traceparent": _TRACEPARENT}
    )
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    # The REAL durable record (not a fixture-built dict).
    record = app_module._service.repo.get_task(task_id)
    assert record is not None
    assert record.metadata.get("traceparent") == _TRACEPARENT

    result = orchestrator.run_mesh(record)

    spans = span_exporter.get_finished_spans()
    assert spans, "expected the worker root span"
    root = spans[-1]
    assert format(root.context.trace_id, "032x") == _TRACEID
    assert result.trace_id == _TRACEID


def test_no_traceparent_starts_fresh_root_no_keyerror(tracer_provider, span_exporter):
    """A task created WITHOUT a traceparent header still runs: fresh root trace,
    no KeyError."""
    from agent_mesh.worker import orchestrator

    task = TaskRecord(
        tenant_id="t1",
        client_slug="c1",
        entrypoint=Entrypoint.API,
        requester=RequesterIdentity(requester_id="r1", entrypoint=Entrypoint.API),
        session_id="s1",
        prompt="summarise the meeting notes",
        metadata={},
    )
    result = orchestrator.run_mesh(task)
    assert result.trace_id is not None
    assert result.trace_id != _TRACEID  # fresh, not the inbound trace
