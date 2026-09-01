"""Harness scenario runner with trajectory capture (P14)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from {{cookiecutter.project_name}}.agents.evaluation import (
    EvalConfig,
    EvalReport,
    format_report,
)
from {{cookiecutter.project_name}}.agents.factory import AgentRuntimeFactory
from {{cookiecutter.project_name}}.agents.harness.fixtures import (
    FixtureReplayer,
    ToolFixture,
    fixture_path,
    load_fixture,
    save_fixture,
    trajectory_to_fixture,
)
from {{cookiecutter.project_name}}.agents.harness.scenarios import HarnessScenario
from {{cookiecutter.project_name}}.agents.harness.trajectory import Trajectory, TrajectoryCapture
from {{cookiecutter.project_name}}.agents.tools import ToolRegistry
from {{cookiecutter.project_name}}.platform.contracts import Scope


class HarnessMode(StrEnum):
    RUN = "run"
    RECORD = "record"
    REPLAY = "replay"


@dataclass(slots=True)
class CaseTrajectory:
    scenario: str
    case_name: str
    trajectory: Trajectory


@dataclass(slots=True)
class HarnessReport:
    """Evaluation report plus per-case trajectories."""

    mode: HarnessMode
    eval: EvalReport
    trajectories: list[CaseTrajectory] = field(default_factory=list)
    fixtures_written: list[str] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return self.eval.passed

    @property
    def failed(self) -> int:
        return self.eval.failed

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "total": self.eval.total,
            "passed": self.eval.passed,
            "failed": self.eval.failed,
            "pass_rate": self.eval.pass_rate,
            "avg_score": self.eval.avg_score,
            "duration_s": self.eval.duration_s,
            "fixtures_written": self.fixtures_written,
            "trajectories": [
                {
                    "scenario": item.scenario,
                    "case": item.case_name,
                    "trajectory": item.trajectory.to_dict(),
                }
                for item in self.trajectories
            ],
        }


class ScenarioRunner:
    """Run, record, or replay harness scenarios."""

    __slots__ = (
        "_model",
        "_tools",
        "_scope",
        "_mode",
        "_fixture_dir",
        "_gateway",
    )

    def __init__(
        self,
        model: Any,
        *,
        tools: ToolRegistry | None = None,
        scope: Scope | None = None,
        mode: HarnessMode = HarnessMode.RUN,
        fixture_dir: str | Path | None = None,
        gateway: Any | None = None,
    ) -> None:
        self._model = model
        self._tools = tools or ToolRegistry()
        self._scope = scope or Scope(
            principal_id="harness",
            organization_id="harness",
        )
        self._mode = mode
        self._fixture_dir = Path(fixture_dir or "tests/evals/fixtures")
        self._gateway = gateway

    async def run_scenarios(
        self,
        scenarios: list[HarnessScenario],
        *,
        config: EvalConfig | None = None,
    ) -> HarnessReport:
        from {{cookiecutter.project_name}}.agents.evaluation import (
            EvalResult,
            evaluate_substrings,
            check_trajectory,
        )
        import time

        config = config or EvalConfig(max_concurrency=2, timeout_s=120)
        _ = config  # reserved for future parallel case execution
        start = time.monotonic()
        results: list[EvalResult] = []
        trajectories: list[CaseTrajectory] = []
        fixtures_written: list[str] = []

        for scenario in scenarios:
            path = (
                Path(scenario.fixture_file)
                if scenario.fixture_file
                else fixture_path(self._fixture_dir, scenario.name)
            )
            fixture = (
                load_fixture(path)
                if self._mode is HarnessMode.REPLAY and path.is_file()
                else None
            )
            replayer = FixtureReplayer(fixture) if fixture is not None else None

            for case in scenario.cases:
                case_start = time.monotonic()
                capture = TrajectoryCapture()
                try:
                    tools = self._tools
                    if replayer is not None:
                        tools = _ReplayToolRegistry(self._tools, replayer)

                    agent = AgentRuntimeFactory.create(
                        scenario.runtime_mode,
                        model=self._model,
                        tools=tools,
                        scope=self._scope,
                        task=case.input,
                        gateway=self._gateway if replayer is None else None,
                        recorder=capture,
                    )
                    await capture.context_built(
                        task=case.input,
                        runtime_mode=scenario.runtime_mode,
                    )
                    raw = await agent.run(case.input)
                    content = str(getattr(raw, "content", raw) or "")
                    actual_tools = capture.trajectory.tools
                    passed, score = evaluate_substrings(
                        content,
                        case.expected_contains,
                    )
                    if passed and case.expected_tools:
                        passed = check_trajectory(actual_tools, case.expected_tools)
                    results.append(
                        EvalResult(
                            case=case,
                            passed=passed,
                            actual=content,
                            score=score,
                            duration_s=time.monotonic() - case_start,
                            actual_tools=actual_tools,
                        ),
                    )
                except Exception as exc:
                    results.append(
                        EvalResult(
                            case=case,
                            passed=False,
                            actual="",
                            score=0.0,
                            duration_s=time.monotonic() - case_start,
                            error=f"{type(exc).__name__}: {exc}",
                            execution_ok=False,
                        ),
                    )
                trajectories.append(
                    CaseTrajectory(
                        scenario=scenario.name,
                        case_name=case.name,
                        trajectory=capture.trajectory,
                    ),
                )
                if self._mode is HarnessMode.RECORD:
                    out_path = fixture_path(self._fixture_dir, scenario.name)
                    tool_fixture = trajectory_to_fixture(
                        scenario.name,
                        capture.trajectory,
                    )
                    save_fixture(out_path, tool_fixture)
                    if str(out_path) not in fixtures_written:
                        fixtures_written.append(str(out_path))

        duration = time.monotonic() - start
        total = len(results)
        passed = sum(item.passed for item in results)
        eval_report = EvalReport(
            total=total,
            passed=passed,
            failed=total - passed,
            avg_score=(sum(item.score for item in results) / total if total else 0.0),
            results=results,
            duration_s=duration,
        )
        return HarnessReport(
            mode=self._mode,
            eval=eval_report,
            trajectories=trajectories,
            fixtures_written=fixtures_written,
        )


class _ReplayToolRegistry(ToolRegistry):
    """ToolRegistry overlay that replays fixture responses."""

    __slots__ = ("_inner", "_replayer")

    def __init__(self, inner: ToolRegistry, replayer: FixtureReplayer) -> None:
        super().__init__(list(inner.all()))
        self._inner = inner
        self._replayer = replayer

    async def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        replayed = self._replayer.next_response(name, arguments)
        if replayed is not None:
            return replayed
        return await self._inner.dispatch(name, arguments)

    def specs(self) -> list[Any]:
        return self._inner.specs()


def run_scenarios_sync(
    scenarios: list[HarnessScenario],
    *,
    model: Any,
    tools: ToolRegistry | None = None,
    scope: Scope | None = None,
    mode: HarnessMode = HarnessMode.RUN,
    fixture_dir: str | Path | None = None,
    config: EvalConfig | None = None,
) -> HarnessReport:
    runner = ScenarioRunner(
        model,
        tools=tools,
        scope=scope,
        mode=mode,
        fixture_dir=fixture_dir,
    )
    return asyncio.run(
        runner.run_scenarios(scenarios, config=config),
    )


__all__ = [
    "CaseTrajectory",
    "HarnessMode",
    "HarnessReport",
    "ScenarioRunner",
    "format_report",
    "run_scenarios_sync",
]
