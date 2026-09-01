"""Tests for vector store factory (P1)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from {{cookiecutter.project_name}}.ai.knowledge.store_factory import resolve_vector_backend


def test_resolve_vector_backend_honors_explicit_memory() -> None:
    app = MagicMock()
    with patch(
        "{{cookiecutter.project_name}}.ai.knowledge.store_factory.settings",
    ) as mock_settings:
        mock_settings.vector_store_backend = "memory"
        assert resolve_vector_backend(app) == "memory"


def test_resolve_vector_backend_honors_explicit_qdrant() -> None:
    app = MagicMock()
    with patch(
        "{{cookiecutter.project_name}}.ai.knowledge.store_factory.settings",
    ) as mock_settings:
        mock_settings.vector_store_backend = "qdrant"
        assert resolve_vector_backend(app) == "qdrant"
