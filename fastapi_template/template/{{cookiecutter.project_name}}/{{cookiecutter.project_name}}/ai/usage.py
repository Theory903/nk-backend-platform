from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class UsageRecord:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0


@dataclass
class UsageTracker:
    """In-memory token/cost ledger. Swap storage for persistent backend."""

    _store: dict[str, UsageRecord] = field(default_factory=lambda: defaultdict(UsageRecord))

    def record(self, provider: str, prompt_tokens: int, completion_tokens: int, cost: float = 0.0) -> None:
        rec = self._store[provider]
        rec.prompt_tokens += prompt_tokens
        rec.completion_tokens += completion_tokens
        rec.cost_usd += cost
        rec.calls += 1

    def get(self, provider: str) -> UsageRecord:
        return self._store[provider]

    def all(self) -> dict[str, UsageRecord]:
        return dict(self._store)

    def reset(self) -> None:
        self._store.clear()


_tracker = UsageTracker()


def get_tracker() -> UsageTracker:
    return _tracker
