"""Unit tests for harness scenario runner (P14)."""

from __future__ import annotations

import pytest

from {{cookiecutter.project_name}}.agents.evaluation import EvalCase
from {{cookiecutter.project_name}}.agents.harness.fixtures import (
    ToolFixture,
    ToolFixtureCall,
    trajectory_to_fixture,
)
from {{cookiecutter.project_name}}.agents.harness.runner import HarnessMode, ScenarioRunner
from {{cookiecutter.project_name}}.agents.harness.scenarios import HarnessScenario
from {{cookiecutter.project_name}}.agents.harness.trajectory import TrajectoryCapture
from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.platform.contracts import Scope


class _FakeModel:
    async def complete(self, messages, tools=None):
        from {{cookiecutter.project_name}}.ai.llm import AssistantReply

        return AssistantReply(content="NK Backend OS agent ready.", tool_calls=[])


@agent_tool("Echo a message")
async def echo(message: str) -> str:
    return message


@pytest.mark.asyncio
async def test_scenario_runner_captures_trajectory() -> None:
    registry = ToolRegistry()
    registry.register(echo)
    scenario = HarnessScenario(
        name="echo-scenario",
        cases=(
            EvalCase(
                name="echo-case",
                input="say hi",
                expected_contains=("NK",),
            ),
        ),
    )
    runner = ScenarioRunner(_FakeModel(), tools=registry)
    report = await runner.run_scenarios([scenario])
    assert report.eval.total == 1
    assert report.eval.passed == 1
    assert len(report.trajectories) == 1
    assert report.trajectories[0].trajectory.steps


def test_trajectory_to_fixture_roundtrip() -> None:
    capture = TrajectoryCapture()
    import asyncio

    async def _record() -> None:
        await capture.tool_called(
            name="echo",
            arguments={"message": "hi"},
            output="hi",
            ok=True,
        )

    asyncio.run(_record())
    fixture = trajectory_to_fixture("demo", capture.trajectory)
    assert fixture.scenario == "demo"
    assert len(fixture.calls) == 1
    assert fixture.calls[0].name == "echo"


def test_replay_registry_uses_fixture() -> None:
    from {{cookiecutter.project_name}}.agents.harness.fixtures import FixtureReplayer
    from {{cookiecutter.project_name}}.agents.harness.runner import _ReplayToolRegistry

    registry = ToolRegistry()
    registry.register(echo)
    fixture = ToolFixture(
        scenario="demo",
        calls=[ToolFixtureCall(name="echo", arguments={"message": "x"}, output="fixed")],
    )
    replay = _ReplayToolRegistry(registry, FixtureReplayer(fixture))
    import asyncio

    async def _dispatch() -> str:
        return await replay.dispatch("echo", {"message": "x"})

    assert asyncio.run(_dispatch()) == "fixed"
