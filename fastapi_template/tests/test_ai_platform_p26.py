"""Tests for P26 experiment runtime."""

from __future__ import annotations

from pathlib import Path

TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
)
PKG = TEMPLATE_ROOT / "{{cookiecutter.project_name}}"
RESEARCH = PKG / "research" / "experiments"


def test_p26_experiment_modules_exist() -> None:
    for name in (
        "contracts.py",
        "mutations.py",
        "store.py",
        "runtime.py",
        "catalog.yaml",
        "__init__.py",
    ):
        assert (RESEARCH / name).is_file(), name
    assert (PKG / "research" / "__init__.py").is_file()


def test_experiment_contracts() -> None:
    text = (RESEARCH / "contracts.py").read_text(encoding="utf-8")
    for token in (
        "Hypothesis",
        "MutationSpec",
        "ExperimentRecord",
        "ExperimentOutcome",
        "LeaderboardEntry",
    ):
        assert token in text


def test_hypothesis_catalog_loads() -> None:
    text = (RESEARCH / "catalog.yaml").read_text(encoding="utf-8")
    assert "agent-concise-replies" in text
    assert "routing-fast-capability" in text


def test_mutations_apply_and_revert() -> None:
    text = (RESEARCH / "mutations.py").read_text(encoding="utf-8")
    assert "apply_mutation" in text
    assert "revert_mutation" in text


def test_bootstrap_exposes_experiment_runtime() -> None:
    text = (PKG / "agents" / "bootstrap.py").read_text(encoding="utf-8")
    assert "build_experiment_runtime" in text
    assert "experiment_runtime" in text


def test_cli_experiment_commands() -> None:
    text = (PKG / "cli" / "__init__.py").read_text(encoding="utf-8")
    assert "cmd_ai_experiment_hypotheses" in text
    assert "cmd_ai_experiment_leaderboard" in text
    assert "cmd_ai_experiment_run" in text
    assert "cmd_ai_experiment_rollback" in text
    assert '"experiment"' in text
