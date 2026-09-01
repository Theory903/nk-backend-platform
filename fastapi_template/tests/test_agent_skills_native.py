"""Tests for NK-native agent skills (no vendor copy)."""

from __future__ import annotations

from pathlib import Path

SKILLS_DIR = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
    / "{{cookiecutter.project_name}}"
    / "agents"
    / "skills"
)


def test_curated_skills_ship_in_template() -> None:
    markers = list(SKILLS_DIR.glob("*/SKILL.md"))
    names = {p.parent.name for p in markers}
    assert "project-graveyard" in names
    assert "scope-creep-detector" in names
    assert len(markers) >= 6


def test_skill_factory_module_exists() -> None:
    assert (SKILLS_DIR / "factory.py").is_file()


def test_patterns_module_exists() -> None:
    patterns = SKILLS_DIR.parent / "patterns.py"
    assert patterns.is_file()
