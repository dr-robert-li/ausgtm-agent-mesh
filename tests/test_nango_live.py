"""Nango aggregator live lane (04-08, TOOL-04, D-09) — OPT-IN ONLY.

One REAL read through the gateway via the self-hosted Nango REST proxy over ``httpx``
(NO nango python package — RESEARCH Pitfall 1). The whole module is
``@pytest.mark.live`` (deselected without ``-m live``) and SKIPS unless ALL FOUR Nango
env vars are set (``NANGO_HOST`` / ``NANGO_SECRET_KEY`` / ``NANGO_CONNECTION_ID`` /
``NANGO_PROVIDER_CONFIG_KEY``) — so the default ``make test`` run NEVER reaches Nango.
``httpx`` is a core dep, so collection is always safe; the skip fires on env absence.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.live  # whole module is opt-in live lane

_REQUIRED_ENV = (
    "NANGO_HOST",
    "NANGO_SECRET_KEY",
    "NANGO_CONNECTION_ID",
    "NANGO_PROVIDER_CONFIG_KEY",
)
_SKIP_REASON = (
    "the Nango live read is opt-in (D-12); needs NANGO_HOST + NANGO_SECRET_KEY + "
    "NANGO_CONNECTION_ID + NANGO_PROVIDER_CONFIG_KEY"
)


@pytest.mark.skipif(
    not all(os.getenv(v) for v in _REQUIRED_ENV), reason=_SKIP_REASON
)
def test_nango_real_read_through_gateway():
    """A real Nango proxy read reaches the registered adapter (NOT the stub) and returns
    a non-stub aggregator result. Requires a self-hosted Nango + a connection."""
    from pathlib import Path

    from agent_mesh.contracts.enums import ToolCategory
    from agent_mesh.contracts.models import ToolCall
    from agent_mesh.tools.credentials import EnvCredentialResolver
    from agent_mesh.tools.gateway import ToolGateway

    manifest = Path(__file__).resolve().parents[1] / "manifests" / "tool_pack_manifest.yaml"
    gw = ToolGateway.from_manifest(manifest)

    call = ToolCall(
        task_id="task-nango-live",
        tenant_id="tenant-live",
        tool_name="nango_hubspot_list_contacts",
        category=ToolCategory.READ,
        approval_required=False,
        parameters={"limit": 1},
        requester_id="req-live",
    )

    result = gw.execute(call, resolver=EnvCredentialResolver())

    # The registered adapter ran (SC-3): NOT the deterministic stub.
    assert result.get("stub") is not True, "live read fell through to the stub (SC-3 regression)"
    assert result.get("aggregator") == "nango"
    assert "result" in result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-m", "live", "-v"]))
