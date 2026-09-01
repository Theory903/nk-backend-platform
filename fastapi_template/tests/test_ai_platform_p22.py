"""Tests for P22 skill runtime + manifests."""

from __future__ import annotations

from pathlib import Path

TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
)
PKG = TEMPLATE_ROOT / "{{cookiecutter.project_name}}"
SKILLS = PKG / "agents" / "skills"


def test_p22_skill_runtime_modules_exist() -> None:
    for name in (
        "manifest.py",
        "manifest_loader.py",
        "runtime.py",
        "presets.yaml",
    ):
        assert (SKILLS / name).is_file(), name


def test_skill_manifest_schema() -> None:
    text = (SKILLS / "manifest.py").read_text(encoding="utf-8")
    for token in ("SkillManifest", "SkillPermissions", "SkillEvaluation", "tools"):
        assert token in text


def test_example_skill_has_skill_yaml() -> None:
    assert (SKILLS / "example" / "skill.yaml").is_file()
    text = (SKILLS / "example" / "skill.yaml").read_text(encoding="utf-8")
    assert "permissions:" in text
    assert "evaluation:" in text


def test_factory_builds_skill_runtime() -> None:
    text = (SKILLS / "factory.py").read_text(encoding="utf-8")
    assert "build_skill_runtime" in text
    assert "SkillRuntime" in text


def test_bootstrap_exposes_skill_runtime() -> None:
    text = (PKG / "agents" / "bootstrap.py").read_text(encoding="utf-8")
    assert "skill_runtime" in text
    assert "build_skill_runtime" in text


def test_presets_gstack_compatible() -> None:
    text = (SKILLS / "presets.yaml").read_text(encoding="utf-8")
    assert "gstack-compatible" in text
    assert "platform-guide" in text


def test_cli_skills_manifest_commands() -> None:
    text = (PKG / "cli" / "__init__.py").read_text(encoding="utf-8")
    assert "cmd_skills_manifest" in text
    assert "cmd_skills_presets" in text
    assert '"manifest"' in text
    assert "--manifests" in text
