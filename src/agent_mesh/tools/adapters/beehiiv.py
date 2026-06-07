"""Beehiiv direct adapter (05-06, TOOL-03, D-07).

ONE dispatcher registered under provider key ``beehiiv`` (04-03 invariant). Beehiiv
exposes a single tool this phase — ``beehiiv_create_post`` (an approval-gated
publishing WRITE) — but it is still registered as a SINGLE dispatcher routing by
``spec.name`` via ``_BEEHIIV_OPS`` (NOT a bare ``register`` per op). This preserves the
one-dispatcher-per-provider shape so a future second Beehiiv op can be added without a
last-wins registration collision (the SC-1 defect HubSpot's docstring warns about).

DRAFT-ONLY (T-05-06-01): ``_create_post`` ALWAYS sends ``status:"draft"``. Even if a
caller passes ``status:"confirmed"`` (or any other value), the adapter overrides it —
this tool never auto-publishes a live post. The default-lane test asserts the override.

APPROVAL (D-07 / T-05-06-02): the manifest declares ``beehiiv_create_post`` as
``category: publishing`` -> ``approval_required: true``. The adapter performs NO gating
of its own; it is reached only after the worker's upstream approval gate
(``runner._resume_after_approval``) has approved the payload-hash-bound write. It is a
pure executor — no gating bypass.

NESTED OUTPUT (the canonical quarantine-avoidance case): Beehiiv's HTTP 201 body NESTS
the new post id under ``data`` — ``{"data": {"id": "post_..."}}`` — NOT a flat
``{"id": ...}``. The adapter maps to the nested shape so it conforms to
``schemas/beehiiv_create_post.output.schema.json`` (which ``require``s ``data``) and a
real create does NOT ``output_quarantine``.

HTTPX IS CORE (D-11): there is no SDK and no new dependency — the adapter calls Beehiiv
API v2 directly over the core ``httpx`` dependency. The stub-fallback branch is therefore
purely credential-driven (``if credential is None: return None``); there is NO
``ImportError`` branch (unlike HubSpot's opt-in SDK). When the credential is absent the
engine degrades to the deterministic stub before reaching the adapter, but the op still
returns ``None`` defensively if reached, so ``make test`` stays green and creds-free.

TOKEN (D-02): the API key is received as ``credential`` and is never logged or returned;
the engine resolves it inside ``execute()`` and discards it on return. The adapter reads
NO ``os.getenv`` — the token arrives only via the ``credential`` arg (T-05-06-03).

TIER CAVEAT: ``create-post`` is beta / Enterprise-tier-gated; a non-Enterprise key may
``403``. The default lane stubs regardless; the live lane treats a tier 403 as a skip.
See ``docs/credentials/beehiiv.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_mesh.tools.adapters import register

if TYPE_CHECKING:  # pragma: no cover - typing only
    from agent_mesh.tools.gateway import ToolSpec

# Beehiiv API v2 base. Auth header is ``Authorization: Bearer {credential}``.
_BEEHIIV_API_BASE = "https://api.beehiiv.com/v2"

# Optional body fields copied from params when present (besides the required title).
# status is deliberately EXCLUDED — it is always forced to "draft" below.
_OPTIONAL_BODY_FIELDS = ("subtitle", "body_content")


def _create_post(
    spec: ToolSpec, params: dict[str, Any], *, credential: str | None
) -> dict[str, Any] | None:
    """WRITE (approval-gated upstream): create a Beehiiv post — ALWAYS a draft.

    Maps the HTTP 201 body to the NESTED ``schemas/beehiiv_create_post.output.schema.json``
    shape ``{"data": {"id": <post-id>}}`` (NOT flat ``{id}``) so a real call does not
    output_quarantine. Reached only after the worker approval gate; the adapter never
    self-gates and never auto-publishes (``status`` is forced to ``"draft"``).
    """
    if credential is None:
        # Engine stubs before reaching here when the key is absent (D-11); this
        # defensive path returns None so the engine still degrades cleanly.
        return None

    # ``httpx`` is a CORE dependency — import is safe at module level, but kept local to
    # mirror the lazy-adapter pattern and avoid a top-level cost on every registry import.
    import httpx  # noqa: PLC0415

    publication_id = spec.resource_bindings["publication_id"]

    # ALWAYS force status:"draft" — never auto-publish, even if the caller passed
    # another status (e.g. "confirmed"). This is the draft-only guarantee (T-05-06-01).
    body: dict[str, Any] = {"title": params["title"], "status": "draft"}
    for field in _OPTIONAL_BODY_FIELDS:
        if params.get(field) is not None:
            body[field] = params[field]

    resp = httpx.post(
        f"{_BEEHIIV_API_BASE}/publications/{publication_id}/posts",
        headers={"Authorization": f"Bearer {credential}", "Accept": "application/json"},
        json=body,
        timeout=30,
    )
    resp.raise_for_status()  # 201 on success; a 403 (tier gate) raises here.
    payload = resp.json()

    # NESTED mapping: the real 201 body is {"data": {"id": ...}}; preserve the nesting
    # (do NOT flatten to {"id": ...}) so it conforms to the output schema. Guard the
    # double-subscript — a tier-gated/changed endpoint can return a 2xx with another
    # shape, and an unguarded KeyError would abort the worker rather than surface a
    # clean error (CR-01).
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or data.get("id") is None:
        raise ValueError(
            "beehiiv_create_post: unexpected 2xx response shape "
            "(expected {'data': {'id': ...}}); refusing to map"
        )
    return {"data": {"id": str(data["id"])}}


# spec.name -> op. The SINGLE dispatcher routes by spec.name even though Beehiiv has one
# op this phase — registering one op per provider key would last-wins-collide and make a
# future second op unreachable (SC-1). The key MUST match the manifest op name (05-01).
_BEEHIIV_OPS = {
    "beehiiv_create_post": _create_post,
}


def beehiiv_adapter(
    spec: ToolSpec, params: dict[str, Any], *, credential: str | None
) -> dict[str, Any] | None:
    """The ONE ``beehiiv`` dispatcher — routes by ``spec.name`` to the matching op."""
    return _BEEHIIV_OPS[spec.name](spec, params, credential=credential)


# Register EXACTLY ONCE under the provider key (04-03: registry keyed on spec.provider;
# execute() dispatches get_adapter(adapter_key_for(spec))="beehiiv").
register("beehiiv", beehiiv_adapter)
