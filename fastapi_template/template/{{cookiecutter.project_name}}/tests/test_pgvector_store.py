"""Tests for pgvector store implementation."""
import pytest

from {{cookiecutter.project_name}}.ai.knowledge import pgvector_store as _pgv

HAS_PGVECTOR = _pgv.HAS_PGVECTOR

try:
    from {{cookiecutter.project_name}}.ai.knowledge.pgvector_store import PgVectorStore
except ImportError:
    PgVectorStore = None  # type: ignore[assignment,misc]


def test_pgvector_import_guard():
    """Module imports cleanly even without pgvector installed."""
    assert _pgv.PgVectorStore is not None or not HAS_PGVECTOR


@pytest.mark.skipif(not HAS_PGVECTOR, reason="pgvector package not installed")
class TestPgVectorStore:
    def test_init_requires_session_factory(self) -> None:
        with pytest.raises(TypeError):
            PgVectorStore()
