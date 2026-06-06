"""Contract tests for the additive ToolCall fields landed in Phase 4 Plan 01.

Phase 4 wires real tool adapters, so the ToolCall record grew three additive
fields (audit item D): ``integration_style``, ``schema_validation`` (validation
outcome at the tool boundary), and ``is_read`` (read vs gated-write marker).
These are additive-only: ``extra="forbid"`` plus the contract-parity test forbid
a rewrite of the P1-era contract, so existing call sites that omit the fields
must keep working with backward-compatible defaults.
"""

import json
from pathlib import Path

from agent_mesh.contracts.models import ToolCall

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_call(**overrides) -> ToolCall:
    base = dict(
        task_id="task-1",
        tenant_id="tenant-1",
        tool_name="hubspot_lookup_company",
        category="read",
        approval_required=False,
        requester_id="user-1",
    )
    base.update(overrides)
    return ToolCall(**base)


def test_tool_call_carries_additive_fields_round_trip():
    call = _make_call(
        integration_style="direct_api",
        schema_validation="input_rejected",
        is_read=True,
    )
    dumped = call.model_dump()
    assert dumped["integration_style"] == "direct_api"
    assert dumped["schema_validation"] == "input_rejected"
    assert dumped["is_read"] is True

    # Re-construction from the dump must round-trip under extra="forbid".
    rebuilt = ToolCall(**dumped)
    assert rebuilt.integration_style == "direct_api"
    assert rebuilt.schema_validation == "input_rejected"
    assert rebuilt.is_read is True


def test_tool_call_defaults_are_backward_compatible():
    # Existing call sites that omit the new fields keep working unchanged.
    call = _make_call()
    assert call.integration_style is None
    assert call.schema_validation is None
    assert call.is_read is False


def test_tool_call_schema_regenerated_with_additive_fields():
    schema_path = _REPO_ROOT / "schemas" / "contracts" / "ToolCall.schema.json"
    schema = json.loads(schema_path.read_text())
    props = schema["properties"]
    assert "integration_style" in props
    assert "schema_validation" in props
    assert "is_read" in props
    # is_read is a non-null boolean with a False default (not optional/anyOf).
    assert props["is_read"].get("default") is False
