"""Telemetry → improvement signal bridge (P30)."""

from __future__ import annotations

from {{cookiecutter.project_name}}.research.self_improving.contracts import (
    SignalKind,
    TelemetrySignal,
)


class TelemetryBridge:
    """Convert metrics, experiments, and harness output into improvement signals."""

    __slots__ = ("_signals",)

    def __init__(self) -> None:
        self._signals: list[TelemetrySignal] = []

    def from_leaderboard(self, leaderboard: list[object]) -> list[TelemetrySignal]:
        signals: list[TelemetrySignal] = []
        for item in leaderboard:
            best_score = getattr(item, "best_score", None)
            hypothesis_id = getattr(item, "hypothesis_id", "")
            if best_score is None:
                continue
            kind = SignalKind.EVAL_IMPROVEMENT if best_score >= 0.8 else SignalKind.EVAL_REGRESSION
            signals.append(
                TelemetrySignal(
                    kind=kind,
                    score=float(best_score),
                    detail=f"leaderboard {hypothesis_id}",
                    source="experiment_leaderboard",
                ),
            )
        self._signals.extend(signals)
        return signals

    def from_cost_latency(self, *, cost_usd: float = 0.0, latency_s: float = 0.0) -> list[TelemetrySignal]:
        signals: list[TelemetrySignal] = []
        if cost_usd > 0:
            signals.append(
                TelemetrySignal(
                    kind=SignalKind.COST,
                    score=float(cost_usd),
                    detail="estimated LLM cost",
                    source="usage_tracker",
                ),
            )
        if latency_s > 0:
            signals.append(
                TelemetrySignal(
                    kind=SignalKind.LATENCY,
                    score=float(latency_s),
                    detail="model latency",
                    source="otel_histogram",
                ),
            )
        self._signals.extend(signals)
        return signals

    def signals(self) -> tuple[TelemetrySignal, ...]:
        return tuple(self._signals)


__all__ = ["TelemetryBridge"]
