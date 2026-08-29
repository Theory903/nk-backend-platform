from __future__ import annotations

from threading import Lock

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BudgetExhausted(RuntimeError):
    """Raised when an execution exceeds its configured budget."""


class Budget(BaseModel):
    """Immutable execution budget."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_steps: int = Field(
        default=10,
        ge=1,
        description="Maximum number of execution steps.",
    )
    max_tokens: int | None = Field(
        default=None,
        ge=1,
        description="Optional max token budget.",
    )
    max_cost_usd: float | None = Field(
        default=None,
        ge=0,
        description="Optional max USD cost budget.",
    )

    @field_validator("max_steps")
    @classmethod
    def validate_max_steps(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_steps must be >= 1")
        return value


class BudgetTracker:
    """
    Thread-safe runtime budget tracker.

    The Budget is immutable. The tracker owns mutable execution state.
    """

    __slots__ = (
        "_budget",
        "_steps_used",
        "_tokens_used",
        "_cost_used",
        "_lock",
    )

    def __init__(self, budget: Budget) -> None:
        self._budget = budget
        self._steps_used = 0
        self._tokens_used = 0
        self._cost_used = 0.0
        self._lock = Lock()

    @property
    def budget(self) -> Budget:
        """Return the immutable budget configuration."""
        return self._budget

    @property
    def steps_used(self) -> int:
        """Return the number of consumed steps."""
        with self._lock:
            return self._steps_used

    @property
    def remaining(self) -> int:
        """Return the number of steps still available."""
        with self._lock:
            return max(
                self._budget.max_steps - self._steps_used,
                0,
            )

    @property
    def exhausted(self) -> bool:
        """Return whether the step budget has been exhausted."""
        return self.remaining == 0

    def add_usage(
        self,
        *,
        tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """Record token/cost usage and raise when budgets are exceeded."""
        with self._lock:
            if tokens:
                self._tokens_used += tokens
                if (
                    self._budget.max_tokens is not None
                    and self._tokens_used > self._budget.max_tokens
                ):
                    raise BudgetExhausted(
                        f"token budget exhausted "
                        f"({self._tokens_used}/{self._budget.max_tokens})"
                    )
            if cost_usd:
                self._cost_used += float(cost_usd)
                if (
                    self._budget.max_cost_usd is not None
                    and self._cost_used > self._budget.max_cost_usd
                ):
                    raise BudgetExhausted(
                        f"cost budget exhausted "
                        f"({self._cost_used}/{self._budget.max_cost_usd})"
                    )

    def step(self) -> int:
        """
        Consume one execution step atomically.

        Returns:
            The new number of consumed steps.

        Raises:
            BudgetExhausted: if no steps remain.
        """
        with self._lock:
            if self._steps_used >= self._budget.max_steps:
                raise BudgetExhausted(
                    "agent budget exhausted after "
                    f"{self._steps_used} steps "
                    f"(limit={self._budget.max_steps})"
                )

            self._steps_used += 1
            return self._steps_used

    def try_step(self) -> bool:
        """
        Attempt to consume one step without raising.

        Returns:
            True if the step was consumed, otherwise False.
        """
        with self._lock:
            if self._steps_used >= self._budget.max_steps:
                return False

            self._steps_used += 1
            return True

    def reset(self) -> None:
        """Reset the tracker for reuse."""
        with self._lock:
            self._steps_used = 0
            self._tokens_used = 0
            self._cost_used = 0.0


__all__ = [
    "Budget",
    "BudgetExhausted",
    "BudgetTracker",
]
