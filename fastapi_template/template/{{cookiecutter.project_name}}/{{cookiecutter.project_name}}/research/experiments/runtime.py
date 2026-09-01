"""Experiment runtime — hypothesis → mutate → evaluate → keep/revert (P26)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from {{cookiecutter.project_name}}.agents.evaluation import EvalCase, EvalConfig, EvalReport
from {{cookiecutter.project_name}}.research.experiments.contracts import (
    ExperimentOutcome,
    ExperimentRecord,
    Hypothesis,
    LeaderboardEntry,
    MutationSpec,
)
from {{cookiecutter.project_name}}.research.experiments.mutations import apply_mutation, revert_mutation
from {{cookiecutter.project_name}}.research.experiments.store import ExperimentStore

_CATALOG_PATH = Path(__file__).with_name("catalog.yaml")
ScoreFn = Callable[[Sequence[EvalCase], dict[str, Any]], Awaitable[float]]


@lru_cache(maxsize=1)
def load_hypothesis_catalog() -> dict[str, Hypothesis]:
    if not _CATALOG_PATH.is_file():
        return {}
    payload = yaml.safe_load(_CATALOG_PATH.read_text(encoding="utf-8")) or {}
    raw = payload.get("hypotheses") or {}
    catalog: dict[str, Hypothesis] = {}
    for key, item in raw.items():
        if not isinstance(item, dict):
            continue
        data = dict(item)
        data.setdefault("id", key)
        mutation = data.get("mutation") or {}
        if isinstance(mutation, dict):
            data["mutation"] = MutationSpec.model_validate(mutation)
        catalog[key] = Hypothesis.model_validate(data)
    return catalog


class ExperimentRuntime:
    """Run bounded optimization experiments without touching production config."""

    __slots__ = ("_store", "_score_fn", "_base_config")

    def __init__(
        self,
        *,
        store: ExperimentStore | None = None,
        score_fn: ScoreFn | None = None,
        base_config: dict[str, Any] | None = None,
    ) -> None:
        self._store = store or ExperimentStore()
        self._score_fn = score_fn
        self._base_config = dict(base_config or {})

    @property
    def store(self) -> ExperimentStore:
        return self._store

    def hypotheses(self) -> dict[str, Hypothesis]:
        return load_hypothesis_catalog()

    def hypothesis(self, hypothesis_id: str) -> Hypothesis:
        catalog = self.hypotheses()
        if hypothesis_id not in catalog:
            raise KeyError(f"unknown hypothesis: {hypothesis_id}")
        return catalog[hypothesis_id]

    async def score(
        self,
        cases: Sequence[EvalCase],
        config: dict[str, Any],
    ) -> float:
        if self._score_fn is None:
            raise RuntimeError("experiment score_fn is not configured")
        return float(await self._score_fn(cases, config))

    async def run(
        self,
        hypothesis_id: str,
        cases: Sequence[EvalCase],
        *,
        base_config: dict[str, Any] | None = None,
    ) -> ExperimentRecord:
        hypothesis = self.hypothesis(hypothesis_id)
        baseline_config = dict(base_config or self._base_config)
        baseline = self._store.baseline_score(hypothesis_id)
        if baseline is None:
            baseline = await self.score(cases, baseline_config)
            self._store.set_baseline_score(hypothesis_id, baseline)

        candidate_config = apply_mutation(baseline_config, hypothesis.mutation)
        try:
            candidate = await self.score(cases, candidate_config)
        except Exception as exc:
            record = ExperimentRecord(
                hypothesis_id=hypothesis_id,
                baseline_score=baseline,
                candidate_score=0.0,
                outcome=ExperimentOutcome.FAILED,
                mutation=hypothesis.mutation,
                detail=f"{type(exc).__name__}: {exc}",
            )
            self._store.add(record)
            return record

        improved = candidate >= baseline + hypothesis.min_delta
        outcome = ExperimentOutcome.KEPT if improved else ExperimentOutcome.REVERTED
        detail = (
            f"{hypothesis.metric}: {baseline:.3f} -> {candidate:.3f}"
        )
        if improved:
            self._store.set_active_config(hypothesis_id, candidate_config)
        else:
            revert_mutation(baseline_config, hypothesis.mutation)

        record = ExperimentRecord(
            hypothesis_id=hypothesis_id,
            baseline_score=baseline,
            candidate_score=candidate,
            outcome=outcome,
            mutation=hypothesis.mutation,
            detail=detail,
        )
        self._store.add(record)
        return record

    def rollback(self, experiment_id: str) -> ExperimentRecord | None:
        record = self._store.get(experiment_id)
        if record is None:
            return None
        self._store.set_active_config(record.hypothesis_id, dict(self._base_config))
        rolled = record.model_copy(
            update={
                "outcome": ExperimentOutcome.REVERTED,
                "detail": f"manual rollback of {experiment_id}",
            },
        )
        self._store.add(rolled)
        return rolled

    def leaderboard(self) -> list[LeaderboardEntry]:
        return self._store.leaderboard()


def format_leaderboard(entries: list[LeaderboardEntry]) -> str:
    lines = ["Experiment leaderboard", "====================="]
    if not entries:
        lines.append("(no experiments yet)")
        return "\n".join(lines)
    for item in entries:
        lines.append(
            f"{item.hypothesis_id:24} best={item.best_score:.3f} "
            f"runs={item.experiments} kept={item.kept} last={item.last_outcome.value}",
        )
    return "\n".join(lines)


def format_hypothesis_catalog(catalog: dict[str, Hypothesis]) -> str:
    lines = ["Experiment hypotheses", "===================="]
    for hypothesis in catalog.values():
        lines.append(
            f"{hypothesis.id:24} target={hypothesis.target.value}:{hypothesis.target_ref} "
            f"metric={hypothesis.metric} delta>={hypothesis.min_delta}",
        )
        if hypothesis.description:
            lines.append(f"    {hypothesis.description}")
    return "\n".join(lines)


async def default_pass_rate_score(
    cases: Sequence[EvalCase],
    config: dict[str, Any],
    *,
    runner_factory: Callable[[dict[str, Any]], Awaitable[Any]] | None = None,
) -> float:
    """Score cases using the native eval adapter pass rate."""
    from {{cookiecutter.project_name}}.agents.evaluation.adapters.native import NativeAdapter

    if runner_factory is None:
        raise RuntimeError("runner_factory is required for default_pass_rate_score")

    async def runner(user_input: str) -> dict[str, object]:
        result = await runner_factory({**config, "task": user_input})
        content = str(getattr(result, "content", result) or "")
        return {"output": content, "tools": []}

    report: EvalReport = await NativeAdapter().run(list(cases), runner, config=EvalConfig())
    return float(report.pass_rate)


def build_experiment_runtime(
    *,
    score_fn: ScoreFn | None = None,
    base_config: dict[str, Any] | None = None,
) -> ExperimentRuntime:
    return ExperimentRuntime(score_fn=score_fn, base_config=base_config)


__all__ = [
    "ExperimentRuntime",
    "build_experiment_runtime",
    "default_pass_rate_score",
    "format_hypothesis_catalog",
    "format_leaderboard",
    "load_hypothesis_catalog",
]
