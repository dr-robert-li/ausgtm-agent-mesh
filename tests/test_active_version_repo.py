"""Active-version pointer + AI-BOM persistence repo methods (06-01, SI-02b/SI-02).

Default lane (creds-free), against the in-memory repository. The SQL layer
mirrors these shapes exactly (upsert_promotion / list_evaluations) but is only
exercised when TEST_DATABASE_URL is set (pg_dsn-gated, out of the default suite).

Tenant scoping (T-06-01 / T-06-03, DUR-02) is a correctness requirement: a
pointer/snapshot owned by tenant A must NEVER be returned for tenant B.
"""

from agent_mesh.contracts.models import AIBOMSnapshot
from agent_mesh.services.repository import InMemoryRepository

# ---------------------------------------------------------------------------
# Active-version pointer (SI-02b)
# ---------------------------------------------------------------------------


def test_current_active_version_none_when_unset() -> None:
    repo = InMemoryRepository()
    assert repo.current_active_version("tenant-a") is None


def test_set_then_read_active_version() -> None:
    repo = InMemoryRepository()
    repo.set_active_version("tenant-a", "v1", promotion_id="promo-1")
    assert repo.current_active_version("tenant-a") == "v1"


def test_active_version_is_tenant_scoped() -> None:
    repo = InMemoryRepository()
    repo.set_active_version("tenant-a", "v1", promotion_id="promo-1")
    # DUR-02: tenant-A's pointer is never returned for tenant-B.
    assert repo.current_active_version("tenant-b") is None


def test_set_active_version_overwrites() -> None:
    repo = InMemoryRepository()
    repo.set_active_version("tenant-a", "v1", promotion_id="promo-1")
    repo.set_active_version("tenant-a", "v2", promotion_id="promo-2")
    # Upsert semantics, mirroring upsert_promotion.
    assert repo.current_active_version("tenant-a") == "v2"


def test_set_active_version_promotion_id_optional() -> None:
    repo = InMemoryRepository()
    repo.set_active_version("tenant-a", "v1")
    assert repo.current_active_version("tenant-a") == "v1"


# ---------------------------------------------------------------------------
# AI-BOM persistence (SI-02; consumed by 06-05)
# ---------------------------------------------------------------------------


def _snapshot(tenant_id: str = "tenant-a", snapshot_id: str | None = None) -> AIBOMSnapshot:
    kwargs = dict(
        tenant_id=tenant_id,
        client_slug="acme",
        version="v1",
        agents=[{"id": "planner"}],
        tools=[{"name": "gmail.send"}],
        skills=[{"name": "summarize"}],
        prompts=[{"id": "supervisor", "version": "3"}],
        model_routes={"high": "claude"},
    )
    if snapshot_id is not None:
        kwargs["snapshot_id"] = snapshot_id
    return AIBOMSnapshot(**kwargs)


def test_upsert_ai_bom_round_trip() -> None:
    repo = InMemoryRepository()
    snap = _snapshot()
    returned = repo.upsert_ai_bom(snap)
    assert returned.snapshot_id == snap.snapshot_id

    fetched = repo.get_ai_bom(snap.snapshot_id, "tenant-a")
    assert fetched is not None
    assert fetched.snapshot_id == snap.snapshot_id
    assert fetched.agents == [{"id": "planner"}]
    assert fetched.tools == [{"name": "gmail.send"}]
    assert fetched.skills == [{"name": "summarize"}]
    assert fetched.prompts == [{"id": "supervisor", "version": "3"}]
    assert fetched.model_routes == {"high": "claude"}


def test_get_ai_bom_is_tenant_scoped() -> None:
    repo = InMemoryRepository()
    snap = _snapshot(tenant_id="tenant-a")
    repo.upsert_ai_bom(snap)
    # DUR-02: a tenant-A snapshot is never returned for tenant-B.
    assert repo.get_ai_bom(snap.snapshot_id, "tenant-b") is None


def test_get_ai_bom_unknown_id_returns_none() -> None:
    repo = InMemoryRepository()
    assert repo.get_ai_bom("does-not-exist", "tenant-a") is None
