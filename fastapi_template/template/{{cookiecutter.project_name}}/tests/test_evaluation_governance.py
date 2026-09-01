"""Tests for promotion thresholds and cost attribution."""

from __future__ import annotations

from {{cookiecutter.project_name}}.agents.evaluation import (
    EvalCase,
    EvalReport,
    EvalResult,
)
from {{cookiecutter.project_name}}.agents.evaluation.governance import (
    CostLedger,
    QualityGate,
    ReleaseDecision,
)


def _report(passed: bool) -> EvalReport:
    case = EvalCase(name="case", input="input")
    result = EvalResult(
        case=case,
        passed=passed,
        actual="output",
        score=1.0 if passed else 0.0,
    )
    return EvalReport(
        total=1,
        passed=int(passed),
        failed=int(not passed),
        avg_score=result.score,
        results=[result],
    )


def test_quality_gate_promotes_only_passing_reports() -> None:
    assert QualityGate().evaluate(_report(True)).decision is ReleaseDecision.PROMOTE
    held = QualityGate().evaluate(_report(False))
    assert held.decision is ReleaseDecision.HOLD
    assert held.reasons


def test_cost_ledger_is_attributed_by_tenant_and_model() -> None:
    ledger = CostLedger()
    ledger.record("org-1", "model-a", 0.25)
    ledger.record("org-1", "model-a", 0.75)
    ledger.record("org-2", "model-a", 10.0)

    assert ledger.total("org-1") == 1.0
    assert ledger.total("org-1", "model-a") == 1.0
    assert ledger.total("org-2") == 10.0
