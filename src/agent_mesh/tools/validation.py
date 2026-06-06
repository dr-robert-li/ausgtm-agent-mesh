"""JSON-Schema validation boundary for the Tool Gateway (TOOL-02).

A standalone, importable module the execution engine (04-03) calls input-pre-call
and output-post-call. It encodes three locked decisions exactly:

- **D-04 source-by-style fail-closed.** Direct tools validate against OUR
  manifest-declared schemas; aggregate tools validate against a runtime provider
  schema the caller supplies. Fail-closed applies to DIRECT tools ONLY — a direct
  tool with no schema is BLOCKED; an aggregate tool with no runtime schema is
  NEVER blocked (its schema arrives at runtime, absence is permissive).
- **D-05 permissive-by-design.** The validator faithfully applies whatever the
  schema declares (``additionalProperties``, enums, bounds). Gate width is the
  schema author's choice, not the validator's.
- **D-06 asymmetric failure.** An input violation raises ``InputSchemaViolation``
  (the caller makes NO SaaS call and records a failed ``tool_call``); an output
  violation returns a non-empty list of messages (the caller quarantines — the
  SaaS call already ran, so this is "ran but untrusted", not "never ran").

``jsonschema`` is a core dependency (promoted in 04-01); the schema boundary must
never be an optional import, so ``Draft202012Validator`` is imported at module
top. The validator is intentionally creds-free and deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


class SchemaError(Exception):
    """Base class for schema-boundary failures."""


class InputSchemaViolation(SchemaError):
    """Input failed validation -> hard reject, no SaaS call (D-06)."""


class OutputSchemaViolation(SchemaError):
    """Output failed validation -> quarantine + record, halt trust (D-06).

    ``validate_output`` itself returns messages rather than raising (the call
    already ran); this type exists for callers that prefer to raise on a
    non-empty quarantine list.
    """


def _load(ref: str) -> dict:
    """Read and JSON-parse a schema file path."""
    return json.loads(Path(ref).read_text())


def validate_input(schema: dict | None, params: dict) -> None:
    """Validate ``params`` against ``schema``; raise on any violation (D-06).

    A ``None`` schema raises — the *caller* decides whether a missing schema is
    "blocked" (direct, D-04) or "skip, runtime schema arrives later" (aggregate).
    Use :func:`validate_tool_input` for the style-aware dispatch.
    """
    if schema is None:
        raise InputSchemaViolation("no input schema declared")
    errs = sorted(
        Draft202012Validator(schema).iter_errors(params),
        key=lambda e: list(e.path),
    )
    if errs:
        raise InputSchemaViolation("; ".join(e.message for e in errs))


def validate_output(schema: dict | None, result: dict) -> list[str]:
    """Validate ``result`` against ``schema``; return error messages (D-06).

    Returns ``[]`` when the result conforms (or when ``schema`` is None —
    permissive: nothing to check). Never raises on a content violation: the SaaS
    call already ran, so the caller quarantines rather than aborting.
    """
    if schema is None:
        return []
    return [e.message for e in Draft202012Validator(schema).iter_errors(result)]


def validate_tool_input(
    *,
    integration_style: str,
    input_schema_ref: str | None,
    runtime_schema: dict | None,
    params: dict,
) -> None:
    """D-04 fail-closed dispatch (the nuance — do NOT generalize).

    - ``direct_api`` with ``input_schema_ref is None``  -> raise (BLOCK).
    - ``direct_api`` with a ref -> load the on-disk schema and validate.
    - any non-``direct_api`` style (composio_aggregator / nango_aggregator /
      aggregate_mcp / mcp_server) -> validate against ``runtime_schema`` when
      supplied; when it is None, return cleanly (NEVER block).

    ``input_schema_ref`` must be resolvable from the caller's CWD (or absolute);
    the engine (04-03) is responsible for passing a CWD-resolvable/absolute path
    from the manifest, since ``_load`` reads it directly.
    """
    if integration_style == "direct_api":
        if input_schema_ref is None:
            raise InputSchemaViolation(
                "direct tool with no schema is BLOCKED (D-04 fail-closed)"
            )
        validate_input(_load(input_schema_ref), params)
        return

    # Aggregate styles: schema arrives at runtime; absence is permissive (D-04).
    if runtime_schema is not None:
        validate_input(runtime_schema, params)
    return None
