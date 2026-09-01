"""Failure taxonomy and bounded retry primitives for runtime operations."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

T = TypeVar("T")


class FailureClass(StrEnum):
    INPUT = "input"
    AUTHORIZATION = "authorization"
    POLICY = "policy"
    DEPENDENCY = "dependency"
    TRANSIENT = "transient"
    BUG = "bug"


def classify_failure(exc: BaseException) -> FailureClass:
    """Map common failures to an operationally actionable class."""
    if isinstance(exc, (ValueError, TypeError)):
        return FailureClass.INPUT
    if isinstance(exc, PermissionError):
        return FailureClass.AUTHORIZATION
    if isinstance(exc, TimeoutError):
        return FailureClass.TRANSIENT
    if isinstance(exc, (ConnectionError, OSError)):
        return FailureClass.DEPENDENCY
    return FailureClass.BUG


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded exponential retry policy."""

    attempts: int = 3
    base_delay_s: float = 0.1
    max_delay_s: float = 2.0

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts must be >= 1")
        if self.base_delay_s < 0 or self.max_delay_s < self.base_delay_s:
            raise ValueError("retry delays must be non-negative and ordered")


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
    retryable: Callable[[BaseException], bool] | None = None,
) -> T:
    """Retry only explicitly retryable failures, then re-raise the last one."""
    policy = policy or RetryPolicy()
    retryable = retryable or (
        lambda exc: classify_failure(exc) is FailureClass.TRANSIENT
        or classify_failure(exc) is FailureClass.DEPENDENCY
    )
    for attempt in range(policy.attempts):
        try:
            return await operation()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if attempt + 1 >= policy.attempts or not retryable(exc):
                raise
            await asyncio.sleep(
                min(policy.base_delay_s * (2**attempt), policy.max_delay_s)
            )
    raise AssertionError("unreachable")


__all__ = [
    "FailureClass",
    "RetryPolicy",
    "classify_failure",
    "retry_async",
]
