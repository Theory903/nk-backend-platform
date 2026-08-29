"""Prompt evaluation gate helpers."""

from __future__ import annotations

from {{cookiecutter.project_name}}.ai.prompts.exceptions import PromptError
from {{cookiecutter.project_name}}.ai.prompts.models import PromptEvaluation


class PromptEvaluationError(PromptError):
    """Raised when an evaluation gate rejects promotion."""


class PromptEvaluator:
    """
    Lightweight gate for promoting aliases after eval.

    Full dataset runners live in agents/evaluation; this records scores
    and checks thresholds before candidate → production moves.
    """

    def __init__(
        self,
        *,
        min_score: float = 0.8,
        metric_thresholds: dict[str, float] | None = None,
    ) -> None:
        self.min_score = min_score
        self.metric_thresholds = metric_thresholds or {}

    def passes(self, evaluation: PromptEvaluation) -> bool:
        if evaluation.score < self.min_score:
            return False
        for metric, threshold in self.metric_thresholds.items():
            if evaluation.metrics.get(metric, 0.0) < threshold:
                return False
        return True

    def require_pass(self, evaluation: PromptEvaluation) -> None:
        if not self.passes(evaluation):
            raise PromptEvaluationError(
                f"evaluation failed for {evaluation.prompt_name}:v{evaluation.version} "
                f"score={evaluation.score} metrics={evaluation.metrics}"
            )
