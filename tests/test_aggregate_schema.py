"""Runtime aggregate-schema fetch + cache tests (04-08 Task 1, default lane).

Creds-free and SDK-free: a fake Composio session whose ``.tools()`` returns a tool
def carrying an input JSON Schema proves the fetch + the fetch-once cache; a
Nango-style spec proves the permissive ``None`` seam (D-04). The module imports
WITHOUT the composio SDK installed (the SDK is never imported in the module).
"""

from __future__ import annotations

import pytest

from agent_mesh.contracts.enums import ToolCategory
from agent_mesh.tools import aggregate_schema
from agent_mesh.tools.gateway import ToolSpec


@pytest.fixture(autouse=True)
def _isolated_schema_cache():
    """The cache is module-global (process-lived); snapshot/restore per test so a
    cached ``None`` from one case never masks a positive fetch in another."""
    saved = dict(aggregate_schema._SCHEMA_CACHE)
    aggregate_schema._SCHEMA_CACHE.clear()
    try:
        yield
    finally:
        aggregate_schema._SCHEMA_CACHE.clear()
        aggregate_schema._SCHEMA_CACHE.update(saved)


def _spec(name: str, *, provider: str, integration_style: str) -> ToolSpec:
    return ToolSpec(
        name=name,
        provider=provider,
        category=ToolCategory.READ,
        description="",
        approval_required=False,
        credential_secret_name=None,
        resource_bindings={},
        integration_style=integration_style,
    )


class _FakeSession:
    """A stand-in Composio session: ``.tools()`` returns tool defs and counts calls."""

    def __init__(self, tool_defs):
        self._tool_defs = tool_defs
        self.tools_call_count = 0

    def tools(self):
        self.tools_call_count += 1
        return self._tool_defs


_INPUT_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}


def test_composio_fetch_returns_input_schema():
    spec = _spec(
        "composio_search", provider="composio_gmail", integration_style="composio_aggregator"
    )
    session = _FakeSession([{"name": "composio_search", "input_parameters": _INPUT_SCHEMA}])

    got = aggregate_schema.fetch_runtime_schema(spec, session=session)

    assert got == _INPUT_SCHEMA
    assert session.tools_call_count == 1


def test_composio_fetch_is_cached_does_not_requery():
    """The cache prevents a second ``session.tools()`` call (fetch-once)."""
    spec = _spec(
        "composio_search", provider="composio_gmail", integration_style="composio_aggregator"
    )
    session = _FakeSession([{"slug": "composio_search", "inputSchema": _INPUT_SCHEMA}])

    first = aggregate_schema.fetch_runtime_schema(spec, session=session)
    second = aggregate_schema.fetch_runtime_schema(spec, session=session)

    assert first == _INPUT_SCHEMA
    assert second == _INPUT_SCHEMA
    assert session.tools_call_count == 1, "second fetch must hit the cache, not re-query"


def test_nango_style_returns_none_without_raising():
    """A Nango-style spec has no per-tool runtime schema -> permissive None (D-04)."""
    spec = _spec(
        "nango_contacts_list", provider="xero", integration_style="nango_aggregator"
    )
    # No session at all — must not raise.
    assert aggregate_schema.fetch_runtime_schema(spec) is None
    # A session passed by mistake is ignored for non-Composio styles.
    session = _FakeSession([{"name": "nango_contacts_list", "input_parameters": _INPUT_SCHEMA}])
    assert aggregate_schema.fetch_runtime_schema(spec, session=session) is None


def test_composio_tool_not_found_caches_none():
    spec = _spec(
        "missing_tool", provider="composio_gmail", integration_style="composio_aggregator"
    )
    session = _FakeSession([{"name": "some_other_tool", "input_parameters": _INPUT_SCHEMA}])

    assert aggregate_schema.fetch_runtime_schema(spec, session=session) is None
    # Cached None: a re-fetch does not re-query.
    aggregate_schema.fetch_runtime_schema(spec, session=session)
    assert session.tools_call_count == 1


def test_module_imports_without_composio_sdk():
    """The module must be import-safe with NO composio SDK (lazy / never-imported)."""
    import sys

    assert "composio" not in sys.modules, "aggregate_schema must not import the composio SDK"
