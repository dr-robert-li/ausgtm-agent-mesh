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
