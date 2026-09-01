"""Tests for P4 tool gateway wiring."""

from __future__ import annotations

from pathlib import Path

TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
)
AGENTS = TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "agents"


def test_p4_tool_gateway_modules_exist() -> None:
    assert (AGENTS / "tool_gateway.py").is_file()
    assert (AGENTS / "tool_policy.py").is_file()
    assert (AGENTS / "tool_policy.yaml").is_file()
    assert (AGENTS / "mcp_bootstrap.py").is_file()


def test_tool_registry_has_register_many() -> None:
    text = (AGENTS / "tools" / "__init__.py").read_text(encoding="utf-8")
    assert "def register_many" in text


def test_bootstrap_wires_tool_gateway() -> None:
    text = (AGENTS / "bootstrap.py").read_text(encoding="utf-8")
    assert "build_tool_gateway" in text
    assert "app.state.tool_gateway" in text


def test_loop_routes_through_gateway() -> None:
    text = (AGENTS / "loop.py").read_text(encoding="utf-8")
    assert "_gateway" in text
    assert "dispatch_string" in text


def test_agent_protocol_mcp_uses_gateway() -> None:
    text = (
        TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "web" / "api" / "agent_protocol.py"
    ).read_text(encoding="utf-8")
    assert "tool_gateway" in text
    assert "gateway.invoke" in text


def test_lifespan_wires_mcp_servers() -> None:
    text = (
        TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "web" / "lifespan.py"
    ).read_text(encoding="utf-8")
    assert "wire_mcp_servers" in text
    assert "mcp_exit_stack" in text


def test_cli_tools_list_command() -> None:
    text = (
        TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "cli" / "__init__.py"
    ).read_text(encoding="utf-8")
    assert "cmd_ai_tools_list" in text
    assert 'add_parser("tools"' in text


def test_settings_tool_policy_file() -> None:
    text = (
        TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "settings.py"
    ).read_text(encoding="utf-8")
    assert "tool_policy_file" in text
