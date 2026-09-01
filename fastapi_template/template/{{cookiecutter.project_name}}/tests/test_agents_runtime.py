import pytest

from {{cookiecutter.project_name}}.ai.llm import AssistantReply, ToolCall
from {{cookiecutter.project_name}}.agents.budgets import Budget, BudgetExhausted
from {{cookiecutter.project_name}}.agents.guardrails import Guardrails
from {{cookiecutter.project_name}}.agents.loop import LoopRuntime
from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.platform.contracts import Scope, ToolRisk
from tests._fakes import FakeChatModel

pytest.importorskip("langgraph.prebuilt", reason="graph runtime needs langgraph")

from {{cookiecutter.project_name}}.agents.graph import GraphRuntime  # noqa: E402


@agent_tool(description="Echo the given text back.")
def echo(text: str) -> str:
    return f"echo:{text}"


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(echo)
    return registry


def _scope() -> Scope:
    return Scope(principal_id="test-user", organization_id="test-org")


async def test_loop_executes_tool_then_answers() -> None:
    """
    Scripted model drives one tool call then a final answer.
    """
    model = FakeChatModel(
        [
            AssistantReply(
                content=None,
                tool_calls=[ToolCall(id="c1", name="echo", arguments={"text": "hi"})],
            ),
            AssistantReply(content="finished", tool_calls=[]),
        ],
    )
    runtime = LoopRuntime(
        model=model,
        tools=_registry(),
        budget=Budget(max_steps=5),
        scope=_scope(),
    )

    result = await runtime.run(task="use the tool")

    assert result.content == "finished"
    assert result.trace == [("tool", "echo"), ("final",)]
    assert "echo:hi" in result.transcript[-2].content


async def test_budget_exhaustion_halts_loop() -> None:
    """
    A model that never stops calling tools hits the step ceiling.
    """
    endless = [
        AssistantReply(
            content=None,
            tool_calls=[ToolCall(id=f"c{i}", name="echo", arguments={"text": "x"})],
        )
        for i in range(10)
    ]
    runtime = LoopRuntime(
        model=FakeChatModel(endless),
        tools=_registry(),
        budget=Budget(max_steps=2),
        scope=_scope(),
    )

    with pytest.raises(BudgetExhausted):
        await runtime.run(task="loop forever")


async def test_guardrail_denial_blocks_execution() -> None:
    """
    Denied tools never run; the model sees a denial observation instead.
    """
    calls: list[str] = []

    @agent_tool(description="Dangerous op.")
    def dangerous() -> str:
        calls.append("ran")
        return "boom"

    registry = ToolRegistry()
    registry.register(dangerous)
    guardrails = Guardrails(deny={"dangerous"})
    model = FakeChatModel(
        [
            AssistantReply(content="ok", tool_calls=[]),
        ],
    )
    runtime = LoopRuntime(
        model=model,
        tools=registry,
        budget=Budget(max_steps=3),
        guardrails=guardrails,
        scope=_scope(),
    )

    outcome = await runtime.dispatch("dangerous", {})

    assert outcome == "DENIED: tool 'dangerous' is not allowed"
    assert calls == []


async def test_loop_requires_scope_even_for_final_answers() -> None:
    model = FakeChatModel([AssistantReply(content="ok", tool_calls=[])])

    with pytest.raises(ValueError, match="scope is required"):
        LoopRuntime(model=model, tools=ToolRegistry())


async def test_high_risk_tool_requires_approval() -> None:
    @agent_tool(description="Irreversible operation.", risk=ToolRisk.HIGH)
    def irreversible() -> str:
        return "done"

    registry = ToolRegistry()
    registry.register(irreversible)
    runtime = LoopRuntime(
        model=FakeChatModel([]),
        tools=registry,
        scope=_scope(),
    )

    with pytest.raises(PermissionError, match="requires approval"):
        await runtime.dispatch("irreversible", {})


async def test_graph_runtime_shares_registry_contract() -> None:
    """
    Graph runtime executes the same registered tool end to end.
    """
    from langchain_core.language_models.fake_chat_models import (
        GenericFakeChatModel,
    )
    from langchain_core.messages import AIMessage

    class ScriptedToolModel(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ANN003
            return self

    messages = iter(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "echo", "args": {"text": "g"}, "id": "gc1"},
                ],
            ),
            AIMessage(content="graph done"),
        ],
    )
    runtime = GraphRuntime(
        model=ScriptedToolModel(messages=messages),
        tools=_registry(),
        checkpointer=None,
    )

    result = await runtime.run(task="graph task")

    assert result.content == "graph done"
    tool_msg = result.transcript[-2]
    tool_content = getattr(tool_msg, "content", None)
    if tool_content is None and isinstance(tool_msg, dict):
        tool_content = tool_msg.get("content")
    assert tool_content is not None and "echo:g" in tool_content
