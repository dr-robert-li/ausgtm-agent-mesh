"""D-10 tool-event OTel span (closes OBS-01).

Each tool execution emits exactly one OTel span carrying
tool/provider/category/integration_style/approval_state/outcome and the shared
correlation keys (tenant/task/requester) — and NEVER a raw credential or full
payload. Uses an injected in-memory exporter via set_tracer_provider_override so
the assertion is hermetic and creds-free.
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

import agent_mesh.observability as obs
from agent_mesh.contracts.enums import ToolCategory
from agent_mesh.contracts.models import ToolCall
from agent_mesh.tools import adapters
from agent_mesh.tools.gateway import ToolGateway

from pathlib import Path

MANIFEST = Path(__file__).resolve().parents[1] / "manifests" / "tool_pack_manifest.yaml"
SENTINEL_CRED = "SENTINEL-SECRET-DO-NOT-LEAK-span"


@pytest.fixture(autouse=True)
def _isolated_registry():
    saved = dict(adapters._REGISTRY)
    adapters._REGISTRY.clear()
    try:
        yield
    finally:
        adapters._REGISTRY.clear()
        adapters._REGISTRY.update(saved)


@pytest.fixture
def wired_exporter(span_exporter):
    """Inject a provider wired to the in-memory exporter as the tracer override."""
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    obs.set_tracer_provider_override(provider)
    try:
        yield span_exporter
    finally:
        obs.set_tracer_provider_override(None)


class _Resolver:
    def __init__(self, value):
        self.value = value

    def resolve(self, name):
        return self.value if name else None


def _call(tool_name, parameters):
    return ToolCall(
        task_id="task-span-1",
        tenant_id="tenant-span-1",
        tool_name=tool_name,
        category=ToolCategory.READ,
        approval_required=False,
        parameters=parameters,
        requester_id="req-span-1",
    )


def test_execute_emits_exactly_one_tool_event_span(wired_exporter):
    gw = ToolGateway.from_manifest(MANIFEST)

    def fake(spec, params, *, credential=None):
        return {"company": "Acme", "id": "1"}

    adapters.register("hubspot", fake)
    call = _call("hubspot_lookup_company", {"object_type": "companies", "query": "Acme"})
    gw.execute(call, resolver=_Resolver(SENTINEL_CRED))

    spans = wired_exporter.get_finished_spans()
    assert len(spans) == 1
    attrs = dict(spans[0].attributes)
    assert attrs["tool"] == "hubspot_lookup_company"
    assert attrs["provider"] == "hubspot"
    assert attrs["category"] == "read"
    assert attrs["integration_style"] == "direct_api"
    assert "approval_state" in attrs
    assert "outcome" in attrs
    # correlation keys present
    assert attrs["task_id"] == "task-span-1"
    assert attrs["tenant_id"] == "tenant-span-1"


def test_span_attributes_never_contain_credential_or_payload(wired_exporter):
    gw = ToolGateway.from_manifest(MANIFEST)

    def fake(spec, params, *, credential=None):
        return {"company": "Acme", "id": "1"}

    adapters.register("hubspot", fake)
    call = _call(
        "hubspot_lookup_company",
        {"object_type": "companies", "query": "SecretCompanyName"},
    )
    gw.execute(call, resolver=_Resolver(SENTINEL_CRED))

    spans = wired_exporter.get_finished_spans()
    assert len(spans) == 1
    blob = repr(dict(spans[0].attributes))
    assert SENTINEL_CRED not in blob
    assert "SecretCompanyName" not in blob  # full payload not in span


def test_span_emitted_even_for_stub_outcome(wired_exporter):
    """No credential -> stub, but a span is still emitted with outcome='stub'."""
    gw = ToolGateway.from_manifest(MANIFEST)
    call = _call("hubspot_lookup_company", {"object_type": "companies", "query": "Acme"})
    gw.execute(call, resolver=_Resolver(None))

    spans = wired_exporter.get_finished_spans()
    assert len(spans) == 1
    assert dict(spans[0].attributes)["outcome"] == "stub"
