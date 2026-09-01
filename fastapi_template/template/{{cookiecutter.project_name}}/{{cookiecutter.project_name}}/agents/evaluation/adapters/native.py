"""NK-native evaluation adapter (P15)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from {{cookiecutter.project_name}}.agents.evaluation import (
    EvalCase,
    EvalConfig,
    EvalReport,
    Runner,
    run_substring_eval,
)
from {{cookiecutter.project_name}}.agents.evaluation.adapters.base import EvalAdapter


class NativeAdapter(EvalAdapter):
    """Deterministic substring + trajectory evaluation (always available)."""

    @property
    def name(self) -> str:
        return "native"

    @property
    def description(self) -> str:
        return "NK substring + tool trajectory checks"

    @classmethod
    def is_available(cls) -> bool:
        return True

    async def run(
        self,
        cases: Sequence[EvalCase],
        runner: Runner,
        *,
        config: EvalConfig | None = None,
        **kwargs: Any,
    ) -> EvalReport:
        return await run_substring_eval(runner, cases, config=config or EvalConfig())


__all__ = ["NativeAdapter"]
