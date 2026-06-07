"""Xero via the EXISTING Composio adapter (05-07, TOOL-03, D-07) — default + opt-in live.

Xero ships NO new adapter module. 05-01 flipped both ``xero_*`` manifest entries to
``composio_aggregator``, so they resolve via ``adapter_key_for`` to the EXISTING
``composio`` adapter (``src/agent_mesh/tools/adapters/composio.py``) — its verb-agnostic
``session.execute(tool=tool_slug, ...)`` carries any Xero ``tool_slug`` with no adapter
code. This module proves that resolution in the DEFAULT lane and exercises one real
read-only ``xero_read_invoices`` in the OPT-IN live lane.

``xero_create_invoice`` is the financial WRITE: it stays approval-gated upstream (D-07)
and is DRAFT-only (Status: DRAFT, never auto-finalised). It is NOT exercised live here;
its mapping rides Composio's verb-agnostic execute and is proven structurally below.

Guard interaction (structural, not discipline): the credential-docs guard derives its
env-var set from all-caps underscore literals in the live-test files. This module
therefore contains exactly ONE such literal — ``COMPOSIO_API_KEY`` (the anchor) — and
references the Xero specs by name (``gw.get(...)`` / ``spec.name``), never as bare
``"XERO_..."`` literals (those live in the manifest ``resource_bindings`` only). This
keeps the derived env-var floor at exactly 12.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_MANIFEST = Path(__file__).resolve().parents[1] / "manifests" / "tool_pack_manifest.yaml"


# ---------------------------------------------------------------------------
# DEFAULT LANE (creds-free, no SDK): both flipped Xero specs resolve to the
# EXISTING "composio" adapter — closing the "default coverage rides existing"
# gap (test_aggregator_adapters covers composio only generically, by key).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tool_name", ["xero_read_invoices", "xero_create_invoice"])
def test_flipped_xero_spec_resolves_to_composio_adapter(tool_name: str) -> None:
    """Both Xero specs are ``composio_aggregator`` -> ``adapter_key_for`` -> ``"composio"``.

    Proves Xero rides the EXISTING composio adapter with NO new Xero module.
    """
    from agent_mesh.tools.adapters import adapter_key_for
    from agent_mesh.tools.gateway import ToolGateway

    gw = ToolGateway.from_manifest(_MANIFEST)
    spec = gw.get(tool_name)

    assert spec.integration_style == "composio_aggregator"
    assert adapter_key_for(spec) == "composio", (
        f"{tool_name} must resolve to the existing 'composio' adapter, not a new module"
    )


def test_no_new_xero_adapter_module_exists() -> None:
    """Xero ships NO adapter module — it rides composio.py unchanged."""
    xero_module = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "agent_mesh"
        / "tools"
        / "adapters"
        / "xero.py"
    )
    assert not xero_module.exists(), "Xero must NOT have its own adapter module"


# ---------------------------------------------------------------------------
# OPT-IN LIVE LANE: one real read through the gateway via Composio's Xero
# toolkit. Deselected without ``-m live``; SKIPS unless COMPOSIO_API_KEY is set.
# ---------------------------------------------------------------------------
_LIVE_SKIP = "COMPOSIO_API_KEY not set; the Xero (via Composio) live read is opt-in (D-12)"


@pytest.mark.live
@pytest.mark.skipif(not os.getenv("COMPOSIO_API_KEY"), reason=_LIVE_SKIP)
def test_xero_read_invoices_real_read_through_gateway() -> None:
    """A real ``xero_read_invoices`` reaches the composio adapter (NOT the stub).

    Requires COMPOSIO_API_KEY + the Xero toolkit connected in Composio (see
    docs/credentials/xero.md). Read-only — the financial write is never exercised live.
    """
    from agent_mesh.contracts.enums import ToolCategory
    from agent_mesh.contracts.models import ToolCall
    from agent_mesh.tools.credentials import EnvCredentialResolver
    from agent_mesh.tools.gateway import ToolGateway

    gw = ToolGateway.from_manifest(_MANIFEST)

    call = ToolCall(
        task_id="task-xero-live",
        tenant_id="tenant-live",
        tool_name="xero_read_invoices",
        category=ToolCategory.READ,
        approval_required=False,
        parameters={},
        requester_id="req-live",
    )

    result = gw.execute(call, resolver=EnvCredentialResolver())

    # The registered composio adapter ran (NOT the deterministic stub).
    assert result.get("stub") is not True, "live read fell through to the stub (regression)"
    assert result.get("aggregator") == "composio"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-m", "live", "-v"]))
