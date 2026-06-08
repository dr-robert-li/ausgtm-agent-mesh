"""LOCAL-04 config-validation guard for the local inference lane profiles.

Mirrors ``tests/test_d06_chokepoint.py``'s config-load pattern but INVERTS its
api_base assertion: the cloud chokepoint test asserts every route egresses
through the CF wrapper indirection; here we assert every route's api_base is a
LOOPBACK URL carrying NO cloud markers — the egress-free, on-box posture of the
vLLM / Ollama profiles authored in Plan 01.

Default lane (D-09): creds-free, NO network. ``build_router`` constructs the
in-process ``litellm.Router`` lazily — it loads ``model_list`` into memory and
makes no provider call (Pitfall 6, verified against installed litellm 1.83.7) —
so this runs with no egress and no skip (matching the non-skipping router test).

What this test does NOT do: it cannot catch a wrong api_base *path* (the
``/v1`` vs no-``/v1`` runtime trap, Pitfall 1) — an offline build succeeds with
any api_base string. That correctness lives in the config value + RUNBOOK. The
full no-cloud-env-ref sweep over the whole profile file is Plan 01's grep
acceptance + Phase 11's job; this guard is scoped to the four LOCAL-04 contracts.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
_PROFILES = {
    "vllm": _REPO / "config" / "model_gateway.vllm.yaml",
    "ollama": _REPO / "config" / "model_gateway.ollama.yaml",
}
# Exact deployment names the Router resolves by (TIER_TO_DEPLOYMENT). A drifted
# name 404s the Router at call time and the stubbed Router test cannot catch it
# (Pitfall 3), so the names are asserted explicitly here.
_NAMES = {"low-complexity", "medium-complexity", "high-complexity"}
_LOOPBACK = ("http://localhost", "http://127.0.0.1")
# Cloud markers that must NOT appear in a local profile's api_base (Phase-11
# no-egress-friendly negative guard; the INVERTED assertion vs test_d06_chokepoint).
_CLOUD_MARKERS = (
    "os.environ/CF_AIG_WRAPPER_URL",
    "vertex_ai",
    "anthropic",
    "googleapis.com",
    "anthropic.com",
)


@pytest.mark.parametrize("name", list(_PROFILES))
def test_profile_has_three_exact_deployment_names(name):
    cfg = yaml.safe_load(_PROFILES[name].read_text())
    got = {r["model_name"] for r in cfg["model_list"]}
    assert _NAMES <= got, f"{name}: missing exact deployment names; has {got}"


@pytest.mark.parametrize("name", list(_PROFILES))
def test_every_route_api_base_is_loopback(name):
    cfg = yaml.safe_load(_PROFILES[name].read_text())
    for r in cfg["model_list"]:
        ab = r["litellm_params"]["api_base"]
        assert ab.startswith(_LOOPBACK), (
            f"{name}/{r['model_name']}: api_base {ab!r} not loopback"
        )
        assert not any(m in ab for m in _CLOUD_MARKERS), (
            f"{name}/{r['model_name']}: cloud marker in api_base {ab!r}"
        )


@pytest.mark.parametrize("name", list(_PROFILES))
def test_no_cloud_named_route(name):
    """D-06: the cloud-only ``high-complexity-vertex`` route is dropped locally."""
    cfg = yaml.safe_load(_PROFILES[name].read_text())
    got = {r["model_name"] for r in cfg["model_list"]}
    assert "high-complexity-vertex" not in got, (
        f"{name}: cloud route 'high-complexity-vertex' leaked into local profile"
    )


@pytest.mark.parametrize("name", list(_PROFILES))
def test_build_router_constructs_with_no_network(name):
    """``build_router`` builds a real ``litellm.Router`` OFFLINE from the profile
    file (Pitfall 6 — construction is lazy, no provider call) and its model_list
    covers the three exact deployment names."""
    from litellm import Router

    from agent_mesh.worker.model_gateway import build_router

    router = build_router(str(_PROFILES[name]))
    assert isinstance(router, Router)
    assert {d["model_name"] for d in router.model_list} >= _NAMES


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
