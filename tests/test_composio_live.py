"""Composio aggregator live lane (04-08, TOOL-04, D-09) — OPT-IN ONLY.

One REAL read through the gateway via the Composio managed-auth Tool Router. The whole
module is ``@pytest.mark.live`` (deselected without ``-m live``) and SKIPS unless
``COMPOSIO_API_KEY`` is set — so the default ``make test`` run NEVER reaches Composio
and NEVER requires the SDK. The composio SDK import is INSIDE the adapter (lazy), and
this module imports no SDK at top level, so collection stays SDK-free (it SKIPS, never
ERRORS, when the key is absent).
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.live  # whole module is opt-in live lane

_SKIP_REASON = "COMPOSIO_API_KEY not set; the Composio live read is opt-in (D-12)"


@pytest.mark.skipif(not os.getenv("COMPOSIO_API_KEY"), reason=_SKIP_REASON)
def test_composio_real_read_through_gateway():
    """A real Composio read reaches the registered adapter (NOT the stub) and returns
    a non-stub aggregator result. Requires COMPOSIO_API_KEY + a connected account."""
    from pathlib import Path

    from agent_mesh.contracts.enums import ToolCategory
    from agent_mesh.contracts.models import ToolCall
    from agent_mesh.tools.credentials import EnvCredentialResolver
    from agent_mesh.tools.gateway import ToolGateway

    manifest = Path(__file__).resolve().parents[1] / "manifests" / "tool_pack_manifest.yaml"
    gw = ToolGateway.from_manifest(manifest)

    call = ToolCall(
        task_id="task-composio-live",
        tenant_id="tenant-live",
        tool_name="composio_gmail_list_messages",
        category=ToolCategory.READ,
        approval_required=False,
        parameters={"max_results": 1},
        requester_id="req-live",
    )

    result = gw.execute(call, resolver=EnvCredentialResolver())

    # The registered adapter ran (SC-3): NOT the deterministic stub.
    assert result.get("stub") is not True, "live read fell through to the stub (SC-3 regression)"
    assert result.get("aggregator") == "composio"
    assert "result" in result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-m", "live", "-v"]))
