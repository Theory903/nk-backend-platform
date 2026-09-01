"""Promptfoo export adapter (P15)."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from {{cookiecutter.project_name}}.agents.evaluation import EvalCase, EvalConfig, EvalReport, Runner
from {{cookiecutter.project_name}}.agents.evaluation.adapters.base import EvalAdapter
from {{cookiecutter.project_name}}.agents.evaluation.adapters.native import NativeAdapter


class PromptfooAdapter(EvalAdapter):
    """
    Export NK cases to Promptfoo format and optionally invoke the CLI.

    Promptfoo is CLI-first; this adapter writes ``promptfoo.yaml`` and runs
    ``npx promptfoo eval`` when requested.
    """

    install_hint = "npm install -g promptfoo (optional CLI invocation)"

    @property
    def name(self) -> str:
        return "promptfoo"

    @property
    def description(self) -> str:
        return "Export cases to Promptfoo YAML + optional CLI eval"

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which("npx") is not None

    @staticmethod
    def export_cases(cases: Sequence[EvalCase], path: str | Path) -> Path:
        """Write a minimal Promptfoo config for the given cases."""
        out = Path(path)
        tests = []
        for case in cases:
            assert_block = []
            for token in case.expected_contains:
                assert_block.append({"type": "icontains", "value": token})
            tests.append(
                {
                    "vars": {"input": case.input},
                    "assert": assert_block or [{"type": "javascript", "value": "true"}],
                    "metadata": {"name": case.name, **dict(case.metadata)},
                },
            )
        payload = {
            "description": "NK harness export (P15)",
            "prompts": ["{{'{{'}}input{{'}}'}}"],
            "providers": ["echo"],
            "tests": tests,
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError("PyYAML is required for Promptfoo export.") from exc
        out.write_text(
            yaml.safe_dump(payload, sort_keys=False),
            encoding="utf-8",
        )
        return out

    async def run(
        self,
        cases: Sequence[EvalCase],
        runner: Runner,
        *,
        config: EvalConfig | None = None,
        export_path: str | Path | None = None,
        invoke_cli: bool = False,
        **kwargs: Any,
    ) -> EvalReport:
        export = self.export_cases(
            cases,
            export_path or Path("tests/evals/promptfoo.yaml"),
        )
        if invoke_cli and shutil.which("npx"):
            subprocess.run(
                ["npx", "promptfoo", "eval", "-c", str(export)],
                check=False,
            )
        return await NativeAdapter().run(cases, runner, config=config)


__all__ = ["PromptfooAdapter"]
