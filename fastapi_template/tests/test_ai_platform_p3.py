"""Tests for P3 agent runtime routing ladder."""

from __future__ import annotations

from pathlib import Path

TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
)
AGENTS = TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "agents"


def test_p3_runtime_modules_exist() -> None:
    assert (AGENTS / "types.py").is_file()
    assert (AGENTS / "routing.py").is_file()
    assert (AGENTS / "supervisor.py").is_file()
    assert (AGENTS / "factory.py").is_file()


def test_loop_supports_cancellation() -> None:
    text = (AGENTS / "loop.py").read_text(encoding="utf-8")
    assert "_check_cancelled" in text
    assert "CancellationToken" in text


def test_agent_protocol_accepts_runtime_mode() -> None:
    text = (
        TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "web" / "api" / "agent_protocol.py"
    ).read_text(encoding="utf-8")
    assert "runtime_mode" in text
    assert "AgentRuntimeFactory" in text


def test_supervisor_delegates_to_workers() -> None:
    text = (AGENTS / "supervisor.py").read_text(encoding="utf-8")
    assert "SupervisorRuntime" in text
    assert "LoopRuntime" in text
