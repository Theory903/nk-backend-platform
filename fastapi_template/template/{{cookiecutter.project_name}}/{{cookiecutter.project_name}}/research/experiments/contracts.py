"""Experiment loop contracts — hypothesis → mutate → evaluate → keep/revert (P26)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ExperimentTarget(StrEnum):
    PROMPT = "prompt"
    SKILL = "skill"
    ROUTING = "routing"
    RAG = "rag"
    AGENT = "agent"


class ExperimentOutcome(StrEnum):
    KEPT = "kept"
    REVERTED = "reverted"
    FAILED = "failed"


class MutationSpec(BaseModel):
    """Declarative mutation applied to a runtime configuration."""

    strategy: str = Field(min_length=1)
    changes: dict[str, Any] = Field(default_factory=dict)


class Hypothesis(BaseModel):
    """An optimizable hypothesis bound to a target and metric."""

    id: str = Field(min_length=1)
    description: str = ""
    target: ExperimentTarget = ExperimentTarget.AGENT
    target_ref: str = "loop"
    metric: str = "pass_rate"
    min_delta: float = 0.0
    mutation: MutationSpec = Field(
        default_factory=lambda: MutationSpec(strategy="noop"),
    )


class ExperimentRecord(BaseModel):
    """One completed experiment trial."""

    experiment_id: str = Field(default_factory=lambda: uuid4().hex)
    hypothesis_id: str
    baseline_score: float
    candidate_score: float
    outcome: ExperimentOutcome
    mutation: MutationSpec
    detail: str = ""


class LeaderboardEntry(BaseModel):
    """Aggregated best result for a hypothesis."""

    hypothesis_id: str
    best_score: float
    experiments: int
    kept: int
    last_outcome: ExperimentOutcome


__all__ = [
    "ExperimentOutcome",
    "ExperimentRecord",
    "ExperimentTarget",
    "Hypothesis",
    "LeaderboardEntry",
    "MutationSpec",
]
