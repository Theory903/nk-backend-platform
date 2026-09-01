"""Tests for P15 evaluation adapters."""

from __future__ import annotations

from pathlib import Path

TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
)
EVAL = TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "agents" / "evaluation"


def test_p15_adapter_modules_exist() -> None:
    adapters = EVAL / "adapters"
    assert (adapters / "base.py").is_file()
    assert (adapters / "native.py").is_file()
    assert (adapters / "ragas.py").is_file()
    assert (adapters / "deepeval.py").is_file()
    assert (adapters / "promptfoo.py").is_file()
    assert (adapters / "harness.py").is_file()
    assert (adapters / "registry.py").is_file() or (adapters / "__init__.py").is_file()


def test_adapter_registry_lists_backends() -> None:
    text = (EVAL / "adapters" / "__init__.py").read_text(encoding="utf-8")
    for name in ("native", "harness", "ragas", "deepeval", "promptfoo"):
        assert f'"{name}"' in text


def test_cli_eval_commands() -> None:
    text = (
        TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "cli" / "__init__.py"
    ).read_text(encoding="utf-8")
    assert "cmd_ai_eval_list" in text
    assert "cmd_ai_eval_run" in text


def test_pyproject_ai_eval_extra() -> None:
    text = (TEMPLATE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "ai-eval" in text
    assert "ragas" in text
    assert "deepeval" in text
