"""Unit tests for the central tool gateway (P4)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from {{cookiecutter.project_name}}.agents.security import ToolPolicy
from {{cookiecutter.project_name}}.agents.tool_gateway import ToolGateway
from {{cookiecutter.project_name}}.agents.tools import AgentTool, ToolRegistry
from {{cookiecutter.project_name}}.platform.contracts import Scope, ToolRisk


def _scope() -> Scope:
    return Scope(principal_id="user-1", organization_id="org-1")


def _echo_tool() -> AgentTool:
    async def echo(message: str) -> str:
        return message

    return AgentTool(
        name="echo",
        description="Echo input",
        fn=echo,
        parameters={
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    )


@pytest.mark.asyncio
async def test_gateway_invokes_registered_tool() -> None:
    registry = ToolRegistry()
    registry.register(_echo_tool())
    gateway = ToolGateway(registry)

    result = await gateway.invoke("echo", {"message": "hi"}, _scope())

    assert result.ok is True
    assert result.output == "hi"


@pytest.mark.asyncio
async def test_gateway_denies_unknown_tool() -> None:
    gateway = ToolGateway(ToolRegistry())

    result = await gateway.invoke("missing", {}, _scope())

    assert result.ok is False
    assert result.error_code == "not_found"


@pytest.mark.asyncio
async def test_gateway_enforces_denied_policy() -> None:
    registry = ToolRegistry()
    registry.register(_echo_tool())
    policy = ToolPolicy(denied_tools=frozenset({"echo"}))
    gateway = ToolGateway(registry, policy=policy)

    result = await gateway.invoke("echo", {"message": "hi"}, _scope())

    assert result.ok is False
    assert result.error_code == "policy_denied"


@pytest.mark.asyncio
async def test_gateway_emits_audit_on_success() -> None:
    registry = ToolRegistry()
    registry.register(_echo_tool())
    gateway = ToolGateway(registry)

    with patch(
        "{{cookiecutter.project_name}}.agents.tool_gateway.emit_audit",
        new_callable=AsyncMock,
    ) as emit:
        await gateway.invoke("echo", {"message": "hi"}, _scope())

    emit.assert_awaited()
    assert emit.await_args.kwargs["outcome"] == "success"


def test_register_many_rejects_duplicate_in_batch() -> None:
    registry = ToolRegistry()
    tools = [
        AgentTool(
            name="dup",
            description="A",
            fn=lambda: None,
            parameters={"type": "object", "properties": {}},
        ),
        AgentTool(
            name="dup",
            description="B",
            fn=lambda: None,
            parameters={"type": "object", "properties": {}},
        ),
    ]

    with pytest.raises(ValueError, match="duplicate tool names"):
        registry.register_many(tools)


def test_register_many_rejects_conflict_without_partial_register() -> None:
    registry = ToolRegistry()
    registry.register(_echo_tool())
    tools = [
        AgentTool(
            name="echo",
            description="Echo clone",
            fn=lambda: None,
            parameters={"type": "object", "properties": {}},
        ),
        AgentTool(
            name="new_tool",
            description="New",
            fn=lambda: None,
            parameters={"type": "object", "properties": {}},
        ),
    ]

    with pytest.raises(ValueError, match="already registered"):
        registry.register_many(tools)

    assert "new_tool" not in registry.names()


def test_load_tool_policy_manifest_defaults() -> None:
    from {{cookiecutter.project_name}}.agents.tool_policy import load_tool_policy_manifest

    manifest = load_tool_policy_manifest()

    assert manifest.policy.high_risk_requires_approval is True
    assert manifest.mcp_servers == ()
