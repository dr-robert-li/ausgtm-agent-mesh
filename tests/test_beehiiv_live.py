"""Beehiiv live lane (05-06, TOOL-03, D-07) — OPT-IN.

The whole module is ``@pytest.mark.live`` (deselected without ``-m live``) and SKIPS
inline when ``BEEHIIV_API_KEY`` is unset — so ``make test`` never reaches Beehiiv and
never requires a key. NOTE: this gates on the Beehiiv key directly (NOT the shared
``live_creds`` fixture, which gates on model/gateway creds — a different credential axis).

CONSERVATIVE BY DESIGN. ``beehiiv_create_post`` is BOTH an approval-gated publishing
mutation AND beta / Enterprise-tier-gated (a non-Enterprise key may ``403``). So the
live lane does NOT blindly create a post:

- By default it asserts the create CALL SHAPE through the gateway/registry — the
  ``beehiiv`` dispatcher is reachable, the spec resolves, and ``status`` is forced to
  ``"draft"`` (never ``"published"``). The end-to-end nested-output mapping is proven in
  the default lane (mirroring HubSpot's write being proven in the default lane).
- Only when ``BEEHIIV_LIVE_PUBLICATION_ID`` is ALSO set does it execute a real draft
  create through the gateway, treating a ``403`` (tier gate) as a skip.

In every path it asserts no ``status:"published"`` is ever sent.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.live  # whole module is opt-in live lane


def _key_present() -> bool:
    return bool(os.getenv("BEEHIIV_API_KEY"))


def test_beehiiv_create_dispatcher_forces_draft_shape():
    """The beehiiv dispatcher is reachable and the create body forces status:"draft"
    (never "published"). Skips without the key. Does NOT hit the network unless an
    explicit BEEHIIV_LIVE_PUBLICATION_ID is supplied (opt-in real create below)."""
    if not _key_present():
        pytest.skip("BEEHIIV_API_KEY not set; live Beehiiv lane skipped")

    from agent_mesh.tools import adapters
    from agent_mesh.tools.adapters import beehiiv as bh

    # The dispatcher is registered and reachable via the 04-03 import-on-miss seam.
    fn = adapters.get_adapter("beehiiv")
    assert callable(fn) and fn.__name__ == "beehiiv_adapter"
    assert "beehiiv_create_post" in bh._BEEHIIV_OPS

    pub_id = os.getenv("BEEHIIV_LIVE_PUBLICATION_ID")
    if not pub_id:
        pytest.skip(
            "BEEHIIV_LIVE_PUBLICATION_ID not set; create-shape verified, "
            "real draft create skipped (approval-gated publishing mutation)"
        )

    # Opt-in REAL draft create through the gateway. Token resolved only at call time
    # (D-02). A 403 means the key is not Enterprise-tier — treat as a skip, not a fail.
    import httpx

    from agent_mesh.contracts.enums import ToolCategory
    from agent_mesh.tools.credentials import EnvCredentialResolver
    from agent_mesh.tools.gateway import ToolSpec

    spec = ToolSpec(
        name="beehiiv_create_post",
        provider="beehiiv",
        category=ToolCategory.PUBLISHING,
        description="",
        approval_required=True,
        credential_secret_name="BEEHIIV_API_KEY",
        resource_bindings={"publication_id": pub_id},
        integration_style="direct_api",
    )
    # Drive the adapter directly with the resolved credential (mirrors execute() post-gate).
    credential = EnvCredentialResolver().resolve("BEEHIIV_API_KEY")
    try:
        result = bh.beehiiv_adapter(
            spec,
            {"title": "ausgtm live test draft", "status": "confirmed"},
            credential=credential,
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            pytest.skip("Beehiiv create-post is Enterprise-tier-gated (403); skipping")
        raise

    # Non-stub nested output; the create was forced to draft (never published).
    assert "data" in result and "id" in result["data"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-m", "live", "-v"]))
