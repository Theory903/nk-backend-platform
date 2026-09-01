"""Unified agent runtime factory (P3)."""

from __future__ import annotations

from typing import Any

from {{cookiecutter.project_name}}.ai.llm import ChatModel
from {{cookiecutter.project_name}}.agents.budgets import Budget
from {{cookiecutter.project_name}}.agents.guardrails import Guardrails
from {{cookiecutter.project_name}}.agents.loop import LoopRuntime
from {{cookiecutter.project_name}}.agents.routing import resolve_runtime_mode, runtime_mode_for_task
from {{cookiecutter.project_name}}.agents.runtime import CancellationToken
from {{cookiecutter.project_name}}.agents.security import SecurityPipeline
from {{cookiecutter.project_name}}.agents.supervisor import SupervisorRuntime
from {{cookiecutter.project_name}}.agents.tools import ToolRegistry
from {{cookiecutter.project_name}}.agents.types import AgentResult, RuntimeMode, WorkerSpec
from {{cookiecutter.project_name}}.platform.contracts import Scope


class AgentRuntimeFactory:
    """Build Loop, Graph, or Supervisor runtimes from one entry point."""

    @staticmethod
    def resolve_mode(
        mode: RuntimeMode | str = RuntimeMode.AUTO,
        *,
        task: str = "",
        tools: ToolRegistry | None = None,
        multi_agent: bool = False,
        prefer_graph: bool = False,
    ) -> RuntimeMode:
        tool_count = len(tools.all()) if tools is not None else 0
        if mode in (RuntimeMode.AUTO, "auto") and task and not multi_agent and not prefer_graph:
            return runtime_mode_for_task(task, tool_count=tool_count)
        return resolve_runtime_mode(
            mode,
            task=task,
            tool_count=tool_count,
            multi_agent=multi_agent,
            prefer_graph=prefer_graph,
        )

    @staticmethod
    def create(
        mode: RuntimeMode | str,
        *,
        model: ChatModel,
        tools: ToolRegistry,
        scope: Scope,
        task: str = "",
        budget: Budget | None = None,
        guardrails: Guardrails | None = None,
        security: SecurityPipeline | None = None,
        system_prompt: str = "You are a helpful agent.",
        checkpointer: Any = None,
        workers: list[WorkerSpec] | None = None,
        cancellation: CancellationToken | None = None,
        multi_agent: bool = False,
        prefer_graph: bool = False,
        gateway: Any | None = None,
        recorder: Any | None = None,
    ) -> LoopRuntime | SupervisorRuntime | Any:
        resolved = AgentRuntimeFactory.resolve_mode(
            mode,
            task=task,
            tools=tools,
            multi_agent=multi_agent,
            prefer_graph=prefer_graph,
        )

        if resolved is RuntimeMode.SUPERVISOR:
            return SupervisorRuntime(
                tools,
                workers=workers,
                scope=scope,
                guardrails=guardrails,
                budget=budget,
                security=security,
                cancellation=cancellation,
                gateway=gateway,
                recorder=recorder,
            )

        if resolved is RuntimeMode.GRAPH:
            from {{cookiecutter.project_name}}.agents.graph import GraphRuntime

            return GraphRuntime(
                model,
                tools,
                checkpointer=checkpointer,
                system_prompt=system_prompt,
            )

        return LoopRuntime(
            model,
            tools,
            budget=budget,
            guardrails=guardrails,
            system_prompt=system_prompt,
            scope=scope,
            security=security,
            cancellation=cancellation,
            gateway=gateway,
            recorder=recorder,
        )

    @staticmethod
    async def run(
        mode: RuntimeMode | str,
        task: str,
        *,
        model: ChatModel,
        tools: ToolRegistry,
        scope: Scope,
        **kwargs: Any,
    ) -> AgentResult:
        runtime = AgentRuntimeFactory.create(
            mode,
            model=model,
            tools=tools,
            scope=scope,
            task=task,
            **kwargs,
        )
        result = await runtime.run(task)
        if isinstance(result, AgentResult):
            if result.runtime_mode is RuntimeMode.LOOP and mode not in (
                RuntimeMode.LOOP,
                "loop",
            ):
                resolved = AgentRuntimeFactory.resolve_mode(
                    mode,
                    task=task,
                    tools=tools,
                )
                return AgentResult(
                    content=result.content,
                    trace=result.trace,
                    transcript=result.transcript,
                    steps=result.steps,
                    runtime_mode=resolved,
                )
            return result
        return AgentResult(content=str(result), runtime_mode=RuntimeMode.LOOP)


__all__ = ["AgentRuntimeFactory"]
