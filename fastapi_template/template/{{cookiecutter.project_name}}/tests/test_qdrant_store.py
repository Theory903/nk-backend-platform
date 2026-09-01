"""Tests for Qdrant vector store adapter (P1)."""

from __future__ import annotations

from {{cookiecutter.project_name}}.ai.knowledge import qdrant_store as _qdrant


def test_qdrant_import_guard() -> None:
    assert _qdrant.QdrantVectorStore is not None or not _qdrant.HAS_QDRANT


def test_point_id_is_stable() -> None:
    from {{cookiecutter.project_name}}.ai.knowledge.qdrant_store import _point_id

    assert _point_id("doc:0") == _point_id("doc:0")
    assert _point_id("doc:0") != _point_id("doc:1")
