"""Bootstrap external MCP servers into the tool registry (P4)."""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from typing import Any

from {{cookiecutter.project_name}}.agents.mcp_bridge import McpToolBridge
from {{cookiecutter.project_name}}.agents.tool_policy import McpServerSpec, load_tool_policy_manifest
from {{cookiecutter.project_name}}.agents.tools import ToolRegistry

logger = logging.getLogger(__name__)

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    HAS_MCP_SDK = True
except ImportError:
    HAS_MCP_SDK = False
    ClientSession = None  # type: ignore[assignment,misc]
    StdioServerParameters = None  # type: ignore[assignment,misc]
    stdio_client = None  # type: ignore[assignment,misc]


async def register_mcp_servers(
    registry: ToolRegistry,
    *,
    servers: tuple[McpServerSpec, ...] | None = None,
) -> tuple[list[str], Any | None]:
    """
    Connect configured MCP servers and register their tools.

    Returns registered tool names and an exit stack for lifespan cleanup.
    """
    manifest = load_tool_policy_manifest()
    specs = servers if servers is not None else manifest.mcp_servers
    enabled = [spec for spec in specs if spec.enabled]
    if not enabled:
        return [], None

    if not HAS_MCP_SDK:
        logger.warning(
            "MCP servers configured but mcp SDK not installed "
            "(uv sync --extra ai-platform)",
        )
        return [], None

    bridge = McpToolBridge(registry)
    registered: list[str] = []
    stack = AsyncExitStack()

    for spec in enabled:
        if spec.transport != "stdio":
            logger.warning("MCP transport %s not supported yet for %s", spec.transport, spec.name)
            continue
        if not spec.command:
            logger.warning("MCP server %s missing command", spec.name)
            continue
        try:
            params = StdioServerParameters(
                command=spec.command,
                args=list(spec.args),
            )
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            async def _runner(
                tool_name: str,
                arguments: dict[str, Any],
                *,
                _session: ClientSession = session,
            ) -> Any:
                return await _session.call_tool(tool_name, arguments)

            names = await bridge.register_session(
                session,
                lambda name, args: _runner(name, args),
                prefix=f"{spec.prefix}" if spec.prefix else f"{spec.name}_",
            )
            registered.extend(names)
            logger.info("registered %d MCP tools from %s", len(names), spec.name)
        except Exception:
            logger.exception("failed to bootstrap MCP server %s", spec.name)

    if not registered:
        await stack.aclose()
        return [], None
    return registered, stack


async def wire_mcp_servers(app: Any) -> None:
    """Register MCP tools on the application tool gateway during startup."""
    gateway = getattr(app.state, "tool_gateway", None)
    if gateway is None:
        return
    names, stack = await register_mcp_servers(gateway.registry)
    app.state.mcp_tool_names = names
    if stack is not None:
        app.state.mcp_exit_stack = stack


__all__ = ["HAS_MCP_SDK", "register_mcp_servers", "wire_mcp_servers"]
