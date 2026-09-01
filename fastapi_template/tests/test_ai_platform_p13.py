"""Tests for P13 session runtime (events, replay, fork, resume)."""

from __future__ import annotations

from pathlib import Path

TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
)
AGENTS = TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "agents"


def test_p13_session_modules_exist() -> None:
    assert (AGENTS / "session_events.py").is_file()
    assert (AGENTS / "session_store.py").is_file()
    assert (AGENTS / "session_runtime.py").is_file()


def test_session_event_kinds_match_roadmap() -> None:
    text = (AGENTS / "session_events.py").read_text(encoding="utf-8")
    for kind in (
        "RunStarted",
        "ContextBuilt",
        "ModelCalled",
        "ToolCalled",
        "MemoryRead",
        "MemoryWrite",
        "ApprovalRequested",
        "RunCompleted",
    ):
        assert kind in text


def test_bootstrap_wires_session_runtime() -> None:
    text = (AGENTS / "bootstrap.py").read_text(encoding="utf-8")
    assert "build_session_runtime" in text
    assert "app.state.session_runtime" in text


def test_loop_emits_session_events() -> None:
    text = (AGENTS / "loop.py").read_text(encoding="utf-8")
    assert "_recorder" in text
    assert "tool_called" in text
    assert "model_called" in text


def test_agent_protocol_session_routes() -> None:
    text = (
        TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "web" / "api" / "agent_protocol.py"
    ).read_text(encoding="utf-8")
    assert "session_runtime" in text
    assert "/v1/runs/{run_id}/events" in text
    assert "/v1/runs/{run_id}/fork" in text
    assert "/v1/runs/{run_id}/resume" in text


def test_cli_session_commands() -> None:
    text = (
        TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "cli" / "__init__.py"
    ).read_text(encoding="utf-8")
    assert "cmd_ai_inspect" in text
    assert "cmd_ai_replay" in text
    assert "cmd_ai_fork" in text
    assert "cmd_ai_resume" in text
