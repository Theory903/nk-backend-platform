from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from {{cookiecutter.project_name}}.ai.llm import (
    AssistantReply,
    ChatModel,
    Message,
)
from {{cookiecutter.project_name}}.agents.budgets import Budget, BudgetTracker
from {{cookiecutter.project_name}}.agents.guardrails import Guardrails
from {{cookiecutter.project_name}}.agents.tools import ToolRegistry


ApprovalHook = Callable[
    [list[Message]],
    Awaitable[None],
]


@dataclass(slots=True)
class AgentResult:
    """Stable result contract shared by NK runtimes."""

    content: str | None
    trace: list[tuple[Any, ...]] = field(default_factory=list)
    transcript: list[Message] = field(default_factory=list)
    steps: int = 0


class LoopRuntime:
    """
    Explicit NK agent runtime.

    This runtime remains useful as the lightweight execution path while
    GraphRuntime provides LangGraph orchestration.

    Responsibilities:
    - model invocation
    - tool dispatch
    - guardrail enforcement
    - budget enforcement
    - optional human approval
    - transcript/trace collection
    """

    __slots__ = (
        "_model",
        "_tools",
        "_guardrails",
        "_budget",
        "_system_prompt",
        "_on_step",
    )

    def __init__(
        self,
        model: ChatModel,
        tools: ToolRegistry,
        *,
        budget: Budget | None = None,
        guardrails: Guardrails | None = None,
        system_prompt: str = "You are a helpful agent.",
        on_step: ApprovalHook | None = None,
    ) -> None:
        if model is None:
            raise ValueError("model cannot be None")

        if tools is None:
            raise ValueError("tools cannot be None")

        if not system_prompt.strip():
            raise ValueError(
                "system_prompt cannot be empty"
            )

        self._model = model
        self._tools = tools
        self._guardrails = guardrails or Guardrails()
        self._budget = BudgetTracker(
            budget or Budget()
        )
        self._system_prompt = system_prompt
        self._on_step = on_step

    @property
    def budget(self) -> BudgetTracker:
        return self._budget

    @property
    def tools(self) -> ToolRegistry:
        return self._tools

    async def dispatch(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> str:
        """
        Guard-check and execute a tool.

        Guardrails are enforced here rather than inside ToolRegistry so the
        same registry can safely be reused by multiple runtimes.
        """
        denial = self._guardrails.check(name)

        if denial is not None:
            return denial

        return await self._tools.dispatch(
            name,
            arguments,
        )

    async def run(
        self,
        task: str,
    ) -> AgentResult:
        """Execute the agent until a final answer is produced."""
        task = task.strip()

        if not task:
            raise ValueError("task cannot be empty")

        messages = self._initial_messages(task)
        trace: list[tuple[Any, ...]] = []
        specs = self._tools.specs()

        while True:
            self._budget.step()

            if self._on_step is not None:
                await self._on_step(messages.copy())

            reply = await self._model.complete(
                messages,
                tools=specs,
            )

            if not isinstance(reply, AssistantReply):
                raise TypeError(
                    "ChatModel.complete() must return AssistantReply"
                )

            messages.append(
                self._assistant_message(reply)
            )

            if not reply.tool_calls:
                trace.append(("final",))

                return AgentResult(
                    content=reply.content,
                    trace=trace,
                    transcript=messages,
                    steps=self._budget.steps_used,
                )

            for call in reply.tool_calls:
                outcome = await self.dispatch(
                    call.name,
                    call.arguments,
                )

                trace.append(
                    (
                        "tool",
                        call.name,
                    )
                )

                messages.append(
                    Message(
                        role="tool",
                        content=outcome,
                        tool_call_id=call.id,
                        name=call.name,
                    )
                )

    @staticmethod
    def _initial_messages(
        task: str,
    ) -> list[Message]:
        return [
            Message(
                role="system",
                content=task if False else "",
            )
        ]

    def _assistant_message(
        self,
        reply: AssistantReply,
    ) -> Message:
        """
        Convert the model response into an assistant transcript message.

        Tool calls are preserved as structured JSON when the underlying
        Message contract has no dedicated tool-call field.
        """
        calls = [
            {
                "id": call.id,
                "name": call.name,
                "arguments": call.arguments,
            }
            for call in reply.tool_calls
        ]

        content = reply.content or ""

        if calls:
            tool_payload = json.dumps(
                calls,
                ensure_ascii=False,
                separators=(",", ":"),
            )

            content = (
                f"{content}\n{tool_payload}"
                if content
                else tool_payload
            )

        return Message(
            role="assistant",
            content=content,
        )