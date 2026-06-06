"""GW-03 stub-lane cascade proof — fallback WIRING with no creds (default suite).

The Router is built from the real ``config/model_gateway.config.yaml`` via
``build_router()`` (D-09: in-process cascades). We force the primary deployment to
raise using the VERIFIED ``mock_testing_fallbacks=True`` hook
(``litellm.router._handle_mock_testing_fallbacks`` raises ``InternalServerError``
*before* any real completion runs, RESEARCH Finding 4), and pin the fallback's
response with the public ``mock_response`` kwarg so the FALLBACK deployment serves
deterministically with ZERO network and ZERO credentials.

This proves ``router_settings.fallbacks`` was loaded and honored in-process: the
primary fails, the Router cascades to the configured fallback, and the fallback
serves. No Router internals are monkeypatched — both kwargs are public litellm API.

Cascade map under test (from the yaml):
    low-complexity   -> [medium-complexity]
    medium-complexity-> [high-complexity]
    high-complexity  -> [high-complexity-vertex, medium-complexity]

The primary ``low-complexity`` is ``vertex_ai/gemini-1.5-flash``; its fallback
``medium-complexity`` is ``vertex_ai/gemini-1.5-pro``. We assert the served
``ModelResponse.model`` is the FALLBACK's underlying model (``gemini-1.5-pro``),
NOT the primary's (``gemini-1.5-flash``) — verified empirically at execution time.
"""

from __future__ import annotations

import pytest

from agent_mesh.worker.model_gateway import build_router

# Deployment names from config/model_gateway.config.yaml.
PRIMARY_DEPLOYMENT = "low-complexity"
FALLBACK_DEPLOYMENT = "medium-complexity"
# The underlying litellm model strings surfaced on ModelResponse.model.
PRIMARY_MODEL = "gemini-1.5-flash"  # vertex_ai/gemini-1.5-flash (low-complexity)
FALLBACK_MODEL = "gemini-1.5-pro"   # vertex_ai/gemini-1.5-pro  (medium-complexity)

_MOCK_CONTENT = "[fallback served]"


def _build_router():
    """Build the Router from the real yaml. ``build_router`` lazy-imports yaml +
    litellm; skip cleanly if the runtime extra is absent (keeps importability)."""
    try:
        return build_router()
    except Exception as exc:  # pragma: no cover - runtime extra missing
        pytest.skip(f"litellm runtime not installed: {exc}")


def test_primary_failure_cascades_to_configured_fallback():
    """The primary deployment is mock-failed; the Router cascades to the configured
    fallback, which serves deterministically (GW-03 wiring proof, no creds)."""
    router = _build_router()

    resp = router.completion(
        model=PRIMARY_DEPLOYMENT,
        messages=[{"role": "user", "content": "hi"}],
        mock_testing_fallbacks=True,  # primary raises InternalServerError -> cascade
        mock_response=_MOCK_CONTENT,  # fallback serves this deterministically (no net)
    )

    # The call SUCCEEDED (it did not propagate the primary's InternalServerError) —
    # i.e. the configured fallback caught the failure.
    served_content = resp.choices[0].message.content
    assert served_content == _MOCK_CONTENT, (
        f"expected the deterministic fallback response, got {served_content!r}"
    )

    # And the deployment that served is the FALLBACK, not the primary — proving
    # router_settings.fallbacks was loaded and honored in-process.
    served_model = resp.model
    assert served_model == FALLBACK_MODEL, (
        f"expected the FALLBACK deployment ({FALLBACK_DEPLOYMENT} -> {FALLBACK_MODEL}) "
        f"to serve, but ModelResponse.model was {served_model!r}"
    )
    assert served_model != PRIMARY_MODEL, (
        f"the PRIMARY ({PRIMARY_DEPLOYMENT} -> {PRIMARY_MODEL}) served — the cascade "
        f"did not occur"
    )


def test_router_loaded_the_fallbacks_from_config():
    """Defence-in-depth: the in-process Router actually carries the yaml fallbacks
    map (so the cascade above is config-driven, not an artefact of a default)."""
    router = _build_router()
    fallbacks = router.fallbacks or []
    # Flatten the list-of-single-key-dicts into a {primary: [fallbacks]} view.
    flat = {k: v for entry in fallbacks for k, v in entry.items()}
    assert flat.get(PRIMARY_DEPLOYMENT) == [FALLBACK_DEPLOYMENT], (
        f"Router.fallbacks for {PRIMARY_DEPLOYMENT!r} = {flat.get(PRIMARY_DEPLOYMENT)!r}; "
        f"expected [{FALLBACK_DEPLOYMENT!r}] from the yaml"
    )


def test_no_fallback_kwarg_means_primary_failure_propagates():
    """Negative control: without the cascade, mock-failing the primary with NO viable
    fallback target served must surface the failure — proves the success above is the
    fallback catching the error, not the mock silently swallowing it.

    We disable fallbacks for this single call so the mock InternalServerError on the
    primary has nowhere to cascade and must propagate."""
    from litellm.exceptions import InternalServerError

    router = _build_router()
    with pytest.raises(InternalServerError):
        router.completion(
            model=PRIMARY_DEPLOYMENT,
            messages=[{"role": "user", "content": "hi"}],
            mock_testing_fallbacks=True,
            mock_response=_MOCK_CONTENT,
            disable_fallbacks=True,  # no cascade -> the primary mock-failure propagates
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
