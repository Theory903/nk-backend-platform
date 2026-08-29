from __future__ import annotations

import inspect
from typing import Any

from langchain_core.tools import StructuredTool
from langgraph.prebuilt import create_react_agent

from {{cookiecutter.project_name}}.agents.loop import AgentResult
from {{cookiecutter.project_name}}.agents.tools import AgentTool, ToolRegistry


DEFAULT_SYSTEM_PROMPT = "You are a helpful agent."


class GraphRuntime:
    """
    LangGraph-backed agent runtime.

    NK owns:
    - AgentTool / ToolRegistry
    - AgentResult
    - application-level contracts

    LangChain/LangGraph owns:
    - model/tool orchestration
    - graph execution
    - checkpointing
    - interrupts
    - streaming
    """

    __slots__ = (
        "_agent",
        "_checkpointer",
    )

    def __init__(
        self,
        model: Any,
        tools: ToolRegistry,
        *,
        checkpointer: Any = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        if model is None:
            raise ValueError("model cannot be None")

        if not system_prompt.strip():
            raise ValueError("system_prompt cannot be empty")

        self._checkpointer = checkpointer

        lc_tools = [
            self._adapt_tool(tool)
            for tool in tools.all()
        ]

        kwargs: dict[str, Any] = {
            "prompt": system_prompt,
        }
        if checkpointer is not None:
            kwargs["checkpointer"] = checkpointer

        self._agent = create_react_agent(model, lc_tools, **kwargs)

    async def run(
        self,
        task: str,
        *,
        thread_id: str = "default",
    ) -> AgentResult:
        """
        Execute one graph-backed agent run.

        A thread_id is required when checkpoint persistence is enabled.
        """
        task = task.strip()

        if not task:
            raise ValueError("task cannot be empty")

        config = self._build_config(thread_id)

        state = await self._agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": task,
                    }
                ]
            },
            config=config,
        )

        return self._to_agent_result(state)

    async def stream(
        self,
        task: str,
        *,
        thread_id: str = "default",
    ):
        """
        Stream graph updates.

        Consumers can use this for UI/token/tool observability without
        coupling themselves to LangGraph's internal state representation.
        """
        task = task.strip()

        if not task:
            raise ValueError("task cannot be empty")

        config = self._build_config(thread_id)

        async for event in self._agent.astream(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": task,
                    }
                ]
            },
            config=config,
            stream_mode="updates",
        ):
            yield event

    def _build_config(
        self,
        thread_id: str,
    ) -> dict[str, Any] | None:
        if self._checkpointer is None:
            return None

        thread_id = thread_id.strip()

        if not thread_id:
            raise ValueError(
                "thread_id cannot be empty when "
                "checkpointing is enabled"
            )

        return {
            "configurable": {
                "thread_id": thread_id,
            }
        }

    @staticmethod
    def _adapt_tool(
        agent_tool: AgentTool,
    ) -> StructuredTool:
        """
        Adapt an NK AgentTool to LangChain's StructuredTool.

        The NK tool remains the source of truth; LangChain is only the
        execution adapter.
        """
        fn = agent_tool.fn

        if inspect.iscoroutinefunction(fn):
            return StructuredTool.from_function(
                coroutine=fn,
                name=agent_tool.name,
                description=agent_tool.description,
            )

        return StructuredTool.from_function(
            func=fn,
            name=agent_tool.name,
            description=agent_tool.description,
        )

    @staticmethod
    def _to_agent_result(
        state: dict[str, Any],
    ) -> AgentResult:
        messages = state.get("messages", [])

        if not messages:
            return AgentResult(
                content="",
                trace=[("final",)],
                transcript=[],
                steps=1,
            )

        transcript: list[Any] = []
        trace: list[tuple] = []

        for message in messages:
            role = _message_role(message)
            content = _message_content(message)

            if content:
                transcript.append(
                    {
                        "role": role,
                        "content": content,
                    }
                )

            if role == "tool":
                trace.append(
                    (
                        "tool",
                        getattr(message, "name", ""),
                    )
                )

            elif role == "assistant":
                trace.append(("assistant",))

        final_content = _message_content(messages[-1])

        trace.append(("final",))

        return AgentResult(
            content=final_content,
            trace=trace,
            transcript=transcript,
            steps=len(trace),
        )


def _message_role(message: Any) -> str:
    """Normalize LangChain message objects into stable roles."""
    role = getattr(message, "type", None)

    if role == "human":
        return "user"

    if role == "ai":
        return "assistant"

    if role == "tool":
        return "tool"

    if role == "system":
        return "system"

    return str(role or "unknown")


def _message_content(message: Any) -> str:
    """Normalize LangChain message content into a string."""
    content = getattr(message, "content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []

        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")

                if text is not None:
                    parts.append(str(text))

        return "".join(parts)

    return str(content)


__all__ = [
    "GraphRuntime",
]