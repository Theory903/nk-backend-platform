"""Trajectory capture for harness scenarios (P14)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TrajectoryStep:
    """One step in an agent execution trajectory."""

    kind: str
    name: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Trajectory:
    """Ordered tool/model steps captured during a harness run."""

    steps: list[TrajectoryStep] = field(default_factory=list)

    @property
    def tools(self) -> tuple[str, ...]:
        return tuple(
            step.name
            for step in self.steps
            if step.kind == "tool" and step.name
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": [
                {
                    "kind": step.kind,
                    "name": step.name,
                    "payload": step.payload,
                }
                for step in self.steps
            ],
            "tools": list(self.tools),
        }


class TrajectoryCapture:
    """LoopRuntime-compatible recorder that builds a harness trajectory."""

    __slots__ = ("trajectory",)

    def __init__(self) -> None:
        self.trajectory = Trajectory()

    async def context_built(self, *, task: str, runtime_mode: str) -> None:
        self.trajectory.steps.append(
            TrajectoryStep(
                kind="context",
                payload={"task": task, "runtime_mode": runtime_mode},
            ),
        )

    async def model_called(self, *, step: int, tool_calls: int = 0) -> None:
        self.trajectory.steps.append(
            TrajectoryStep(
                kind="model",
                payload={"step": step, "tool_calls": tool_calls},
            ),
        )

    async def tool_called(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        output: str,
        ok: bool,
    ) -> None:
        self.trajectory.steps.append(
            TrajectoryStep(
                kind="tool",
                name=name,
                payload={
                    "arguments": arguments,
                    "output": output,
                    "ok": ok,
                },
            ),
        )

    async def approval_requested(self, *, tool_name: str) -> None:
        self.trajectory.steps.append(
            TrajectoryStep(
                kind="approval",
                name=tool_name,
                payload={},
            ),
        )


__all__ = ["Trajectory", "TrajectoryCapture", "TrajectoryStep"]
