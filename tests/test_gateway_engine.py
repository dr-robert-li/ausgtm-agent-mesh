"""Tool Gateway execution-engine tests (04-03).

Task 1 — ToolSpec D-03 fields, EnvCredentialResolver (D-02), and the lazy-import
adapter registry with ``adapter_key_for`` dispatch-key derivation (the parallel-
adapter seam three Wave-4 plans build against).

Task 2 — the real ``execute(call)`` engine: cred-only-in-execute (no leak),
stub degradation (D-11), live adapter reached for BOTH lanes (SC-1/SC-3),
input-reject hard-stop (D-06).

Creds-free and deterministic: no provider SDKs installed, no network.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from agent_mesh.contracts.enums import ToolCategory
from agent_mesh.contracts.models import ToolCall

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "manifests" / "tool_pack_manifest.yaml"


# ---------------------------------------------------------------------------
# Registry isolation — _REGISTRY is module-global; snapshot/restore per test so
# registrations (and lazy imports) never leak across tests (advisor trap #2).
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolated_registry():
    from agent_mesh.tools import adapters

    saved = dict(adapters._REGISTRY)
    adapters._REGISTRY.clear()
    try:
        yield
    finally:
        adapters._REGISTRY.clear()
        adapters._REGISTRY.update(saved)


def _spec(name: str):
    """Resolve a ToolSpec by name from the real manifest."""
    from agent_mesh.tools.gateway import load_tool_pack

    return next(s for s in load_tool_pack(MANIFEST) if s.name == name)


# ===========================================================================
# Task 1
# ===========================================================================
def test_load_tool_pack_surfaces_d03_fields():
    """The loader must populate integration_style + input/output_schema_ref
    (D-03 — fields the stub loader silently dropped)."""
    spec = _spec("hubspot_lookup_company")
    assert spec.integration_style == "direct_api"
    assert spec.input_schema_ref == "schemas/hubspot_lookup_company.input.schema.json"
    assert spec.output_schema_ref == "schemas/hubspot_lookup_company.output.schema.json"


def test_env_credential_resolver_resolves_by_name(monkeypatch):
    from agent_mesh.tools.credentials import EnvCredentialResolver

    r = EnvCredentialResolver()
    monkeypatch.setenv("HUBSPOT_PRIVATE_APP_TOKEN", "tok-123")
    assert r.resolve("HUBSPOT_PRIVATE_APP_TOKEN") == "tok-123"


def test_env_credential_resolver_returns_none_when_unset(monkeypatch):
    """None when absent — the stub-degradation precondition (D-11)."""
    from agent_mesh.tools.credentials import EnvCredentialResolver

    r = EnvCredentialResolver()
    monkeypatch.delenv("HUBSPOT_PRIVATE_APP_TOKEN", raising=False)
    assert r.resolve("HUBSPOT_PRIVATE_APP_TOKEN") is None
    assert r.resolve(None) is None


def test_registry_register_and_get():
    from agent_mesh.tools.adapters import get_adapter, register

    def fake(spec, params, *, credential=None):
        return {"ok": True}

    register("hubspot", fake)
    assert get_adapter("hubspot") is fake


def test_get_adapter_bogus_returns_none_without_raising():
    """Registry-miss + import-miss swallows ImportError -> None (D-11)."""
    from agent_mesh.tools.adapters import get_adapter

    assert get_adapter("definitely_not_a_real_adapter_xyz") is None


def test_get_adapter_lazy_imports_on_miss(tmp_path, monkeypatch):
    """The blocker fix: a module that calls register() at import time is loaded
    on the first get_adapter() lookup, EVEN THOUGH no test imported it first.

    A synthetic throwaway probe is written here (not "hubspot") because the real
    adapter modules land in wave 4 (04-05/06/08) and do not exist at this wave-3
    plan; real-module import-on-miss is asserted there.
    """
    from agent_mesh.tools import adapters as adapters_pkg
    from agent_mesh.tools.adapters import get_adapter

    pkg_dir = Path(adapters_pkg.__file__).parent
    probe = pkg_dir / "_lazy_probe.py"
    mod_name = "agent_mesh.tools.adapters._lazy_probe"
    probe.write_text(
        "from agent_mesh.tools.adapters import register\n"
        "def _probe(spec, params, *, credential=None):\n"
        "    return {'probe': True}\n"
        "register('_lazy_probe', _probe)\n"
    )
    try:
        assert "_lazy_probe" not in adapters_pkg._REGISTRY  # not yet loaded
        assert mod_name not in sys.modules  # nobody imported it
        fn = get_adapter("_lazy_probe")  # import-on-miss fires register()
        assert callable(fn)
        assert fn(None, {})["probe"] is True
    finally:
        probe.unlink(missing_ok=True)
        sys.modules.pop(mod_name, None)


def test_adapter_key_for_derives_dispatch_key():
    """direct -> provider; composio_aggregator -> 'composio'; nango -> 'nango'."""
    from agent_mesh.tools.adapters import adapter_key_for

    assert adapter_key_for(_spec("hubspot_lookup_company")) == "hubspot"

    # Synthetic aggregator specs (the manifest's aggregator entries vary by
    # deployment; assert the derivation rule directly).
    from agent_mesh.tools.gateway import ToolSpec

    composio_spec = ToolSpec(
        name="x",
        provider="some_provider",
        category=ToolCategory.READ,
        description="",
        approval_required=False,
        credential_secret_name=None,
        resource_bindings={},
        integration_style="composio_aggregator",
        input_schema_ref=None,
        output_schema_ref=None,
    )
    nango_spec = ToolSpec(
        name="y",
        provider="some_provider",
        category=ToolCategory.READ,
        description="",
        approval_required=False,
        credential_secret_name=None,
        resource_bindings={},
        integration_style="nango_aggregator",
        input_schema_ref=None,
        output_schema_ref=None,
    )
    assert adapter_key_for(composio_spec) == "composio"
    assert adapter_key_for(nango_spec) == "nango"


def test_toolspec_validate_invariant_unchanged():
    """A write-class tool with approval_required=false still raises (unchanged)."""
    from agent_mesh.tools.gateway import ToolSpec

    bad = ToolSpec(
        name="bad_write",
        provider="p",
        category=ToolCategory.WRITE,
        description="",
        approval_required=False,
        credential_secret_name=None,
        resource_bindings={},
        integration_style="direct_api",
        input_schema_ref=None,
        output_schema_ref=None,
    )
    with pytest.raises(ValueError):
        bad.validate()


# ===========================================================================
# Task 2 — real execute(call) engine
# ===========================================================================
SENTINEL_CRED = "SENTINEL-SECRET-DO-NOT-LEAK-abc123"


class _SpyResolver:
    """Records every resolve() call and returns a fixed value per name."""

    def __init__(self, values: dict[str, str | None]):
        self.values = values
        self.calls: list[str | None] = []

    def resolve(self, secret_name):
        self.calls.append(secret_name)
        return self.values.get(secret_name)


def _gateway():
    from agent_mesh.tools.gateway import ToolGateway

    return ToolGateway.from_manifest(MANIFEST)


def _call(tool_name: str, parameters: dict, category=ToolCategory.READ):
    return ToolCall(
        task_id="task-1",
        tenant_id="tenant-1",
        tool_name=tool_name,
        category=category,
        approval_required=False,
        parameters=parameters,
        requester_id="req-1",
    )


def test_credential_resolved_only_in_execute_and_never_leaks():
    """D-02: resolver is called inside execute; the secret never appears in the
    returned dict (no credential leakage)."""
    gw = _gateway()
    resolver = _SpyResolver({"HUBSPOT_PRIVATE_APP_TOKEN": SENTINEL_CRED})
    call = _call("hubspot_lookup_company", {"object_type": "companies", "query": "Acme"})

    result = gw.execute(call, resolver=resolver)

    assert resolver.calls == ["HUBSPOT_PRIVATE_APP_TOKEN"]
    assert SENTINEL_CRED not in repr(result)


def test_stub_degradation_when_credential_absent():
    """D-11: a direct tool whose credential resolves to None returns the stub dict
    shape and makes no adapter call."""
    from agent_mesh.tools import adapters

    gw = _gateway()
    resolver = _SpyResolver({"HUBSPOT_PRIVATE_APP_TOKEN": None})
    call = _call("hubspot_lookup_company", {"object_type": "companies", "query": "Acme"})

    called = []

    def fake(spec, params, *, credential=None):
        called.append(True)
        return {"unexpected": True}

    adapters.register("hubspot", fake)
    result = gw.execute(call, resolver=resolver)

    assert called == []  # adapter never reached
    assert result.get("stub") is True
    assert result["tool"] == "hubspot_lookup_company"
    assert result["echo_parameters"] == {"object_type": "companies", "query": "Acme"}


def test_adapter_reached_direct_lane():
    """SC-1: a direct tool with a registered adapter AND a resolved credential
    dispatches to the adapter (NOT the stub)."""
    from agent_mesh.tools import adapters

    gw = _gateway()
    resolver = _SpyResolver({"HUBSPOT_PRIVATE_APP_TOKEN": SENTINEL_CRED})
    call = _call("hubspot_lookup_company", {"object_type": "companies", "query": "Acme"})

    seen = {}

    def fake(spec, params, *, credential=None):
        seen["credential"] = credential
        # schema-valid output (records[].id) so this exercises the live-call path,
        # not the output-quarantine branch.
        return {"records": [{"id": "123", "properties": {"name": "Acme Inc"}}]}

    adapters.register("hubspot", fake)
    result = gw.execute(call, resolver=resolver)

    assert result.get("stub") is not True
    assert result["records"][0]["id"] == "123"
    # credential reached the adapter but is NOT echoed back to the caller
    assert seen["credential"] == SENTINEL_CRED
    assert SENTINEL_CRED not in repr(result)


def test_adapter_reached_aggregator_lane():
    """SC-3: an aggregator spec (composio_aggregator -> key 'composio') with a
    registered fake adapter + a credential reaches the adapter."""
    from agent_mesh.tools import adapters
    from agent_mesh.tools.gateway import ToolGateway, ToolSpec

    spec = ToolSpec(
        name="agg_search",
        provider="some_saas",
        category=ToolCategory.READ,
        description="",
        approval_required=False,
        credential_secret_name="COMPOSIO_API_KEY",
        resource_bindings={},
        integration_style="composio_aggregator",
        input_schema_ref=None,
        output_schema_ref=None,
    )
    gw = ToolGateway([spec])
    resolver = _SpyResolver({"COMPOSIO_API_KEY": SENTINEL_CRED})
    call = _call("agg_search", {"q": "x"})

    reached = []

    def fake(spec, params, *, credential=None):
        reached.append(True)
        return {"results": []}

    adapters.register("composio", fake)
    result = gw.execute(call, resolver=resolver)

    assert reached == [True]
    assert result.get("stub") is not True
    assert result == {"results": []}


def test_input_reject_makes_no_adapter_call(monkeypatch):
    """D-06: a schema-invalid input to a direct tool does NOT call the adapter and
    records schema_validation == 'input_rejected'."""
    from agent_mesh.tools import adapters

    gw = _gateway()
    resolver = _SpyResolver({"HUBSPOT_PRIVATE_APP_TOKEN": SENTINEL_CRED})
    # hubspot_lookup_company requires 'query'; omit it -> input violation.
    call = _call("hubspot_lookup_company", {"wrong_field": "x"})

    called = []

    def fake(spec, params, *, credential=None):
        called.append(True)
        return {}

    adapters.register("hubspot", fake)
    result = gw.execute(call, resolver=resolver)

    assert called == []
    assert call.schema_validation == "input_rejected"
    assert result.get("outcome") == "input_rejected"


def test_execute_resolves_schema_ref_from_non_repo_root_cwd(tmp_path, monkeypatch):
    """The 04-02 handoff: manifest schema refs are repo-root-relative but the
    production CWD (Cloud Run Job) is NOT the repo root. execute() must anchor the
    ref against the gateway base_dir so validation._load() finds the schema and the
    no-cred stub path does NOT crash with FileNotFoundError (D-11)."""
    gw = _gateway()  # from_manifest -> base_dir anchored at the manifest's parent
    monkeypatch.chdir(tmp_path)  # CWD where "schemas/..." does NOT resolve
    call = _call("hubspot_lookup_company", {"object_type": "companies", "query": "Acme"})

    # No resolver -> credential None -> stub. The bug would FileNotFoundError in the
    # input-validation step BEFORE reaching the stub fallback.
    result = gw.execute(call)
    assert result.get("stub") is True
    assert call.schema_validation == "ok"
