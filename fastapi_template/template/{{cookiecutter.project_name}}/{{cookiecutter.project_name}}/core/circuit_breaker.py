"""Production circuit breaker for unreliable external dependencies."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when the circuit refuses a request."""


@dataclass(frozen=True, slots=True)
class CircuitStats:
    state: CircuitState
    failures: int
    successes: int
    opened_at: float | None


class CircuitBreaker:
    """
    Thread-safe circuit breaker.

    State machine:

        CLOSED
          │ failures >= threshold
          ▼
        OPEN
          │ reset timeout elapsed
          ▼
        HALF_OPEN
          │ success
          └──────────► CLOSED

          HALF_OPEN failure
                │
                ▼
               OPEN

    Only one request is allowed to probe the dependency in HALF_OPEN.
    """

    __slots__ = (
        "_failure_threshold",
        "_reset_timeout_s",
        "_lock",
        "_state",
        "_failures",
        "_successes",
        "_opened_at",
        "_half_open_probe",
    )

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        reset_timeout_s: float = 30.0,
    ) -> None:
        if failure_threshold <= 0:
            raise ValueError(
                "failure_threshold must be greater than zero"
            )

        if reset_timeout_s <= 0:
            raise ValueError(
                "reset_timeout_s must be greater than zero"
            )

        self._failure_threshold = failure_threshold
        self._reset_timeout_s = reset_timeout_s

        self._lock = Lock()

        self._state = CircuitState.CLOSED
        self._failures = 0
        self._successes = 0
        self._opened_at: float | None = None

        self._half_open_probe = False

    @property
    def state(self) -> CircuitState:
        """Return the current state and perform timeout transition."""
        with self._lock:
            self._refresh_state()
            return self._state

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failures

    @property
    def stats(self) -> CircuitStats:
        with self._lock:
            self._refresh_state()

            return CircuitStats(
                state=self._state,
                failures=self._failures,
                successes=self._successes,
                opened_at=self._opened_at,
            )

    def allow(self) -> bool:
        """
        Attempt to acquire permission for one request.

        In HALF_OPEN, only one request is allowed through as the
        recovery probe.
        """
        with self._lock:
            self._refresh_state()

            if self._state is CircuitState.OPEN:
                return False

            if self._state is CircuitState.HALF_OPEN:
                if self._half_open_probe:
                    return False

                self._half_open_probe = True
                return True

            return True

    def acquire(self) -> None:
        """Allow a request or raise CircuitOpenError."""
        if not self.allow():
            raise CircuitOpenError(
                "circuit breaker is open"
            )

    def record_success(self) -> None:
        """Record a successful dependency call."""
        with self._lock:
            self._successes += 1

            self._failures = 0
            self._state = CircuitState.CLOSED
            self._opened_at = None
            self._half_open_probe = False

    def record_failure(self) -> None:
        """Record a failed dependency call."""
        with self._lock:
            self._failures += 1
            self._half_open_probe = False

            if self._state is CircuitState.HALF_OPEN:
                self._open()

            elif self._failures >= self._failure_threshold:
                self._open()

    def reset(self) -> None:
        """Manually close the circuit."""
        with self._lock:
            self._failures = 0
            self._state = CircuitState.CLOSED
            self._opened_at = None
            self._half_open_probe = False

    def _refresh_state(self) -> None:
        if self._state is not CircuitState.OPEN:
            return

        if self._opened_at is None:
            return

        elapsed = (
            time.monotonic()
            - self._opened_at
        )

        if elapsed >= self._reset_timeout_s:
            self._state = CircuitState.HALF_OPEN
            self._half_open_probe = False

    def _open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        self._half_open_probe = False


class AsyncCircuitBreaker:
    """
    Async-compatible circuit breaker.

    Uses the same state machine while protecting transitions with
    asyncio.Lock for async applications.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        reset_timeout_s: float = 30.0,
    ) -> None:
        if failure_threshold <= 0:
            raise ValueError(
                "failure_threshold must be greater than zero"
            )

        if reset_timeout_s <= 0:
            raise ValueError(
                "reset_timeout_s must be greater than zero"
            )

        self._failure_threshold = failure_threshold
        self._reset_timeout_s = reset_timeout_s

        self._lock = asyncio.Lock()

        self._state = CircuitState.CLOSED
        self._failures = 0
        self._successes = 0
        self._opened_at: float | None = None
        self._half_open_probe = False

    @property
    def state(self) -> CircuitState:
        return self._state

    async def allow(self) -> bool:
        async with self._lock:
            self._refresh_state()

            if self._state is CircuitState.OPEN:
                return False

            if self._state is CircuitState.HALF_OPEN:
                if self._half_open_probe:
                    return False

                self._half_open_probe = True

            return True

    async def acquire(self) -> None:
        if not await self.allow():
            raise CircuitOpenError(
                "circuit breaker is open"
            )

    async def record_success(self) -> None:
        async with self._lock:
            self._successes += 1
            self._failures = 0
            self._state = CircuitState.CLOSED
            self._opened_at = None
            self._half_open_probe = False

    async def record_failure(self) -> None:
        async with self._lock:
            self._failures += 1
            self._half_open_probe = False

            if self._state is CircuitState.HALF_OPEN:
                self._open()
            elif self._failures >= self._failure_threshold:
                self._open()

    async def reset(self) -> None:
        async with self._lock:
            self._failures = 0
            self._state = CircuitState.CLOSED
            self._opened_at = None
            self._half_open_probe = False

    def _refresh_state(self) -> None:
        if (
            self._state is CircuitState.OPEN
            and self._opened_at is not None
            and (
                time.monotonic()
                - self._opened_at
                >= self._reset_timeout_s
            )
        ):
            self._state = CircuitState.HALF_OPEN
            self._half_open_probe = False

    def _open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        self._half_open_probe = False


__all__ = [
    "AsyncCircuitBreaker",
    "CircuitBreaker",
    "CircuitOpenError",
    "CircuitState",
    "CircuitStats",
]