"""GW-01: in-process LiteLLM Router loader + RouterChatLiteLLM binding.

THE LOAD-BEARING PROOF (03-RESEARCH Finding 1 / Pitfall 1): ``langchain_litellm``'s
pydantic validator at ``litellm.py:558`` runs ``values["client"] = litellm``
UNCONDITIONALLY, so a plain ``ChatLiteLLM(client=router)`` is silently ignored and the
Router never executes. ``RouterChatLiteLLM`` overrides ``completion_with_retry`` /
``acompletion_with_retry`` to call a HELD Router instead. ``test_router_chat_litellm_
routes_through_router`` proves an ``.invoke()`` lands exactly one completion call on the
stubbed Router (NOT on bare litellm) — the override defeats the clobber, verifiably.

These tests need ``litellm`` + ``langchain_litellm`` importable but NO network/creds.
"""

from __future__ import annotations

import asyncio

from agent_mesh.worker import model_gateway


def test_build_router_loads_yaml_fallbacks_and_retries():
    router = model_gateway.build_router("config/model_gateway.config.yaml")
    from litellm import Router

    assert isinstance(router, Router)
    # num_retries comes from router_settings in the yaml (2).
    assert router.num_retries == 2
    # The four declared deployments are loaded (hyphenated model_name values).
    names = {d["model_name"] for d in router.model_list}
    assert {"low-complexity", "medium-complexity", "high-complexity"} <= names


def test_router_chat_litellm_routes_through_router(stub_router):
    """LOAD-BEARING: .invoke() routes through the held Router, not bare litellm."""
    chat = model_gateway.RouterChatLiteLLM(model="high-complexity")
    # Inject the recording stub as the held Router (defeating the line-558 clobber).
    chat._router = stub_router

    result = chat.invoke("hello world")

    # Exactly one completion call landed on the STUB Router (not on litellm).
    assert len(stub_router.calls) == 1
    assert stub_router.acalls == []
    # The deployment name is forwarded as model= so the Router resolves the route.
    assert stub_router.calls[0]["model"] == "high-complexity"
    # The result is the stub's response, threaded back through ChatLiteLLM.
    assert result.content == "[stub-router] ok"


def test_router_chat_litellm_async_routes_through_router(stub_router):
    """Async twin: .ainvoke() routes through the held Router's acompletion."""
    chat = model_gateway.RouterChatLiteLLM(model="high-complexity")
    chat._router = stub_router

    result = asyncio.run(chat.ainvoke("hello world"))

    assert len(stub_router.acalls) == 1
    assert stub_router.calls == []
    assert result.content == "[stub-router] ok"


def test_get_chat_model_returns_router_backed_model():
    chat = model_gateway.get_chat_model("high_complexity")
    assert isinstance(chat, model_gateway.RouterChatLiteLLM)
    # model= is the hyphenated yaml DEPLOYMENT name, not the underscore tier key
    # and not a raw provider id — or live routing would 404 "deployment not found".
    assert chat.model == "high-complexity"
    # A real Router is attached.
    from litellm import Router

    assert isinstance(chat._router, Router)


# --- delegated-call cost accounting (creds-free, D-04) ----------------------


def test_actual_cost_prices_from_usage_metadata():
    """D-04: post-call cost is priced from AIMessage.usage_metadata, not the estimate.

    Regression guard: ``chat.invoke`` returns a LangChain AIMessage whose token counts
    live in ``usage_metadata`` (input_tokens/output_tokens), NOT a litellm ``_response``.
    """
    from agent_mesh.worker.graph import _actual_cost

    usage = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
    cost, prompt_tokens, completion_tokens = _actual_cost(
        "anthropic/claude-sonnet-4-6", usage, fallback=999.0
    )
    assert prompt_tokens == 100
    assert completion_tokens == 50
    # A real (small, positive) priced cost — NOT the 999.0 fallback.
    assert 0.0 < cost < 999.0


def test_actual_cost_falls_back_when_usage_absent():
    from agent_mesh.worker.graph import _actual_cost

    cost, prompt_tokens, completion_tokens = _actual_cost(
        "anthropic/claude-sonnet-4-6", None, fallback=0.42
    )
    assert cost == 0.42
    assert prompt_tokens == 0 and completion_tokens == 0
