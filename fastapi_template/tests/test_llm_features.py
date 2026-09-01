"""Tests for LLM feature packs and upstream catalog."""

from __future__ import annotations

from pathlib import Path

import yaml


FEATURES = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
    / "{{cookiecutter.project_name}}"
    / "llm"
    / "features"
)


def test_catalog_maps_upstream_to_packs() -> None:
    catalog_path = FEATURES / "catalog.yaml"
    assert catalog_path.is_file()
    data = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    assert data["upstream_count"] >= 100
    assert len(data["packs"]) >= 13
    packs = data["packs"]
    assert packs["chat_over_docs"]["upstream_templates"] > 0
    assert packs["starter_agents"]["upstream_templates"] > 0


def test_all_pack_modules_exist() -> None:
    for name in (
        "chat_over_docs",
        "agentic_rag",
        "deep_research",
        "data_analyst",
        "starter_agents",
        "advanced_agents",
        "mcp_assistant",
        "memory_chat",
        "voice_multimodal",
        "always_on",
        "generative_ui",
        "structured_agents",
    ):
        assert (FEATURES / name / "__init__.py").is_file(), name


def test_shared_common_modules_exist() -> None:
    assert (FEATURES / "common" / "rag.py").is_file()
    assert (FEATURES / "common" / "research.py").is_file()
    assert (FEATURES / "common" / "agentic.py").is_file()
    assert (FEATURES / "common" / "memory_tools.py").is_file()
    assert (FEATURES / "common" / "teams.py").is_file()
    assert (FEATURES / "common" / "always_on.py").is_file()
    assert (FEATURES / "runtime.py").is_file()
    assert (FEATURES / "registry.py").is_file()
    assert (FEATURES / "router.py").is_file()


def test_pack_imports_use_cookiecutter_placeholders() -> None:
    import re

    bad = re.compile(r"(?<!\{)\{cookiecutter\.project_name\}(?!\})")
    for name in (
        "chat_over_docs",
        "agentic_rag",
        "deep_research",
        "memory_chat",
        "advanced_agents",
        "always_on",
        "voice_multimodal",
    ):
        text = (FEATURES / name / "__init__.py").read_text(encoding="utf-8")
        assert bad.search(text) is None, name
        assert "{{cookiecutter.project_name}}" in text, name
