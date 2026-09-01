"""Run the generated golden evaluation dataset through the agent adapter."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from {{cookiecutter.project_name}}.agents.evaluation import (
    EvalConfig,
    format_report,
    load_dataset_yaml,
    run_substring_eval,
)
from {{cookiecutter.project_name}}.agents.loop import LoopRuntime
from {{cookiecutter.project_name}}.agents.tools import ToolRegistry
from {{cookiecutter.project_name}}.platform.contracts import Scope
from {{cookiecutter.project_name}}.ai.gateway.router import get_router


async def _run(dataset: Path) -> int:
    cases = load_dataset_yaml(dataset)
    runtime = LoopRuntime(
        get_router().model_for(),
        ToolRegistry(),
        scope=Scope(principal_id="evaluation", organization_id="evaluation"),
    )
    report = await run_substring_eval(
        runtime.run,
        cases,
        config=EvalConfig(max_concurrency=2, timeout_s=120),
    )
    print(format_report(report))
    return 0 if report.failed == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args.dataset)))


if __name__ == "__main__":
    main()
