from __future__ import annotations

import time
from collections import defaultdict


class LimitExceededError(ValueError):
    pass


class LimitChecker:
    def __init__(
        self,
        daily_limit_minor: int = 10_000_000_00,
        monthly_limit_minor: int = 100_000_000_00,
    ) -> None:
        self._daily = daily_limit_minor
        self._monthly = monthly_limit_minor
        self._daily_used: dict[str, tuple[int, int]] = {}
        self._monthly_used: dict[str, tuple[int, int]] = {}

    def check_and_record(self, key: str, amount_minor: int, now: float | None = None) -> None:
        ts = now if now is not None else time.time()
        day = int(ts // 86400)
        month = int(ts // (86400 * 30))
        d_key = f"{key}:d:{day}"
        m_key = f"{key}:m:{month}"
        d_used = self._daily_used.get(d_key, (0, day))[0]
        m_used = self._monthly_used.get(m_key, (0, month))[0]
        if d_used + amount_minor > self._daily:
            raise LimitExceededError(f"daily limit exceeded for {key}")
        if m_used + amount_minor > self._monthly:
            raise LimitExceededError(f"monthly limit exceeded for {key}")
        self._daily_used[d_key] = (d_used + amount_minor, day)
        self._monthly_used[m_key] = (m_used + amount_minor, month)

    def get_daily_used(self, key: str, now: float | None = None) -> int:
        ts = now if now is not None else time.time()
        day = int(ts // 86400)
        return self._daily_used.get(f"{key}:d:{day}", (0, day))[0]
