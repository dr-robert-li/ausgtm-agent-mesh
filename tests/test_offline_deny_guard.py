"""OFFLINE-03 (D-02): a `socket.getaddrinfo` autouse deny-guard that raises ONLY
on known cloud-LLM hosts, proving the default creds-free lane performs no outbound
to a real LLM provider / model gateway — while every other host (Postgres,
Langfuse, SaaS, loopback, service-DNS) is allowed.

Why `socket.getaddrinfo` and not `socket.create_connection`: the DNS-resolution
seam is the single point BOTH the sync (httpcore) and async (anyio) httpx backends
must pass through. A `create_connection`-only guard passes its sync positive
control but lets the real LangGraph/Deep Agents async worker (`acompletion`) reach
the provider unblocked — a silently vacuous proof (RESEARCH Pitfall 1, empirically
verified against litellm 1.83.7 / httpx 0.28.1).

Scope (CONTEXT): "offline" = no cloud-hosted LLM inference (Anthropic-direct,
Vertex AI, the Cloudflare AI Gateway model path). It does NOT mean blocking all
outbound. This is a cloud-LLM-host deny-list, NOT a pytest-socket global disable.

The guard is file-local autouse (function-scoped — the autouse=True default; NOT
`scope="module"`, which would raise pytest ScopeMismatch against function-scoped
`monkeypatch`). It no-ops when real provider creds are present so `make test-live`
real cloud calls are not blocked (Pitfall 4). Zero `src/` change — the guard lives
entirely here in tests/.
"""

from __future__ import annotations

import asyncio
import os
import socket

import pytest

# ---------------------------------------------------------------------------
# Cloud-LLM hosts the offline posture forbids (D-02 / RESEARCH Final Host List).
# anthropic.com VERIFIED at the seam this session; Vertex + CF ASSUMED (host shape
# known, but not observed reaching the seam in the creds-free lane — Vertex dies at
# DefaultCredentialsError BEFORE connect, Pitfall 2). Included defensively.
# Match the PRECISE Vertex host (`aiplatform.googleapis.com`), NEVER bare
# `googleapis.com` — a SaaS adapter may legitimately call other Google APIs
# (e.g. sheets.googleapis.com) (V5 input-validation precision).
# ---------------------------------------------------------------------------
_CLOUD_LLM_HOSTS = (
    "api.anthropic.com",
    "anthropic.com",
    "aiplatform.googleapis.com",  # Vertex (regional: <region>-aiplatform.googleapis.com)
    "gateway.ai.cloudflare.com",  # Cloudflare AI Gateway
)

# Reuse the conftest.py live_creds probe set (:124-136), INVERTED: when ANY real
# provider/gateway cred is present, the autouse guard no-ops so `make test-live`'s
# legitimate cloud calls are not blocked (Pitfall 4). The guard targets the default
# creds-free lane only.
_LIVE_CREDS_VARS = ("ANTHROPIC_API_KEY", "VERTEX_PROJECT_ID", "CF_AIG_WRAPPER_URL")


def _is_cloud_llm_host(host: str) -> bool:
    """True iff ``host`` is a known cloud-LLM provider / gateway host.

    Matches the exact host list plus the regional Vertex shape
    (`<region>-aiplatform.googleapis.com`) and CF subdomain shape
    (`*.gateway.ai.cloudflare.com`). Precise Vertex match only — bare
    `googleapis.com` is NOT denied (other Google APIs are legitimate SaaS traffic).
    """
    h = (host or "").lower()
    if h in _CLOUD_LLM_HOSTS:
        return True
    if h.endswith("-aiplatform.googleapis.com") or h.endswith(".gateway.ai.cloudflare.com"):
        return True
    return False


