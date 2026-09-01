"""Self-improving pipeline orchestrator (P30)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from {{cookiecutter.project_name}}.agents.evaluation import EvalCase, EvalReport
from {{cookiecutter.project_name}}.research.experiments.runtime import ExperimentRuntime
from {{cookiecutter.project_name}}.research.self_improving.contracts import (
    ImprovementProposal,
    PipelineRun,
    TelemetrySignal,
)
from {{cookiecutter.project_name}}.research.self_improving.gates import CanaryPromoter, HarnessGate
from {{cookiecutter.project_name}}.research.self_improving.telemetry import TelemetryBridge


class SelfImprovingPipeline:
    """Telemetry → experiment → harness → canary → record loop."""

    __slots__ = (
        "_telemetry",
        "_gate",
        "_canary",
        "_experiments",
        "_runs",
    )

    def __init__(
        self,
        *,
        experiment_runtime: ExperimentRuntime | None = None,
        min_pass_rate: float = 0.8,
        max_rollout: float = 1.0,
    ) -> None:
        self._telemetry = TelemetryBridge()
        self._gate = HarnessGate(min_pass_rate=min_pass_rate)
        self._canary = CanaryPromoter(max_rollout=max_rollout)
        self._experiments = experiment_runtime or ExperimentRuntime()
        self._runs: list[PipelineRun] = []

    @property
    def telemetry(self) -> TelemetryBridge:
        return self._telemetry

    @property
    def harness_gate(self) -> HarnessGate:
        return self._gate

    def propose_from_experiment(self, hypothesis_id: str) -> ImprovementProposal:
        hypothesis = self._experiments.hypothesis(hypothesis_id)
        return ImprovementProposal(
            hypothesis_id=hypothesis.id,
            title=hypothesis.description or hypothesis.id,
            mutation=hypothesis.mutation.changes,
            expected_delta=hypothesis.min_delta,
            signals=tuple(
                signal.id for signal in self._telemetry.signals()
                if signal.kind in {
                    "eval_regression",
                    "eval_improvement",
                    "cost",
                    "latency",
                }
            ),
        )

    async def evaluate_proposal(
        self,
        proposal: ImprovementProposal,
        cases: Sequence[EvalCase],
        *,
        base_config: dict[str, Any] | None = None,
    ) -> PipelineRun:
        experiment = await self._experiments.run(
            proposal.hypothesis_id,
            list(cases),
            base_config=base_config or {},
        )
        report = EvalReport(
            total=len(cases),
            passed=0,
            failed=len(cases),
            pass_rate=0.0,
            avg_score=0.0,
            duration_s=0.0,
        )
        # Use experiment score as proxy eval score.
        report = EvalReport(
            total=len(cases),
            passed=int(experiment.candidate_score * len(cases)),
            failed=len(cases) - int(experiment.candidate_score * len(cases)),
            pass_rate=float(experiment.candidate_score),
            avg_score=float(experiment.candidate_score),
            duration_s=0.0,
        )
        run = self._gate.evaluate(proposal, report)
        if run.canary and run.canary.promoted:
            self._canary.promote(run, ratio=run.canary.rollout_ratio)
        self._runs.append(run)
        return run

    def rollback(self, run_id: str, *, reason: str = "manual rollback") -> PipelineRun | None:
        for run in self._runs:
            if run.id == run_id:
                self._canary.rollback(run, reason=reason)
                return run
        return None

    def runs(self) -> tuple[PipelineRun, ...]:
        return tuple(self._runs)


def format_pipeline_report(pipeline: SelfImprovingPipeline) -> str:
    lines = ["Self-improving pipeline", "======================="]
    for run in pipeline.runs():
        status = run.outcome
        ratio = f"{run.canary.rollout_ratio:.0%}" if run.canary else "-"
        lines.append(
            f"{run.id} proposal={run.proposal.hypothesis_id} status={status} canary={ratio}",
        )
    return "\n".join(lines)


def build_self_improving_pipeline(
    *,
    experiment_runtime: ExperimentRuntime | None = None,
    min_pass_rate: float = 0.8,
) -> SelfImprovingPipeline:
    return SelfImprovingPipeline(
        experiment_runtime=experiment_runtime,
        min_pass_rate=min_pass_rate,
    )


__all__ = [
    "SelfImprovingPipeline",
    "build_self_improving_pipeline",
    "format_pipeline_report",
]
