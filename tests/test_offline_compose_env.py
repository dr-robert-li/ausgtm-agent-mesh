"""OFFLINE-02 (D-04) — ``docker-compose.yml`` api/worker env-block no-cloud-LLM sweep.

Companion to ``tests/test_local_profiles.py`` (which sweeps the 4 model-gateway
PROFILE files). This file sweeps the ASSEMBLED stack's env surface: the ``api``
and ``worker`` service ``environment:`` blocks in ``docker-compose.yml``. It
asserts the no-cloud-LLM-egress posture reaches the composed stack — no VALUED
cloud-LLM key (Vertex/Anthropic/CF) and no cloud host in any env value.

What this asserts:
  * Each named cloud-LLM key (``_CLOUD_KEY_NAMES``) is ABSENT or BLANK-valued in
    both env blocks. Semantics are VALUED-key, not substring: a key present but
    empty (``ANTHROPIC_API_KEY: ""``) is fine; present-and-non-empty is the
    violation. The compose env legitimately OMITS these keys today, so a
    substring sweep would be the wrong tool (it would also trip on the cloud
    profile's own intentionally-blank key names if any were declared).
  * No env VALUE in either service carries a cloud-LLM host substring
    (``googleapis.com``, ``anthropic``, ``gateway.ai.cloudflare.com``).

What this does NOT assert (out of scope — offline = cloud-LLM-scoped, NOT a
blanket no-network block):
  * The service-DNS model ``api_base`` mount (``model_gateway.${MODEL_PROFILE}.
    compose.yaml``) — that is covered by the Task-1 profile sweep, not here.
  * Local Postgres (``@postgres``), self-hosted Langfuse (``@langfuse-web``),
    blank ``LANGFUSE_*`` keys, and ``TMPDIR`` are all LEGITIMATE in-stack/local
    references and must NOT trip the sweep.

Static & daemon-free: this reads ``docker-compose.yml`` text with
``yaml.safe_load`` and asserts over the parsed dict. Unlike
``tests/test_compose_config.py`` (which shells ``docker compose config``), it
needs NO docker binary, so it carries NO ``skipif(shutil.which("docker"))`` and
auto-collects under plain ``make test`` (``pytest -q -m "not live"``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
_COMPOSE = _REPO / "docker-compose.yml"

# Named cloud-LLM / gateway keys whose PRESENCE-WITH-A-VALUE in the composed
# api/worker stack would constitute cloud-LLM egress config. Present-but-blank
# is OK (the posture leaves them blank); present-and-valued is the violation.
_CLOUD_KEY_NAMES = (
    "ANTHROPIC_API_KEY",
    "VERTEX_PROJECT_ID",
    "VERTEX_LOCATION",
    "CF_AIG_WRAPPER_URL",
    "MODEL_GATEWAY_SHARED_SECRET",
)

# Cloud-LLM host substrings that must not appear in any env VALUE.
_CLOUD_HOSTS = ("googleapis.com", "anthropic", "gateway.ai.cloudflare.com")

_SERVICES = ("api", "worker")


def _env_items(service: str) -> list[tuple[str, str]]:
    """Return the (key, value) pairs of a service's ``environment:`` block.

    Compose ``environment:`` may be a mapping (dict) OR a ``KEY=VALUE`` list —
    normalize both. A bare ``KEY`` (no ``=``) in the list form normalizes to an
    empty value (compose passes through the host env; for a static posture sweep
    a value-less key is treated as blank).
    """
    cfg = yaml.safe_load(_COMPOSE.read_text())
    env = cfg["services"][service].get("environment", {}) or {}
    if isinstance(env, dict):
        return [(str(k), "" if v is None else str(v)) for k, v in env.items()]
    # list form: "KEY=VALUE" or bare "KEY"
    items: list[tuple[str, str]] = []
    for entry in env:
        k, _, v = str(entry).partition("=")
        items.append((k, v))
    return items


@pytest.mark.parametrize("service", _SERVICES)
def test_no_valued_cloud_llm_key_in_env(service):
    """OFFLINE-02/D-04: no NAMED cloud-LLM key carries a value in the api/worker
    env block. Present-but-blank is OK; present-and-valued is the violation."""
    for k, v in _env_items(service):
        if k in _CLOUD_KEY_NAMES:
            assert not v, (
                f"{service}: cloud-LLM key {k} has a VALUED entry {v!r} "
                f"(present-but-blank is OK; valued is the egress violation)"
            )


@pytest.mark.parametrize("service", _SERVICES)
def test_no_cloud_host_in_env_values(service):
    """OFFLINE-02/D-04: no env VALUE in the api/worker block carries a cloud-LLM
    host substring. Local @postgres / @langfuse-web / TMPDIR must NOT trip."""
    for k, v in _env_items(service):
        lowered = v.lower()
        hits = [h for h in _CLOUD_HOSTS if h in lowered]
        assert not hits, (
            f"{service}: cloud-LLM host {hits} in env value {k}={v!r}"
        )


@pytest.mark.parametrize("service", _SERVICES)
def test_env_block_is_non_empty(service):
    """Sanity: the sweep actually walked a populated env block (a sweep over an
    empty/absent block would vacuously pass). Both api and worker declare env
    today (DATABASE_URL/LANGFUSE_* at minimum)."""
    items = _env_items(service)
    assert items, f"{service}: environment block is empty — sweep would be vacuous"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
