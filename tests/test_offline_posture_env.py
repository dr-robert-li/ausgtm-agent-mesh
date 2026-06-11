"""OFFLINE-01 (D-03) — ``.env.offline.example`` valued-cloud-key sweep.

Asserts the concrete OFFLINE posture artifact expresses "no cloud-hosted LLM
egress" honestly: every NAMED cloud-LLM / gateway credential is present-but-BLANK
(``ANTHROPIC_API_KEY=`` with no value), and the model gateway base URL resolves
to a LOCAL (loopback) host.

Why VALUED-key semantics, NOT a substring sweep (load-bearing correction —
11-PATTERNS.md:24-31): the posture file legitimately contains the cloud-LLM key
*names* (``CF_AIG_WRAPPER_URL=``, ``ANTHROPIC_API_KEY=``) blank by design. A
substring sweep (``"anthropic" in text``) would false-trip on the file's own
intentionally-blank key names. The correct check is "key present but VALUED"
(non-empty value) = violation; "key present but blank" = OK.

Scope (offline = cloud-LLM-scoped, NOT a blanket no-network block):
  * SaaS / tool-pack creds (``COMPOSIO_API_KEY``, ``BITSCALE_API_KEY``) are
    LEFT NORMAL — this sweep does NOT require them blank (over-asserting them is
    a documented trap). The offline posture zeroes only cloud-LLM/gateway creds.
  * Local Postgres DSN, self-hosted ``LANGFUSE_HOST``, and the local
    ``MODEL_GATEWAY_BASE_URL`` are all legitimate and must NOT be flagged.

Static & creds-free: reads ``.env.offline.example`` text, parses ``KEY=VALUE``
lines, asserts over them. No env var gates this test — it runs (does NOT skip)
under plain ``make test`` (``pytest -q -m "not live"``).
"""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_OFFLINE_ENV = _REPO / ".env.offline.example"

# Named cloud-LLM / gateway keys whose PRESENCE-WITH-A-VALUE in the offline
# posture file would constitute cloud-LLM egress config. Present-but-blank is the
# posture; present-and-valued is the violation. Six names per 11-03-PLAN.md
# interfaces (:90) — note this includes MODEL_GATEWAY_MASTER_KEY, which the
# compose-env sweep (test_offline_compose_env.py) omits.
_CLOUD_KEY_NAMES = (
    "ANTHROPIC_API_KEY",
    "VERTEX_PROJECT_ID",
    "VERTEX_LOCATION",
    "CF_AIG_WRAPPER_URL",
    "MODEL_GATEWAY_SHARED_SECRET",
    "MODEL_GATEWAY_MASTER_KEY",
)

_LOCAL_HOSTS = ("http://localhost", "http://127.0.0.1")


def _env_pairs() -> dict[str, str]:
    """Parse ``.env.offline.example`` into a {KEY: VALUE} map.

    Skips blank lines and ``#`` comment lines (the file's prose comments carry
    ``=`` and commas that a naive splitter would mis-key), splits on the FIRST
    ``=`` only, and strips surrounding whitespace from the value.
    """
    pairs: dict[str, str] = {}
    for raw in _OFFLINE_ENV.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        pairs[key.strip()] = value.strip()
    return pairs


def test_offline_env_file_exists():
    """The concrete posture artifact (D-03) is shipped."""
    assert _OFFLINE_ENV.is_file(), f"{_OFFLINE_ENV} not found"


def test_cloud_llm_keys_present_but_blank():
    """OFFLINE-01/D-03: every named cloud-LLM/gateway key is present AND blank.

    Present-but-blank = the offline posture; present-and-valued = cloud-LLM
    egress config (the violation). This is the valued-key rule, NOT a substring
    sweep (the file legitimately contains the blank key names by design).
    """
    pairs = _env_pairs()
    for key in _CLOUD_KEY_NAMES:
        assert key in pairs, (
            f"{key} not present in .env.offline.example — the offline posture "
            f"should declare it (blank), not omit it"
        )
        assert not pairs[key], (
            f"{key} carries a VALUE {pairs[key]!r} in .env.offline.example — "
            f"the offline posture requires it BLANK (no cloud-LLM egress)"
        )


def test_model_gateway_base_url_is_local():
    """OFFLINE-01: MODEL_GATEWAY_BASE_URL resolves to a local (loopback) host."""
    pairs = _env_pairs()
    base = pairs.get("MODEL_GATEWAY_BASE_URL", "")
    assert base.startswith(_LOCAL_HOSTS), (
        f"MODEL_GATEWAY_BASE_URL {base!r} is not local "
        f"(expected one of {_LOCAL_HOSTS})"
    )


def test_saas_creds_are_not_over_asserted():
    """Scope guard: the offline posture zeroes ONLY cloud-LLM/gateway creds.

    SaaS / tool-pack creds and the local data plane stay NORMAL — this sweep must
    not over-assert them blank. We assert the keys are present (the file carries
    them) WITHOUT requiring them blank, documenting that they are out of the
    cloud-LLM-egress scope.
    """
    pairs = _env_pairs()
    for key in ("COMPOSIO_API_KEY", "BITSCALE_API_KEY", "DATABASE_URL"):
        assert key in pairs, f"{key} missing from .env.offline.example"
    # DATABASE_URL is a local dev DSN, NOT blanked (legitimate under offline).
    assert pairs["DATABASE_URL"], "DATABASE_URL should keep its local dev DSN"


if __name__ == "__main__":  # pragma: no cover
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
