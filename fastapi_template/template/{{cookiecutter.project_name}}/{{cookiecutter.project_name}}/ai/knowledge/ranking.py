"""Provider-neutral ranking helpers for hybrid retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class RankingWeights:
    """Weighted signals used after candidate retrieval."""

    dense: float = 0.55
    lexical: float = 0.30
    freshness: float = 0.10
    authority: float = 0.05

    def __post_init__(self) -> None:
        if min(self.dense, self.lexical, self.freshness, self.authority) < 0:
            raise ValueError("ranking weights cannot be negative")


def rank_candidates(
    candidates: list[Mapping[str, Any]],
    *,
    weights: RankingWeights | None = None,
) -> list[dict[str, Any]]:
    """Rank candidates with explicit weighted signals and stable tie-breaking."""
    weights = weights or RankingWeights()
    ranked: list[dict[str, Any]] = []
    for position, candidate in enumerate(candidates):
        score = (
            float(candidate.get("dense_score", 0.0)) * weights.dense
            + float(candidate.get("lexical_score", 0.0)) * weights.lexical
            + float(candidate.get("freshness_score", 0.0)) * weights.freshness
            + float(candidate.get("authority_score", 0.0)) * weights.authority
        )
        ranked.append({**dict(candidate), "rank_score": score, "_position": position})
    ranked.sort(key=lambda item: (-float(item["rank_score"]), int(item["_position"])))
    for item in ranked:
        item.pop("_position", None)
    return ranked


__all__ = ["RankingWeights", "rank_candidates"]
