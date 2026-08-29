"""MCP -> NK ToolRegistry bridge.

Transport-agnostic adapter for MCP sessions.

The MCP session lifecycle remains owned by the caller. This module only
discovers MCP tools and exposes them through NK's canonical AgentTool
interface.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from {{cookiecutter.project_name}}.agents.tools import AgentTool, ToolRegistry


@dataclass(frozen=True, slots=True)
class McpToolSpec:
    """Normalized MCP tool metadata."""

    name: str
    description: str
    parameters: dict[str, Any]


SessionLike = Any
ToolRunner = Callable[
    [str, dict[str, Any]],
    Any | Awaitable[Any],
]


class McpToolBridge:
    """
    Register MCP server tools into the NK ToolRegistry.

    NK remains the canonical tool abstraction.

        MCP server
            ↓
        McpToolBridge
            ↓
        AgentTool
            ↓
        ToolRegistry
            ↓
        LoopRuntime / LangGraph
    """

    __slots__ = ("_registry",)

    def __init__(self, registry: ToolRegistry) -> None:
        if registry is None:
            raise ValueError("registry cannot be None")

        self._registry = registry

    async def register_session(
        self,
        session: SessionLike,
        runner: ToolRunner,
        *,
        prefix: str = "",
    ) -> list[str]:
        """
        Discover and register all tools exposed by an MCP session.

        `runner` owns the actual MCP call_tool transport.
        """
        if session is None:
            raise ValueError("session cannot be None")

        if not callable(runner):
            raise TypeError("runner must be callable")

        prefix = _normalize_prefix(prefix)

        listing = await _maybe_await(
            session.list_tools()
        )

        tools = getattr(listing, "tools", None)

        if tools is None:
            raise TypeError(
                "MCP list_tools() response does not contain tools"
            )

        registered: list[str] = []

        # Validate the complete batch before mutating the registry.
        prepared: list[AgentTool] = []

        for tool in tools:
            prepared.append(
                _remote_agent_tool(
                    prefix=prefix,
                    tool=tool,
                    runner=runner,
                )
            )

        names = [tool.name for tool in prepared]

        if len(names) != len(set(names)):
            raise ValueError(
                "MCP session returned duplicate tool names: "
                + ", ".join(names)
            )

        self._registry.register_many(prepared)

        registered.extend(names)

        return registered


def _remote_agent_tool(
    *,
    prefix: str,
    tool: Any,
    runner: ToolRunner,
) -> AgentTool:
    """Convert an MCP tool definition into an NK AgentTool."""
    original_name = getattr(tool, "name", None)

    if not isinstance(original_name, str) or not original_name.strip():
        raise ValueError(
            "MCP tool has no valid name"
        )

    original_name = original_name.strip()
    name = f"{prefix}{original_name}"

    description = (
        getattr(tool, "description", None)
        or ""
    ).strip()

    parameters = getattr(
        tool,
        "inputSchema",
        None,
    )

    if not isinstance(parameters, Mapping):
        parameters = {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
    else:
        parameters = dict(parameters)

    async def invoke(
        **arguments: Any,
    ) -> str:
        try:
            result = runner(
                original_name,
                arguments,
            )

            result = await _maybe_await(result)

            return _serialize_mcp_result(result)

        except Exception as exc:
            raise RuntimeError(
                f"MCP tool '{original_name}' failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    return AgentTool(
        name=name,
        description=description
        or f"MCP tool: {original_name}",
        fn=invoke,
        parameters=parameters,
    )


async def _maybe_await(value: Any) -> Any:
    """Resolve sync or async MCP/client operations."""
    if inspect.isawaitable(value):
        return await value

    return value


def _serialize_mcp_result(result: Any) -> str:
    """
    Convert an MCP CallToolResult into a stable model-facing string.

    Text content is preferred. Structured MCP output is preserved as JSON.
    """
    content = getattr(result, "content", None)

    if content:
        text_parts: list[str] = []

        for block in content:
            if getattr(block, "type", None) == "text":
                text = getattr(block, "text", None)

                if text:
                    text_parts.append(str(text))

        if text_parts:
            return "\n".join(text_parts)

    structured = getattr(
        result,
        "structuredContent",
        None,
    )

    if structured is not None:
        return json.dumps(
            structured,
            ensure_ascii=False,
            default=str,
        )

    if hasattr(result, "model_dump"):
        return json.dumps(
            result.model_dump(),
            ensure_ascii=False,
            default=str,
        )

    if isinstance(result, (dict, list, tuple)):
        return json.dumps(
            result,
            ensure_ascii=False,
            default=str,
        )

    return str(result)


def _normalize_prefix(prefix: str) -> str:
    if not isinstance(prefix, str):
        raise TypeError("prefix must be a string")

    return prefix.strip()


__all__ = [
    "McpToolBridge",
    "McpToolSpec",
    "SessionLike",
    "ToolRunner",
]