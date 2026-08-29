from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Step:
    """A single workflow step with optional retry and compensation."""

    name: str
    fn: Callable[..., Any]
    max_retries: int = 0
    compensate: Callable[..., Any] | None = None
    requires_approval: bool = False


@dataclass
class Workflow:
    """Ordered step sequence with shared context dict."""

    name: str
    steps: list[Step] = field(default_factory=list)
    on_failure: str = "abort"

    def add_step(self, step: Step) -> "Workflow":
        """Append a step to this workflow."""
        self.steps.append(step)
        return self

    def validate(self) -> list[str]:
        """Return a list of validation errors (empty = valid)."""
        errors = []
        if not self.steps:
            errors.append(f"workflow '{self.name}' has no steps")
        seen = set()
        for s in self.steps:
            if s.name in seen:
                errors.append(f"duplicate step name '{s.name}'")
            seen.add(s.name)
        return errors


@dataclass
class WorkflowResult:
    workflow_name: str
    status: str
    completed_steps: list[str] = field(default_factory=list)
    failed_step: str | None = None
    error: str | None = None
    outputs: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """True when status == completed."""
        return self.status == "completed"
