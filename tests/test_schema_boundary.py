"""Schema-boundary tests for the Tool Gateway validator (TOOL-02).

Exercises the three locked decisions against tools that DO declare schemas
(Pitfall 5 — the reject test must target a schema-declaring tool, never a
schema-less one):

- D-04 source-by-style fail-closed: a *direct* tool with no schema is BLOCKED;
  an *aggregate* tool with no runtime schema is NEVER blocked.
- D-05 permissive-by-design: the validator faithfully applies whatever the
  on-disk schema declares (required / enum / additionalProperties:false).
- D-06 asymmetric failure: an input violation raises ``InputSchemaViolation``
  (no SaaS call); an output violation returns quarantine messages (the call
  already ran).

Creds-free and deterministic — runs in the default ("not live") lane.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_mesh.tools.validation import (
    InputSchemaViolation,
    OutputSchemaViolation,
    SchemaError,
    validate_input,
    validate_output,
    validate_tool_input,
)

_SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"
_HUBSPOT_INPUT = _SCHEMAS / "hubspot_lookup_company.input.schema.json"
_GMAIL_OUTPUT = _SCHEMAS / "gmail_send.output.schema.json"


def _load(name: Path) -> dict:
    return json.loads(name.read_text())


# --- D-06 input: a schema-declaring tool rejects bad input (Pitfall 5) -------


def test_input_reject_missing_required_field_raises():
    """hubspot_lookup_company requires both object_type AND query; omitting
    query is a hard reject naming the missing field (D-06 input violation)."""
    schema = _load(_HUBSPOT_INPUT)
    with pytest.raises(InputSchemaViolation) as exc:
        validate_input(schema, {"object_type": "companies"})
    assert "query" in str(exc.value)


def test_input_ok_conforming_payload_passes():
    """A conforming payload returns None and does not raise."""
    schema = _load(_HUBSPOT_INPUT)
    assert validate_input(schema, {"object_type": "companies", "query": "acme"}) is None


# --- D-04 fail-closed dispatch: direct BLOCKS, aggregate is PERMISSIVE -------


def test_direct_no_schema_is_blocked():
    """D-04: a direct_api tool with input_schema_ref=None is BLOCKED."""
    with pytest.raises(InputSchemaViolation):
        validate_tool_input(
            integration_style="direct_api",
            input_schema_ref=None,
            runtime_schema=None,
            params={"anything": 1},
        )


def test_direct_with_ref_validates_against_disk_schema():
    """D-04: a direct tool WITH a ref validates against the on-disk schema —
    a bad payload is still rejected (proves the ref is loaded, not skipped)."""
    with pytest.raises(InputSchemaViolation):
        validate_tool_input(
            integration_style="direct_api",
            input_schema_ref=str(_HUBSPOT_INPUT),
            runtime_schema=None,
            params={"object_type": "companies"},  # missing required "query"
        )


def test_aggregate_no_runtime_schema_is_permissive():
    """D-04: an aggregate (composio) tool with no runtime schema is NEVER
    blocked — returns cleanly even with an otherwise-invalid-looking payload."""
    assert (
        validate_tool_input(
            integration_style="composio_aggregator",
            input_schema_ref=None,
            runtime_schema=None,
            params={"whatever": True},
        )
        is None
    )


def test_aggregate_with_runtime_schema_is_validated():
    """When an aggregate tool DOES supply a runtime schema, it is enforced."""
    runtime = _load(_HUBSPOT_INPUT)
    with pytest.raises(InputSchemaViolation):
        validate_tool_input(
            integration_style="nango_aggregator",
            input_schema_ref=None,
            runtime_schema=runtime,
            params={"object_type": "companies"},  # missing required "query"
        )


# --- D-06 output: quarantine messages, never a raise from validate_output ----


def test_output_violation_returns_quarantine_messages():
    """gmail_send.output requires message_id; a result lacking it returns a
    non-empty list of error messages (caller quarantines) — and does NOT
    raise (the SaaS call already ran)."""
    schema = _load(_GMAIL_OUTPUT)
    msgs = validate_output(schema, {"thread_id": "t-1"})
    assert isinstance(msgs, list)
    assert msgs  # non-empty == quarantine
    assert any("message_id" in m for m in msgs)


def test_output_conforming_result_returns_empty():
    """A conforming output returns [] (valid, nothing to quarantine)."""
    schema = _load(_GMAIL_OUTPUT)
    assert validate_output(schema, {"message_id": "m-1", "thread_id": "t-1"}) == []


def test_output_no_schema_is_permissive():
    """D-04/05: validate_output with schema=None returns [] (permissive)."""
    assert validate_output(None, {"anything": "goes"}) == []


# --- exception hierarchy -----------------------------------------------------


def test_exception_hierarchy():
    assert issubclass(InputSchemaViolation, SchemaError)
    assert issubclass(OutputSchemaViolation, SchemaError)
