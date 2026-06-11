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
    # Phase 11 D-01: the P10 compose variants (service-DNS api_base, not loopback).
    "vllm-compose": _REPO / "config" / "model_gateway.vllm.compose.yaml",
    "cpu-compose": _REPO / "config" / "model_gateway.cpu.compose.yaml",
}
# Exact deployment names the Router resolves by (TIER_TO_DEPLOYMENT). A drifted
# name 404s the Router at call time and the stubbed Router test cannot catch it
# (Pitfall 3), so the names are asserted explicitly here.
_NAMES = {"low-complexity", "medium-complexity", "high-complexity"}
_LOOPBACK = ("http://localhost", "http://127.0.0.1")
# Phase 11 D-01: in-stack service-DNS is egress-free (the compose `vllm`/`ollama`
# sibling services), NOT required to be loopback. Allowlist it alongside loopback.
_SERVICE_DNS = ("http://vllm:8000", "http://ollama:11434")
_LOCAL_ALLOW = _LOOPBACK + _SERVICE_DNS
# Cloud markers that must NOT appear in a local profile's api_base (Phase-11
# no-egress-friendly negative guard; the INVERTED assertion vs test_d06_chokepoint).
_CLOUD_MARKERS = (
    "os.environ/CF_AIG_WRAPPER_URL",
    "vertex_ai",
    "anthropic",
    "googleapis.com",
    "anthropic.com",
)
# Phase 11 D-01 (whole-file cloud-LLM deny markers — the D-01 floor). Unlike
# _CLOUD_MARKERS (scoped to api_base), this sweeps the ENTIRE profile file:
# a stray Vertex/Anthropic/CF reference OUTSIDE api_base (e.g. a key, a header,
# or a commented host) would leak past the LOCAL-04 api_base-only guard. Kept
# cloud-LLM-scoped (NOT generic-online): "openai" is deliberately OMITTED — no
# OpenAI route exists and it would false-positive on vLLM's "OpenAI-compatible"
# prose (CONTEXT Discretion + RESEARCH A3). `sk-` covers an OpenAI/Anthropic
# key-prefix leak.
_FILE_DENY = (
    "CF_AIG_WRAPPER_URL",
    "vertex_ai",
    "googleapis.com",
    "anthropic",
    "anthropic.com",
    "sk-",
)
# Phase 11: the pristine cloud profile is the NEGATIVE CONTROL — it MUST trip
# _FILE_DENY. If it ever stops tripping, the sweep is vacuous/broken.
_CLOUD_PROFILE = _REPO / "config" / "model_gateway.cloud.yaml"


@pytest.mark.parametrize("name", list(_PROFILES))
def test_profile_has_three_exact_deployment_names(name):
    cfg = yaml.safe_load(_PROFILES[name].read_text())
    got = {r["model_name"] for r in cfg["model_list"]}
    assert _NAMES <= got, f"{name}: missing exact deployment names; has {got}"


@pytest.mark.parametrize("name", list(_PROFILES))
def test_every_route_api_base_is_loopback_or_service_dns(name):
    """Phase 11 D-01: every route's api_base is LOOPBACK or in-stack service-DNS.

    The 2 loopback profiles (vllm/ollama) still satisfy loopback; the 2 compose
    profiles point at the egress-free compose sibling services (vllm:8000,
    ollama:11434), which are allowlisted as in-stack — not flagged as non-loopback.
    """
    cfg = yaml.safe_load(_PROFILES[name].read_text())
    for r in cfg["model_list"]:
        ab = r["litellm_params"]["api_base"]
        assert ab.startswith(_LOCAL_ALLOW), (
            f"{name}/{r['model_name']}: api_base {ab!r} not loopback or service-DNS"
        )
        assert not any(m in ab for m in _CLOUD_MARKERS), (
            f"{name}/{r['model_name']}: cloud marker in api_base {ab!r}"
        )


@pytest.mark.parametrize("name", list(_PROFILES))
def test_profile_file_has_no_cloud_llm_marker(name):
    """Phase 11 D-01 (OFFLINE-02): WHOLE-FILE cloud-LLM-marker sweep — the gap the
    api_base-only LOCAL-04 guard left open. A stray Vertex/Anthropic/CF reference
    anywhere in the profile (key, header, comment, env-indirection) fails here."""
    text = _PROFILES[name].read_text()
    hits = [m for m in _FILE_DENY if m in text]
    assert not hits, f"{name}: cloud-LLM marker(s) {hits} present in profile file"


def test_cloud_reference_profile_does_trip_the_sweep():
    """Phase 11 negative control (mirrors test_d06_chokepoint.py:180): the pristine
    cloud profile MUST trip _FILE_DENY. This proves the whole-file sweep is
    non-vacuous and fails loudly if a future edit ever empties _FILE_DENY."""
    text = _CLOUD_PROFILE.read_text()
    tripped = [m for m in _FILE_DENY if m in text]
    assert tripped, (
        "config/model_gateway.cloud.yaml no longer trips _FILE_DENY — the "
        "whole-file cloud-LLM sweep is vacuous/broken (marker list emptied?)"
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
