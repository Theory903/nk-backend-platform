from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ScreeningResult:
    allowed: bool
    reason: str = ""


class AmlChecker(Protocol):
    async def screen(self, org_id: str, amount_minor: int) -> ScreeningResult: ...


class AllowAllAmlChecker:
    async def screen(self, org_id: str, amount_minor: int) -> ScreeningResult:  # noqa: ARG002
        return ScreeningResult(allowed=True, reason="allow-all stub")


class DenyHighValueAmlChecker:
    def __init__(self, threshold: int = 50_000_00) -> None:
        self._threshold = threshold

    async def screen(self, org_id: str, amount_minor: int) -> ScreeningResult:  # noqa: ARG002
        if amount_minor > self._threshold:
            return ScreeningResult(allowed=False, reason="high value flagged")
        return ScreeningResult(allowed=True)
