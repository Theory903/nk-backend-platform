from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, get_type_hints

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, TypeAdapter

from {{cookiecutter.project_name}}.ai.llm import ToolSpec
from {{cookiecutter.project_name}}.platform.contracts import ToolRisk


@dataclass(frozen=True, slots=True)
class AgentTool:
    """NK canonical tool definition."""

    name: str
    description: str
    fn: Callable[..., Any]
    parameters: dict[str, Any]
    risk: ToolRisk = ToolRisk.LOW
    requires_approval: bool = False

    def as_langchain(self) -> StructuredTool:
        """Adapt the NK tool to LangChain/LangGraph."""
        return StructuredTool.from_function(
            coroutine=self.fn if inspect.iscoroutinefunction(self.fn) else None,
            func=self.fn if not inspect.iscoroutinefunction(self.fn) else None,
            name=self.name,
            description=self.description,
        )


def agent_tool(
    description: str,
    *,
    risk: ToolRisk = ToolRisk.LOW,
    requires_approval: bool = False,
) -> Callable[[Callable[..., Any]], AgentTool]:
    """Turn a typed Python function into an NK agent tool."""

    description = description.strip()

    if not description:
        raise ValueError("tool description cannot be empty")

    def wrap(fn: Callable[..., Any]) -> AgentTool:
        return AgentTool(
            name=fn.__name__,
            description=description,
            fn=fn,
            parameters=_schema_from_signature(fn),
            risk=risk,
            requires_approval=requires_approval,
        )

    return wrap


def _schema_from_signature(
    fn: Callable[..., Any],
) -> dict[str, Any]:
    """Generate JSON Schema from the function signature."""

    hints = get_type_hints(fn)
    signature = inspect.signature(fn)

    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, parameter in signature.parameters.items():
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            raise TypeError(
                f"tool '{fn.__name__}' cannot use *args or **kwargs"
            )

        annotation = hints.get(name, Any)

        properties[name] = TypeAdapter(
            annotation,
        ).json_schema()

        if parameter.default is inspect.Parameter.empty:
            required.append(name)
        else:
            properties[name]["default"] = parameter.default

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }

    if required:
        schema["required"] = required

    return schema


class ToolRegistry:
    """
    Canonical NK tool registry.

    LangGraph consumes the registry through `langchain_tools()`.
    NK runtimes can continue using `dispatch()`.
    """

    def __init__(
        self,
        tools: list[AgentTool] | None = None,
    ) -> None:
        self._tools: dict[str, AgentTool] = {}

        for tool in tools or []:
            self.register(tool)

    def register(self, tool: AgentTool) -> None:
        if tool.name in self._tools:
            raise ValueError(
                f"tool '{tool.name}' is already registered"
            )

        self._tools[tool.name] = tool

    def names(self) -> list[str]:
        return sorted(self._tools)

    def get(self, name: str) -> AgentTool | None:
        return self._tools.get(name)

    def require(self, name: str) -> AgentTool:
        tool = self._tools.get(name)

        if tool is None:
            raise KeyError(f"unknown tool '{name}'")

        return tool

    def all(self) -> list[AgentTool]:
        return [
            self._tools[name]
            for name in self.names()
        ]

    def specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
            )
            for tool in self.all()
        ]

    def langchain_tools(self) -> list[StructuredTool]:
        """Return tools ready for LangGraph/LangChain."""
        return [
            tool.as_langchain()
            for tool in self.all()
        ]

    async def dispatch(
        self,
        name: str,
        arguments: Mapping[str, Any],
    ) -> str:
        """Execute a tool directly through the NK runtime."""

        tool = self.require(name)

        result = tool.fn(**dict(arguments))

        if inspect.isawaitable(result):
            result = await result

        return _serialize_result(result)


def _serialize_result(result: Any) -> str:
    if isinstance(result, BaseModel):
        return result.model_dump_json()

    if isinstance(result, (dict, list, tuple)):
        return json.dumps(
            result,
            ensure_ascii=False,
            default=str,
        )

    if result is None:
        return "null"

    return str(result)