"""OBS-02 default lane: prompt fetch-with-fallback returns the local default offline.

``get_prompt_with_fallback`` is the stub-fallback invariant for OBS-02: when Langfuse
is uninstalled / unreachable / unconfigured (no creds), it MUST return the trusted
local default so ``make test`` stays green with no cloud deps — and so an unreachable
remote can never inject a prompt (T-03-03-04). The live seeding of the versioned
prompt itself is the live lane (test_langfuse_seed_live.py).
"""

from __future__ import annotations

import agent_mesh.observability as obs

_LOCAL_DEFAULT = "You are the planner. Decompose the task into an ordered plan."


def test_fallback_returns_local_default_without_creds(monkeypatch):
    # No Langfuse credentials configured -> the client cannot authenticate, so the
    # fetch path raises/disables and the trusted local default is returned.
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    result = obs.get_prompt_with_fallback("agent-mesh/planner-system", _LOCAL_DEFAULT)
    assert result == _LOCAL_DEFAULT


def test_fallback_returns_local_default_when_langfuse_unavailable(monkeypatch):
    # Simulate langfuse not installed: the feature gate returns False, so the
    # function short-circuits to the local default with no import attempt.
    monkeypatch.setattr(obs, "langfuse_available", lambda: False)

    result = obs.get_prompt_with_fallback("agent-mesh/reviewer-system", _LOCAL_DEFAULT)
    assert result == _LOCAL_DEFAULT


def test_fallback_used_when_get_prompt_raises(monkeypatch):
    # langfuse "available" but the remote fetch raises (unreachable host / bad
    # creds): the except path returns the trusted local default, never propagating
    # the error and never returning a partially-fetched prompt.
    monkeypatch.setattr(obs, "langfuse_available", lambda: True)

    import langfuse

    class _BoomClient:
        def __init__(self, *a, **k):
            pass

        def get_prompt(self, *a, **k):
            raise RuntimeError("langfuse unreachable")

    monkeypatch.setattr(langfuse, "Langfuse", _BoomClient)

    result = obs.get_prompt_with_fallback("agent-mesh/planner-system", _LOCAL_DEFAULT)
    assert result == _LOCAL_DEFAULT
