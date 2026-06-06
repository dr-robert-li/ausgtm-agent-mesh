"""Google Workspace adapter — live lane (opt-in, real Drive call) (04-06).

OPT-IN ONLY. ``pytestmark = pytest.mark.live`` keeps this out of the default suite
(``deselected`` without ``-m live``), and it SKIPS (does NOT error) unless
``GOOGLE_WORKSPACE_OAUTH`` is exported — gated on the GWS-specific secret, NOT the
shared ``live_creds`` fixture (which gates on Anthropic/Vertex/CF, a different lane).

When the refresh-token blob IS present this runs ONE real ``google_drive_search``
through ``ToolGateway.execute(call, resolver=EnvCredentialResolver())`` and asserts a
NON-stub, schema-conforming result — proving the boundary is real (D-08), the OAuth
creds resolve + auto-refresh at execution time, and the output passes the gateway's
post-call schema validation (not quarantined).
"""

from __future__ import annotations

import os

import pytest

from agent_mesh.contracts.enums import ToolCategory
from agent_mesh.contracts.models import ToolCall

pytestmark = pytest.mark.live


@pytest.fixture
def gws_oauth() -> str:
    """Skip cleanly unless the GWS refresh-token blob is exported.

    NOT ``live_creds`` (that gates the model lane). The GWS live lane needs its own
    secret; absence is a SKIP, never an error.
    """
    blob = os.getenv("GOOGLE_WORKSPACE_OAUTH")
    if not blob:
        pytest.skip("GOOGLE_WORKSPACE_OAUTH not exported; GWS live lane requires it")
    return blob


def test_live_drive_search_runs_real_call_through_gateway(gws_oauth):
    from pathlib import Path

    from agent_mesh.tools.credentials import EnvCredentialResolver
    from agent_mesh.tools.gateway import ToolGateway

    manifest = Path(__file__).resolve().parents[1] / "manifests" / "tool_pack_manifest.yaml"
    gateway = ToolGateway.from_manifest(manifest)

    call = ToolCall(
        task_id="live-gws-task",
        tenant_id="live-tenant",
        tool_name="google_drive_search",
        category=ToolCategory.READ,
        approval_required=False,
        requester_id="live-requester",
        parameters={"query": "test", "max_results": 1},
    )

    result = gateway.execute(call, resolver=EnvCredentialResolver())

    # A real call (not the deterministic stub) and schema-conforming (not quarantined).
    assert result.get("stub") is not True
    assert "outcome" not in result or result["outcome"] not in (
        "stub",
        "output_quarantined",
    )
    assert "results" in result
    assert isinstance(result["results"], list)
