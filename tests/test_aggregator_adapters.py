"""Default-lane SC-3 registration guard for the aggregator adapters (04-08 Task 2).

The load-bearing assertion: ``composio.py`` registers under ``"composio"`` and
``nango.py`` under ``"nango"`` — the EXACT keys ``adapter_key_for`` produces for the
``composio_aggregator`` / ``nango_aggregator`` styles. If either registered under the
integration_style string instead, a creds-present call would silently fall to the stub
(SC-3 regression). This proves registration in the DEFAULT lane (no creds, no SDK
installed), not only the skipped live lane.

Bulletproofing (advisor): ``get_adapter`` does import-on-miss via
``importlib.import_module``, which is a NO-OP if the module is already in
``sys.modules`` — it does NOT re-run ``register()``. The autouse ``_isolated_registry``
fixture clears ``_REGISTRY`` per test, so a module imported earlier in the session would
leave the registry empty after the clear. So we force a true re-import
(``sys.modules.pop`` + ``importlib.import_module``) and assert registration directly.
The import succeeding WITHOUT the composio SDK installed is itself proof that
registration is SDK-free (the SDK import is lazy, inside the adapter fn).
"""

from __future__ import annotations

import importlib
import sys

import pytest

from agent_mesh.tools import adapters


@pytest.fixture(autouse=True)
def _isolated_registry():
    saved = dict(adapters._REGISTRY)
    adapters._REGISTRY.clear()
    try:
        yield
    finally:
        adapters._REGISTRY.clear()
        adapters._REGISTRY.update(saved)


def _force_reimport(module_name: str) -> None:
    sys.modules.pop(module_name, None)
    importlib.import_module(module_name)


def test_composio_registers_under_composio_key():
    _force_reimport("agent_mesh.tools.adapters.composio")
    assert callable(adapters._REGISTRY.get("composio")), (
        "composio.py must register under 'composio' (the adapter_key_for key), "
        "not 'composio_aggregator'"
    )
    assert "composio_aggregator" not in adapters._REGISTRY


def test_nango_registers_under_nango_key():
    _force_reimport("agent_mesh.tools.adapters.nango")
    assert callable(adapters._REGISTRY.get("nango")), (
        "nango.py must register under 'nango' (the adapter_key_for key), "
        "not 'nango_aggregator'"
    )
    assert "nango_aggregator" not in adapters._REGISTRY


def test_get_adapter_resolves_aggregator_keys_via_import_on_miss():
    """The runtime path: get_adapter('composio'/'nango') returns a callable via
    import-on-miss, with NO composio SDK installed (proves lazy SDK import)."""
    sys.modules.pop("agent_mesh.tools.adapters.composio", None)
    sys.modules.pop("agent_mesh.tools.adapters.nango", None)

    assert callable(adapters.get_adapter("composio"))
    assert callable(adapters.get_adapter("nango"))


def test_adapter_modules_import_without_composio_sdk():
    """Both adapter modules import cleanly with NO composio package present and the
    composio SDK is never imported at module load (lazy import discipline)."""
    _force_reimport("agent_mesh.tools.adapters.composio")
    _force_reimport("agent_mesh.tools.adapters.nango")
    assert "composio" not in sys.modules, "composio SDK must be lazy-imported, not at module top"


def test_nango_adapter_has_no_nango_package_import():
    """T-04-08-02: nango.py must not import any 'nango' package (httpx proxy only)."""
    src = (
        importlib.import_module("agent_mesh.tools.adapters.nango").__file__
    )
    text = open(src, encoding="utf-8").read()
    assert "import nango" not in text
    assert "from nango" not in text
    assert "proxy" in text  # the httpx proxy path is present
