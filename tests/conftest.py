import pytest

from agent_mesh.services.repository import InMemoryRepository


@pytest.fixture
def repo() -> InMemoryRepository:
    """Fresh in-memory repository per test (avoids the process-wide singleton)."""
    return InMemoryRepository()
