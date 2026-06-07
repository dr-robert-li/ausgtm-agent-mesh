"""Boot-time set-once active-version loader (SI-02b, criterion 5).

This module is the *non-hot* read path for the self-improvement active version.
It mirrors the set-once module-cache *shape* of ``observability._PROCESS_PROVIDER``
(a module-level global plus an accessor that reads the cache, never the source),
but it deliberately does NOT copy that ``if _X is None`` guard onto the loader.

Two distinct surfaces:

* :func:`active_version` — the hot path. Returns ONLY the module cache; it never
  reads the repository. This is what makes promotion non-hot: running code only
  ever calls ``active_version()``, so a promotion that writes a new pointer to
  the store cannot change live behaviour.
* :func:`load_active_version_at_boot` — the explicit boot / reload step. It
  UNCONDITIONALLY re-reads ``repo.current_active_version(tenant_id)`` and
  overwrites the cache, so a subsequent boot (or operator-owned reload) picks up
  the latest promoted/rolled-back pointer.

Hard rule (D-12 / CLAUDE.md no-runtime-mutation): never read the active version
via the settings accessor or any other call-time source. A promotion is inert
until an explicit, human-owned reload re-reads the store at the next boot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from agent_mesh.services.repository import Repository

# Process-level cache of the active promoted version. Set once at boot via
# ``load_active_version_at_boot`` and read by ``active_version`` on the hot path.
# Mirrors the ``observability._PROCESS_PROVIDER`` set-once cache shape.
_ACTIVE_VERSION: str | None = None


def load_active_version_at_boot(repo: Repository, tenant_id: str) -> str | None:
    """Read the tenant's active version from the store ONCE into the module cache.

    This is the explicit boot / reload step. It UNCONDITIONALLY re-reads the
    store (no ``if None`` guard) so an operator-owned reload reflects the latest
    promoted or rolled-back pointer. Returns the cached value."""
    global _ACTIVE_VERSION
    _ACTIVE_VERSION = repo.current_active_version(tenant_id)
    return _ACTIVE_VERSION


def active_version() -> str | None:
    """Return the boot-cached active version. NEVER reads the repository.

    Returns ``None`` before any :func:`load_active_version_at_boot` call. This is
    the only function the running mesh should call to learn the active version,
    which is what keeps promotion non-hot (criterion 5)."""
    return _ACTIVE_VERSION


def _reset() -> None:
    """Test-only hook: clear the module cache to simulate a fresh boot."""
    global _ACTIVE_VERSION
    _ACTIVE_VERSION = None
