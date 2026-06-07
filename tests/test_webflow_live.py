"""Webflow live lane (05-02, TOOL-03, D-07) — OPT-IN.

The whole module is ``@pytest.mark.live`` (deselected without ``-m live``) and SKIPS
inline when ``WEBFLOW_API_TOKEN`` is unset — so ``make test`` never reaches Webflow and
stays creds-free. (Gates on the Webflow token directly, NOT the shared model/gateway
``live_creds`` axis — a different credential.)

Proves the direct_api integration style end-to-end on a REAL provider: a real
``webflow_list_cms_items`` flows through ``gateway.execute(call, resolver=
EnvCredentialResolver())`` with the token resolved only at execution time (D-02), and
the result is a non-stub, output-schema-conforming dict.

Scope: list-only (the read). ``webflow_create_cms_item`` (the approval-gated publishing
write) is a draft mutation requiring the worker approval flow; its mapping (and the
forced ``isDraft: true``) is proven in the default-lane unit test instead, mirroring
HubSpot's lookup-only live lane.

NB (operator): the live lane also needs REAL ``resource_bindings`` (``site_id`` /
``collection_id``), not just the env key — a placeholder binding (e.g.
``REPLACE_WITH_COLLECTION_ID``) errors the live call instead of skipping it. Set both
before running this lane (see docs/credentials/webflow.md).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.live  # whole module is opt-in live lane

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"
_MANIFEST = Path(__file__).resolve().parents[1] / "manifests" / "tool_pack_manifest.yaml"


def _token_present() -> bool:
    return bool(os.getenv("WEBFLOW_API_TOKEN"))


def test_webflow_list_cms_items_real_call_through_gateway():
    """A real Webflow list runs through the gateway (token resolved at call time),
    returns a NON-stub result conforming to the output schema. Skips without the token."""
    if not _token_present():
        pytest.skip("WEBFLOW_API_TOKEN not set; live Webflow list skipped")

    from agent_mesh.contracts.enums import ToolCategory
    from agent_mesh.contracts.models import ToolCall
    from agent_mesh.tools.credentials import EnvCredentialResolver
    from agent_mesh.tools.gateway import ToolGateway

    gw = ToolGateway.from_manifest(_MANIFEST)
    call = ToolCall(
        task_id="task-live-webflow",
        tenant_id="tenant-live",
        tool_name="webflow_list_cms_items",
        category=ToolCategory.READ,
        approval_required=False,
        parameters={"limit": 1},
        requester_id="req-live",
    )

    result = gw.execute(call, resolver=EnvCredentialResolver())

    # NOT the deterministic stub — a real adapter call ran.
    assert result.get("stub") is not True, f"got stub, expected a real call: {result!r}"

    # Conforms to the output schema.
    schema = json.loads(
        (_SCHEMA_DIR / "webflow_list_cms_items.output.schema.json").read_text()
    )
    from jsonschema import Draft202012Validator

    Draft202012Validator(schema).validate(result)
    assert "items" in result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-m", "live", "-v"]))
