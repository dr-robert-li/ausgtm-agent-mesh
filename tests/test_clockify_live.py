"""Clockify live lane (05-05, TOOL-03, D-02) — OPT-IN, READ-ONLY.

The whole module is ``@pytest.mark.live`` (deselected without ``-m live``) and SKIPS
inline when ``CLOCKIFY_API_KEY`` is unset — so ``make test`` never reaches Clockify and
stays creds-free. NOTE: this gates on the Clockify key directly (NOT the shared
``live_creds`` fixture, which gates on model/gateway creds — a different credential
axis, see 04-PATTERNS).

Proves the direct_api integration style end-to-end on a REAL provider: a real
``clockify_read_time_entries`` flows through ``gateway.execute(call, resolver=
EnvCredentialResolver())`` with the key resolved only at execution time (D-02) and
authenticated via the ``X-Api-Key`` header. The result is a non-stub,
output-schema-conforming ``{"entries":[...]}`` dict.

OPERATOR NOTE: the live lane ALSO needs REAL ``resource_bindings`` (``workspace_id`` /
``user_id``) in the manifest — live reads skip on a missing key but NOT on placeholder
bindings (e.g. ``REPLACE_WITH_CLOCKIFY_WORKSPACE_ID``), so a placeholder binding ERRORS
the live call (404/raise) instead of skipping it. See docs/credentials/clockify.md.
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
    return bool(os.getenv("CLOCKIFY_API_KEY"))


def test_clockify_read_time_entries_real_call_through_gateway():
    """A real Clockify read runs through the gateway (key resolved at call time via
    X-Api-Key), returns a NON-stub result conforming to the output schema. Skips
    without the key."""
    if not _key_present():
        pytest.skip("CLOCKIFY_API_KEY not set; live Clockify read skipped")

    from agent_mesh.contracts.enums import ToolCategory
    from agent_mesh.contracts.models import ToolCall
    from agent_mesh.tools.credentials import EnvCredentialResolver
    from agent_mesh.tools.gateway import ToolGateway

    gw = ToolGateway.from_manifest(_MANIFEST)
    call = ToolCall(
        task_id="task-live-clockify",
        tenant_id="tenant-live",
        tool_name="clockify_read_time_entries",
        category=ToolCategory.READ,
        approval_required=False,
        parameters={"page-size": 1},
        requester_id="req-live",
    )

    result = gw.execute(call, resolver=EnvCredentialResolver())

    # NOT the deterministic stub — a real adapter call ran.
    assert result.get("stub") is not True, f"got stub, expected a real call: {result!r}"

    # Conforms to the output schema (object wrapping the entries array).
    schema = json.loads(
        (_SCHEMA_DIR / "clockify_read_time_entries.output.schema.json").read_text()
    )
    from jsonschema import Draft202012Validator

    Draft202012Validator(schema).validate(result)
    assert "entries" in result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-m", "live", "-v"]))
