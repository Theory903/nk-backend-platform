"""Tests for P14 harness runner wiring."""

from __future__ import annotations

from pathlib import Path

TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
)
AGENTS = TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "agents"


def test_p14_harness_modules_exist() -> None:
    harness = AGENTS / "harness"
    assert (harness / "trajectory.py").is_file()
    assert (harness / "scenarios.py").is_file()
    assert (harness / "fixtures.py").is_file()
    assert (harness / "runner.py").is_file()


def test_scenarios_yaml_exists() -> None:
    assert (TEMPLATE_ROOT / "tests" / "evals" / "scenarios.yaml").is_file()


def test_harness_exports_scenario_runner() -> None:
    text = (AGENTS / "harness" / "__init__.py").read_text(encoding="utf-8")
    assert "ScenarioRunner" in text
    assert "HarnessMode" in text
    assert "load_scenarios_yaml" in text


def test_cli_harness_commands() -> None:
    text = (
        TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "cli" / "__init__.py"
    ).read_text(encoding="utf-8")
    assert "cmd_ai_harness_run" in text
    assert "cmd_ai_harness_record" in text
    assert "cmd_ai_harness_replay" in text
    assert "cmd_ai_harness_list" in text


def test_harness_loop_accepts_recorder() -> None:
    text = (AGENTS / "harness" / "__init__.py").read_text(encoding="utf-8")
    assert "recorder" in text
