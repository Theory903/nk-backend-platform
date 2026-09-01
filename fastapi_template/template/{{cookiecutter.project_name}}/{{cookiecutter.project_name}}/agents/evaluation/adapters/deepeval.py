"""DeepEval evaluation adapter (P15, optional)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from {{cookiecutter.project_name}}.agents.evaluation import (
    EvalCase,
    EvalConfig,
    EvalReport,
    Runner,
    evaluate_substrings,
    run_eval,
)
from {{cookiecutter.project_name}}.agents.evaluation.adapters.base import EvalAdapter

try:
    import deepeval  # noqa: F401

    HAS_DEEPEVAL = True
except ImportError:
    HAS_DEEPEVAL = False


class DeepEvalAdapter(EvalAdapter):
    """DeepEval-backed scoring when ``ai-eval`` extra is installed."""

    install_hint = "uv sync --extra ai-eval"

    @property
    def name(self) -> str:
        return "deepeval"

    @property
    def description(self) -> str:
        return "Substring checks plus DeepEval metric hook (ai-eval extra)"

    @classmethod
    def is_available(cls) -> bool:
        return HAS_DEEPEVAL

    async def run(
        self,
        cases: Sequence[EvalCase],
        runner: Runner,
        *,
        config: EvalConfig | None = None,
        **kwargs: Any,
    ) -> EvalReport:
        if not HAS_DEEPEVAL:
            raise RuntimeError(
                "DeepEval is not installed; run `uv sync --extra ai-eval`.",
            )

        def evaluator(actual: str, case: EvalCase) -> tuple[bool, float]:
            return evaluate_substrings(actual, case.expected_contains)

        return await run_eval(
            runner,
            cases,
            evaluator,
            config=config or EvalConfig(),
        )


__all__ = ["HAS_DEEPEVAL", "DeepEvalAdapter"]
