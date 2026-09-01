"""Tests for P30 self-improving loop."""

from __future__ import annotations

from pathlib import Path

TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
)
PKG = TEMPLATE_ROOT / "{{cookiecutter.project_name}}"
P30 = PKG / "research" / "self_improving"


def test_p30_modules_exist() -> None:
    for name in (
        "contracts.py",
        "telemetry.py",
        "gates.py",
        "pipeline.py",
        "__init__.py",
    ):
        assert (P30 / name).is_file(), name
    assert (PKG / "research" / "__init__.py").is_file()


def test_contracts_include_loop_models() -> None:
    text = (P30 / "contracts.py").read_text(encoding="utf-8")
    for token in (
        "TelemetrySignal",
        "ImprovementProposal",
        "CanaryDecision",
        "PipelineRun",
    ):
        assert token in text


def test_pipeline_evaluate_and_rollback() -> None:
    text = (P30 / "pipeline.py").read_text(encoding="utf-8")
    assert "evaluate_proposal" in text
    assert "rollback" in text
    assert "propose_from_experiment" in text


def test_bootstrap_exposes_pipeline() -> None:
    text = (PKG / "agents" / "bootstrap.py").read_text(encoding="utf-8")
    assert "build_self_improving_pipeline" in text
    assert "self_improving_pipeline" in text


def test_cli_self_improving_commands() -> None:
    text = (PKG / "cli" / "__init__.py").read_text(encoding="utf-8")
    assert "cmd_ai_self_improving" in text
    assert '"self-improving"' in text
