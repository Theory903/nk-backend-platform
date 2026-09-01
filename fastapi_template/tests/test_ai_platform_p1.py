"""Tests for vector store auto-selection (P1)."""

from __future__ import annotations

from pathlib import Path

TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
)


def test_store_factory_modules_exist() -> None:
    pkg = TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "ai" / "knowledge"
    assert (pkg / "store_factory.py").is_file()
    assert (pkg / "qdrant_store.py").is_file()
    text = (pkg / "store_factory.py").read_text(encoding="utf-8")
    assert "resolve_vector_backend" in text
    assert "create_vector_store" in text


def test_memory_factory_modules_exist() -> None:
    agents = TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "agents"
    assert (agents / "memory_redis.py").is_file()
    assert (agents / "memory_factory.py").is_file()


def test_compose_includes_qdrant_and_ollama_init() -> None:
    compose = (TEMPLATE_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "qdrant:" in compose
    assert "ollama-init:" in compose
    assert "qdrant-data" in compose


def test_settings_include_storage_backends() -> None:
    text = (
        TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "settings.py"
    ).read_text(encoding="utf-8")
    assert "vector_store_backend" in text
    assert "memory_backend" in text
    assert "qdrant_host" in text


def test_ai_doctor_probes_qdrant() -> None:
    script = (TEMPLATE_ROOT / "scripts" / "ai_doctor.py").read_text(encoding="utf-8")
    assert "probe_qdrant" in script
