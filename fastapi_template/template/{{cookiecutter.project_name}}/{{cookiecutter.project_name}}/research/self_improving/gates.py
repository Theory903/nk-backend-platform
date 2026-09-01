"""Harness gate and canary decisions (P30)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from {{cookiecutter.project_name}}.agents.evaluation import EvalReport
from {{cookiecutter.project_name}}.research.self_improving.contracts import (
    CanaryDecision,
    ImprovementProposal,
    PipelineRun,
)


class HarnessGate:
    """Validate proposals against harness/eval before promotion."""

    __slots__ = ("_min_pass_rate",)

    def __init__(self, *, min_pass_rate: float = 0.8) -> None:
        self._min_pass_rate = min_pass_rate

    def evaluate(self, proposal: ImprovementProposal, report: EvalReport) -> PipelineRun:
        promoted = report.pass_rate >= self._min_pass_rate
        canary = CanaryDecision(
            proposal_id=proposal.id,
            promoted=promoted,
            rollout_ratio=0.1 if promoted else 0.0,
            reason=(
                f"pass_rate={report.pass_rate:.3f} "
                f"threshold={self._min_pass_rate:.3f}"
            ),
        )
        run = PipelineRun(
            id=uuid4().hex,
            proposal=proposal,
            canary=canary,
            outcome="promoted" if promoted else "rejected",
            detail="harness gate result",
        )
        return run


class CanaryPromoter:
    """Promote or rollback candidate changes by ratio."""

    __slots__ = ("_max_rollout",)

    def __init__(self, *, max_rollout: float = 1.0) -> None:
        self._max_rollout = max_rollout

    def promote(self, run: PipelineRun, *, ratio: float = 0.1) -> CanaryDecision:
        promoted = bool(run.canary.promoted) if run.canary else False
        rollout = min(max(ratio, 0.0), self._max_rollout) if promoted else 0.0
        decision = CanaryDecision(
            proposal_id=run.proposal.id,
            promoted=promoted,
            rollout_ratio=rollout,
            reason="promoted from harness gate" if promoted else "not promoted",
        )
        run.canary = decision
        run.outcome = "canary" if promoted else "rejected"
        return decision

    def rollback(self, run: PipelineRun, *, reason: str = "rollback requested") -> CanaryDecision:
        decision = CanaryDecision(
            proposal_id=run.proposal.id,
            promoted=False,
            rollout_ratio=0.0,
            reason=reason,
        )
        run.canary = decision
        run.outcome = "rolled_back"
        return decision


__all__ = ["CanaryPromoter", "HarnessGate"]
