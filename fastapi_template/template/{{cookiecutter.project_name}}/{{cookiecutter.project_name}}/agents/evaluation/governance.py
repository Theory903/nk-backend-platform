"""Durable-shaped evaluation, red-team, cost, and release gates."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from {{cookiecutter.project_name}}.agents.evaluation import EvalReport


class ReleaseDecision(StrEnum):
    PROMOTE = "promote"
    HOLD = "hold"
    ROLLBACK = "rollback"


@dataclass(frozen=True, slots=True)
class QualityThresholds:
    """Minimum quality and safety thresholds for promotion."""

    min_pass_rate: float = 0.95
    min_avg_score: float = 0.80
    max_error_count: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.min_pass_rate <= 1:
            raise ValueError("min_pass_rate must be between 0 and 1")
        if not 0 <= self.min_avg_score <= 1:
            raise ValueError("min_avg_score must be between 0 and 1")
        if self.max_error_count < 0:
            raise ValueError("max_error_count must be >= 0")


@dataclass(frozen=True, slots=True)
class RedTeamCase:
    """Adversarial input and the expected refusal/control behavior."""

    case_id: str
    prompt: str
    forbidden_output_markers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GateResult:
    """Auditable result of a release gate evaluation."""

    decision: ReleaseDecision
    reasons: tuple[str, ...] = ()
    metrics: dict[str, float] = field(default_factory=dict)


class QualityGate:
    """Apply deterministic promotion and rollback thresholds."""

    def __init__(self, thresholds: QualityThresholds | None = None) -> None:
        self.thresholds = thresholds or QualityThresholds()

    def evaluate(self, report: EvalReport) -> GateResult:
        reasons: list[str] = []
        metrics = {
            "pass_rate": report.pass_rate,
            "avg_score": report.avg_score,
            "errors": float(report.errors),
        }
        if report.pass_rate < self.thresholds.min_pass_rate:
            reasons.append("pass rate below promotion threshold")
        if report.avg_score < self.thresholds.min_avg_score:
            reasons.append("average score below promotion threshold")
        if report.errors > self.thresholds.max_error_count:
            reasons.append("evaluation errors exceed threshold")
        return GateResult(
            decision=ReleaseDecision.HOLD if reasons else ReleaseDecision.PROMOTE,
            reasons=tuple(reasons),
            metrics=metrics,
        )


@dataclass
class CostLedger:
    """Tenant/model cost attribution ledger for release and operations."""

    _totals: dict[tuple[str, str], float] = field(default_factory=dict)

    def record(self, organization_id: str, model: str, cost_usd: float) -> None:
        if cost_usd < 0:
            raise ValueError("cost_usd must be non-negative")
        key = (organization_id, model)
        self._totals[key] = self._totals.get(key, 0.0) + cost_usd

    def total(self, organization_id: str, model: str | None = None) -> float:
        return sum(
            amount
            for (org_id, model_name), amount in self._totals.items()
            if org_id == organization_id and (model is None or model_name == model)
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            f"{organization_id}:{model}": amount
            for (organization_id, model), amount in sorted(self._totals.items())
        }


__all__ = [
    "CostLedger",
    "GateResult",
    "QualityGate",
    "QualityThresholds",
    "RedTeamCase",
    "ReleaseDecision",
]
