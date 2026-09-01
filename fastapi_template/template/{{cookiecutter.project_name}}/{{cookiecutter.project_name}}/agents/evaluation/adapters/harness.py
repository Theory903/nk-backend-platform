"""Harness-backed evaluation adapter (P15)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from {{cookiecutter.project_name}}.agents.evaluation import EvalCase, EvalConfig, EvalReport
from {{cookiecutter.project_name}}.agents.evaluation.adapters.base import EvalAdapter
from {{cookiecutter.project_name}}.agents.harness import (
    HarnessMode,
    HarnessScenario,
    ScenarioRunner,
    load_scenarios_yaml,
)


class HarnessEvalAdapter(EvalAdapter):
    """Run evaluation through the NK harness scenario runner."""

    @property
    def name(self) -> str:
        return "harness"

    @property
    def description(self) -> str:
        return "NK harness scenarios with trajectory capture"

    @classmethod
    def is_available(cls) -> bool:
        return True

    async def run(
        self,
        cases: Sequence[EvalCase],
        runner: Any,
        *,
        config: EvalConfig | None = None,
        scenarios_path: str | Path | None = None,
        model: Any | None = None,
        tools: Any | None = None,
        **kwargs: Any,
    ) -> EvalReport:
        if scenarios_path is not None:
            scenarios = load_scenarios_yaml(scenarios_path)
        else:
            scenarios = [
                HarnessScenario(
                    name="inline",
                    cases=tuple(cases),
                ),
            ]
        if model is None:
            raise ValueError("harness adapter requires model= for ScenarioRunner")
        scenario_runner = ScenarioRunner(
            model,
            tools=tools,
            mode=HarnessMode.RUN,
        )
        harness_report = await scenario_runner.run_scenarios(
            scenarios,
            config=config,
        )
        return harness_report.eval


__all__ = ["HarnessEvalAdapter"]
