"""Self-improving loop contracts (P30)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class SignalKind(StrEnum):
    COST = "cost"
    LATENCY = "latency"
    TOOL_FAILURE = "tool_failure"
    EVAL_REGRESSION = "eval_regression"
    EVAL_IMPROVEMENT = "eval_improvement"


class TelemetrySignal(BaseModel):
    """One observed signal from metrics, harness, or experiments."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    kind: SignalKind
    score: float
    detail: str = ""
    source: str = "telemetry"


class ImprovementProposal(BaseModel):
    """Candidate improvement sourced from experiments or signals."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    hypothesis_id: str = ""
    title: str = ""
    mutation: dict[str, Any] = Field(default_factory=dict)
    expected_delta: float = 0.0
    signals: tuple[str, ...] = ()


class CanaryDecision(BaseModel):
    """Canary promotion or rollback outcome."""

    proposal_id: str
    promoted: bool
    rollout_ratio: float = 0.0
    reason: str = ""


class PipelineRun(BaseModel):
    """Single self-improving loop execution record."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    proposal: ImprovementProposal
    canary: CanaryDecision | None = None
    outcome: str = "started"
    detail: str = ""


__all__ = [
    "CanaryDecision",
    "ImprovementProposal",
    "PipelineRun",
    "SignalKind",
    "TelemetrySignal",
]
