"""HubSpot live lane (04-05, TOOL-01, D-07) — OPT-IN.

The whole module is ``@pytest.mark.live`` (deselected without ``-m live``) and SKIPS
inline when ``HUBSPOT_PRIVATE_APP_TOKEN`` is unset — so ``make test`` never reaches
HubSpot and never requires the SDK. NOTE: this gates on the HubSpot token directly
(NOT the shared ``live_creds`` fixture, which gates on model/gateway creds — a
different credential axis, see 04-PATTERNS).

Proves the direct_api integration style end-to-end on a REAL provider: a real
``hubspot_lookup_company`` flows through ``gateway.execute(call, resolver=
EnvCredentialResolver())`` with the token resolved only at execution time (D-02), and
the result is a non-stub, output-schema-conforming dict.

Scope: lookup-only (the read). ``hubspot_create_deal`` (the approval-gated write) is a
SANDBOX-only mutation requiring the worker approval flow + a real sandbox
``pipeline_id``; its mapping is proven in the default-lane unit test instead, and its
live execution is gated behind the existing approval ledger (unchanged here).
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
    return bool(os.getenv("HUBSPOT_PRIVATE_APP_TOKEN"))


def test_hubspot_lookup_company_real_call_through_gateway():
    """A real HubSpot lookup runs through the gateway (token resolved at call time),
    returns a NON-stub result conforming to the output schema. Skips without the token."""
    if not _token_present():
        pytest.skip("HUBSPOT_PRIVATE_APP_TOKEN not set; live HubSpot lookup skipped")

    from agent_mesh.contracts.enums import ToolCategory
    from agent_mesh.contracts.models import ToolCall
    from agent_mesh.tools.credentials import EnvCredentialResolver
    from agent_mesh.tools.gateway import ToolGateway

    gw = ToolGateway.from_manifest(_MANIFEST)
    call = ToolCall(
        task_id="task-live-hubspot",
        tenant_id="tenant-live",
        tool_name="hubspot_lookup_company",
        category=ToolCategory.READ,
        approval_required=False,
        parameters={"object_type": "companies", "query": "a", "limit": 1},
        requester_id="req-live",
    )

    result = gw.execute(call, resolver=EnvCredentialResolver())

    # NOT the deterministic stub — a real adapter call ran.
    assert result.get("stub") is not True, f"got stub, expected a real call: {result!r}"

    # Conforms to the strict output schema.
    schema = json.loads((_SCHEMA_DIR / "hubspot_lookup_company.output.schema.json").read_text())
    from jsonschema import Draft202012Validator

    Draft202012Validator(schema).validate(result)
    assert "records" in result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-m", "live", "-v"]))
