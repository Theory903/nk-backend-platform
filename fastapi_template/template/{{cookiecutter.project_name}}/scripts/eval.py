"""Run the generated golden evaluation dataset through the harness."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from {{cookiecutter.project_name}}.agents.evaluation import format_report
from {{cookiecutter.project_name}}.agents.harness import (
    HarnessMode,
    ScenarioRunner,
    load_scenarios_yaml,
)
from {{cookiecutter.project_name}}.agents.tools import ToolRegistry
from {{cookiecutter.project_name}}.ai.gateway.router import get_router
from {{cookiecutter.project_name}}.llm.features.registry import register_feature_tools
from {{cookiecutter.project_name}}.llm.features.runtime import get_or_create_runtime


async def _run(dataset: Path) -> int:
    scenarios = load_scenarios_yaml(dataset)
    registry = ToolRegistry()
    register_feature_tools(registry, get_or_create_runtime(None))
    runner = ScenarioRunner(
        get_router().model_for(),
        tools=registry,
        mode=HarnessMode.RUN,
        fixture_dir=dataset.parent / "fixtures",
    )
    report = await runner.run_scenarios(scenarios)
    print(format_report(report.eval))
    return 0 if report.failed == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args.dataset)))


if __name__ == "__main__":
    main()
