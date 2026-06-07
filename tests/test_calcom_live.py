"""Cal.com live lane (05-04, TOOL-03, D-07) — OPT-IN.

The whole module is ``@pytest.mark.live`` (deselected without ``-m live``) and SKIPS
inline when ``CALCOM_API_KEY`` is unset — so ``make test`` never reaches Cal.com and
stays creds-free. NOTE: this gates on the Cal.com key directly (NOT the shared
``live_creds`` fixture, which gates on model/gateway creds — a different credential axis).

Proves the direct_api integration style end-to-end on a REAL provider: a real
``calcom_list_bookings`` flows through ``gateway.execute(call, resolver=
EnvCredentialResolver())`` with the key resolved only at execution time (D-02), the
mandatory ``cal-api-version: 2026-05-01`` header is sent by the adapter, and the result
is a non-stub, output-schema-conforming dict.

Scope: list-only (the read). ``calcom_create_booking`` (the approval-gated write) is a
real mutation requiring the worker approval flow + a real ``event_type_id`` binding; its
mapping is proven in the default-lane unit test instead, and its live execution stays
gated behind the existing approval ledger (unchanged here).
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
    return bool(os.getenv("CALCOM_API_KEY"))


def test_calcom_list_bookings_real_call_through_gateway():
    """A real Cal.com list runs through the gateway (key resolved at call time), returns
    a NON-stub result conforming to the output schema. Skips without the key."""
    if not _key_present():
        pytest.skip("CALCOM_API_KEY not set; live Cal.com list-bookings skipped")

    from agent_mesh.contracts.enums import ToolCategory
    from agent_mesh.contracts.models import ToolCall
    from agent_mesh.tools.credentials import EnvCredentialResolver
    from agent_mesh.tools.gateway import ToolGateway

    gw = ToolGateway.from_manifest(_MANIFEST)
    call = ToolCall(
        task_id="task-live-calcom",
        tenant_id="tenant-live",
        tool_name="calcom_list_bookings",
        category=ToolCategory.READ,
        approval_required=False,
        parameters={},
        requester_id="req-live",
    )

    result = gw.execute(call, resolver=EnvCredentialResolver())

    # NOT the deterministic stub — a real adapter call ran.
    assert result.get("stub") is not True, f"got stub, expected a real call: {result!r}"

    # Conforms to the output schema.
    schema = json.loads((_SCHEMA_DIR / "calcom_list_bookings.output.schema.json").read_text())
    from jsonschema import Draft202012Validator

    Draft202012Validator(schema).validate(result)
    assert "data" in result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-m", "live", "-v"]))
