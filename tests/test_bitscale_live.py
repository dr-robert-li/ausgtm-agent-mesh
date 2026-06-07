"""Bitscale live lane (05-03, TOOL-03, D-07) — OPT-IN, READS ONLY.

The whole module is ``@pytest.mark.live`` (deselected without ``-m live``) and SKIPS
inline when ``BITSCALE_API_KEY`` is unset — so ``make test`` never reaches Bitscale and
stays creds-free. This gates on the Bitscale key directly (NOT the shared model/gateway
``live_creds`` fixture — a different credential axis).

Proves the direct_api integration style end-to-end on the REAL provider: a real
``bitscale_list_grids`` (and ``bitscale_get_workspace``) flows through
``gateway.execute(call, resolver=EnvCredentialResolver())`` with the ``X-API-Key``
resolved only at execution time (D-02), returning a non-stub, output-schema-conforming
dict.

CREDIT-SAFETY (LOCKED): this file is READS ONLY. ``bitscale_run_grid`` consumes the
client's PAID credits on their real ``australiagtm.com`` workspace and is NEVER executed
here — its mapping is proven only in the default-lane fake-httpx test + the upstream
approval gate. There is intentionally NO run_grid call anywhere in this module.

The credit-free reads (list_grids, get_workspace) need NO ``grid_id`` resource binding,
so the manifest's ``REPLACE_WITH_BITSCALE_GRID_ID`` placeholder can't error these live
calls — only run_grid needs grid_id, and it is never called live.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.live  # whole module is opt-in live lane

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"
_MANIFEST = Path(__file__).resolve().parents[1] / "manifests" / "tool_pack_manifest.yaml"


def _key_present() -> bool:
    return bool(os.getenv("BITSCALE_API_KEY"))


def test_bitscale_list_grids_real_call_through_gateway():
    """A real Bitscale list-grids runs through the gateway (key resolved at call time),
    returns a NON-stub result conforming to the output schema. Skips without the key."""
    if not _key_present():
        pytest.skip("BITSCALE_API_KEY not set; live Bitscale list-grids skipped")

    from agent_mesh.contracts.enums import ToolCategory
    from agent_mesh.contracts.models import ToolCall
    from agent_mesh.tools.credentials import EnvCredentialResolver
    from agent_mesh.tools.gateway import ToolGateway

    gw = ToolGateway.from_manifest(_MANIFEST)
    call = ToolCall(
        task_id="task-live-bitscale",
        tenant_id="tenant-live",
        tool_name="bitscale_list_grids",
        category=ToolCategory.READ,
        approval_required=False,
        parameters={},
        requester_id="req-live",
    )

    result = gw.execute(call, resolver=EnvCredentialResolver())

    # NOT the deterministic stub — a real (credit-free) read ran.
    assert result.get("stub") is not True, f"got stub, expected a real call: {result!r}"

    schema = json.loads((_SCHEMA_DIR / "bitscale_list_grids.output.schema.json").read_text())
    from jsonschema import Draft202012Validator

    Draft202012Validator(schema).validate(result)
    assert "grids" in result


def test_bitscale_get_workspace_real_call_through_gateway():
    """A real Bitscale get-workspace (credit-free) runs through the gateway and returns a
    NON-stub, schema-conforming dict. Skips without the key."""
    if not _key_present():
        pytest.skip("BITSCALE_API_KEY not set; live Bitscale get-workspace skipped")

    from agent_mesh.contracts.enums import ToolCategory
    from agent_mesh.contracts.models import ToolCall
    from agent_mesh.tools.credentials import EnvCredentialResolver
    from agent_mesh.tools.gateway import ToolGateway

    gw = ToolGateway.from_manifest(_MANIFEST)
    call = ToolCall(
        task_id="task-live-bitscale-ws",
        tenant_id="tenant-live",
        tool_name="bitscale_get_workspace",
        category=ToolCategory.READ,
        approval_required=False,
        parameters={},
        requester_id="req-live",
    )

    result = gw.execute(call, resolver=EnvCredentialResolver())

    assert result.get("stub") is not True, f"got stub, expected a real call: {result!r}"

    schema = json.loads((_SCHEMA_DIR / "bitscale_get_workspace.output.schema.json").read_text())
    from jsonschema import Draft202012Validator

    Draft202012Validator(schema).validate(result)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-m", "live", "-v"]))