@pytest.fixture(autouse=True)
def _cloud_llm_deny_guard(monkeypatch):
    """File-local autouse (function-scoped) cloud-LLM-host deny-guard.

    Patches `socket.getaddrinfo` to raise ONLY on cloud-LLM hosts; every other
    host delegates to the real resolver. No-ops when real creds are present
    (Pitfall 4). Suppresses litellm's model-cost-map fetch to
    raw.githubusercontent.com (Pitfall 3).
    """
    # Pitfall 4: gate OFF when real provider creds are present so the live lane's
    # real cloud calls are not blocked. Yield WITHOUT patching in that case.
    if any(os.getenv(var) for var in _LIVE_CREDS_VARS):
        yield
        return

    # Pitfall 3: tell litellm to use its bundled cost map instead of fetching
    # https://raw.githubusercontent.com/.../model_prices_and_context_window.json
    # at call time (a non-cloud-LLM outbound the "offline" suite should not make).
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")

    real = socket.getaddrinfo

    # Pitfall 6: observed callers pass `host` positionally in both the httpcore
    # sync and anyio async backends; accept it positionally but stay defensive
    # about the rest of the signature.
    def guard(host, *args, **kwargs):
        if _is_cloud_llm_host(host):
            raise RuntimeError(f"OFFLINE deny: cloud-LLM host {host!r} contacted")
        return real(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", guard)
    yield


# ---------------------------------------------------------------------------
# Host-classification unit assertions: precise Vertex match, not bare googleapis.
# ---------------------------------------------------------------------------


def test_is_cloud_llm_host_matches_vertex_precisely():
    assert _is_cloud_llm_host("aiplatform.googleapis.com") is True
    assert _is_cloud_llm_host("australia-southeast1-aiplatform.googleapis.com") is True
    # A non-Vertex Google API is legitimate SaaS traffic — must NOT be denied.
    assert _is_cloud_llm_host("sheets.googleapis.com") is False
    assert _is_cloud_llm_host("googleapis.com") is False


def test_is_cloud_llm_host_matches_anthropic_and_cf():
    assert _is_cloud_llm_host("api.anthropic.com") is True
    assert _is_cloud_llm_host("anthropic.com") is True
    assert _is_cloud_llm_host("gateway.ai.cloudflare.com") is True
    assert _is_cloud_llm_host("acct123.gateway.ai.cloudflare.com") is True
    # Non-cloud-LLM hosts pass through.
    assert _is_cloud_llm_host("localhost") is False
    assert _is_cloud_llm_host("vllm") is False
    assert _is_cloud_llm_host("raw.githubusercontent.com") is False


# ---------------------------------------------------------------------------
# Positive controls — prove the guard is WIRED. Use `anthropic/` (it reaches the
# `getaddrinfo` seam with a fake sk-ant- key), NEVER `vertex_ai/` (which dies at
# DefaultCredentialsError BEFORE connect in the creds-free lane — Pitfall 2).
# ---------------------------------------------------------------------------


def test_guard_denies_anthropic_sync_positive_control():
    """SYNC path: an `anthropic/` completion MUST trip the guard."""
    import litellm

    with pytest.raises(Exception) as ei:
        litellm.completion(
            model="anthropic/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "hi"}],
            api_key="sk-ant-fake",
            max_retries=0,
        )
    assert "OFFLINE deny" in str(ei.value) or "anthropic.com" in str(ei.value)


def test_guard_denies_anthropic_async_positive_control():
    """ASYNC path (`acompletion`): the path the real LangGraph/Deep Agents worker
    uses (RESEARCH Pitfall 1 / A5). It MUST also trip — a sync-only proof is
    vacuous against the async worker."""
    import litellm

    async def go():
        with pytest.raises(Exception) as ei:
            await litellm.acompletion(
                model="anthropic/claude-sonnet-4-6",
                messages=[{"role": "user", "content": "hi"}],
                api_key="sk-ant-fake",
                max_retries=0,
            )
        assert "OFFLINE deny" in str(ei.value) or "anthropic.com" in str(ei.value)

    asyncio.run(go())
