"""Tests for P3 runtime routing ladder."""

from __future__ import annotations

import pytest

from {{cookiecutter.project_name}}.agents.routing import resolve_runtime_mode, runtime_mode_for_task
from {{cookiecutter.project_name}}.agents.runtime import CancellationToken, RuntimeCancelled
from {{cookiecutter.project_name}}.agents.types import RuntimeMode
from {{cookiecutter.project_name}}.ai.llm import AssistantReply
from {{cookiecutter.project_name}}.agents.budgets import Budget
from {{cookiecutter.project_name}}.agents.loop import LoopRuntime
from {{cookiecutter.project_name}}.agents.tools import ToolRegistry
from {{cookiecutter.project_name}}.platform.contracts import Scope
from tests._fakes import FakeChatModel


def test_resolve_supervisor_for_multi_agent_flag() -> None:
    mode = resolve_runtime_mode(
        RuntimeMode.AUTO,
        task="hello",
        multi_agent=True,
    )
    assert mode is RuntimeMode.SUPERVISOR


def test_runtime_mode_for_task_detects_supervisor_phrase() -> None:
    mode = runtime_mode_for_task("Use a team of agents to research this")
    assert mode is RuntimeMode.SUPERVISOR


def test_explicit_loop_mode() -> None:
    mode = resolve_runtime_mode("loop", task="x", tool_count=3)
    assert mode is RuntimeMode.LOOP


@pytest.mark.asyncio
async def test_loop_honours_cancellation_token() -> None:
    token = CancellationToken()
    token.cancel()
    runtime = LoopRuntime(
        model=FakeChatModel([AssistantReply(content="ok", tool_calls=[])]),
        tools=ToolRegistry(),
        budget=Budget(max_steps=3),
        scope=Scope(principal_id="u", organization_id="o"),
        cancellation=token,
    )
    with pytest.raises(RuntimeCancelled):
        await runtime.run("task")


def test_factory_module_exports() -> None:
    from {{cookiecutter.project_name}}.agents.factory import AgentRuntimeFactory

    mode = AgentRuntimeFactory.resolve_mode("auto", task="simple question")
    assert mode in {RuntimeMode.LOOP, RuntimeMode.GRAPH, RuntimeMode.SUPERVISOR}
