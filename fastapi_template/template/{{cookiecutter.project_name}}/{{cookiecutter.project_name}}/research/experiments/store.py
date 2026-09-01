"""In-memory experiment history and leaderboard (P26)."""

from __future__ import annotations

from {{cookiecutter.project_name}}.research.experiments.contracts import (
    ExperimentOutcome,
    ExperimentRecord,
    LeaderboardEntry,
)


class ExperimentStore:
    """Process-local experiment ledger."""

    __slots__ = ("_records", "_baselines", "_active")

    def __init__(self) -> None:
        self._records: list[ExperimentRecord] = []
        self._baselines: dict[str, float] = {}
        self._active: dict[str, dict] = {}

    def add(self, record: ExperimentRecord) -> None:
        self._records.append(record)

    def records(self) -> tuple[ExperimentRecord, ...]:
        return tuple(self._records)

    def get(self, experiment_id: str) -> ExperimentRecord | None:
        for record in reversed(self._records):
            if record.experiment_id == experiment_id:
                return record
        return None

    def baseline_score(self, hypothesis_id: str) -> float | None:
        return self._baselines.get(hypothesis_id)

    def set_baseline_score(self, hypothesis_id: str, score: float) -> None:
        self._baselines[hypothesis_id] = score

    def set_active_config(self, hypothesis_id: str, config: dict) -> None:
        self._active[hypothesis_id] = dict(config)

    def active_config(self, hypothesis_id: str) -> dict | None:
        value = self._active.get(hypothesis_id)
        return dict(value) if value is not None else None

    def leaderboard(self) -> list[LeaderboardEntry]:
        grouped: dict[str, list[ExperimentRecord]] = {}
        for record in self._records:
            grouped.setdefault(record.hypothesis_id, []).append(record)
        entries: list[LeaderboardEntry] = []
        for hypothesis_id, items in grouped.items():
            best = max(item.candidate_score for item in items)
            kept = sum(1 for item in items if item.outcome == ExperimentOutcome.KEPT)
            entries.append(
                LeaderboardEntry(
                    hypothesis_id=hypothesis_id,
                    best_score=best,
                    experiments=len(items),
                    kept=kept,
                    last_outcome=items[-1].outcome,
                ),
            )
        return sorted(entries, key=lambda item: item.best_score, reverse=True)


__all__ = ["ExperimentStore"]
