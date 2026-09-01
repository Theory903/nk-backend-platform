"""Deterministic tool fixture record/replay for harness CI (P14)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from {{cookiecutter.project_name}}.agents.harness.trajectory import Trajectory


@dataclass(frozen=True, slots=True)
class ToolFixtureCall:
    """One recorded tool invocation and response."""

    name: str
    arguments: dict[str, Any]
    output: str
    ok: bool = True


@dataclass(slots=True)
class ToolFixture:
    """Recorded tool I/O for a scenario."""

    scenario: str
    calls: list[ToolFixtureCall] = field(default_factory=list)
    recorded_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "recorded_at": self.recorded_at,
            "calls": [
                {
                    "name": call.name,
                    "arguments": call.arguments,
                    "output": call.output,
                    "ok": call.ok,
                }
                for call in self.calls
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ToolFixture:
        calls = [
            ToolFixtureCall(
                name=str(item["name"]),
                arguments=dict(item.get("arguments") or {}),
                output=str(item.get("output", "")),
                ok=bool(item.get("ok", True)),
            )
            for item in payload.get("calls") or []
        ]
        return cls(
            scenario=str(payload.get("scenario", "")),
            calls=calls,
            recorded_at=payload.get("recorded_at"),
        )


def fixture_path(base: Path, scenario_name: str) -> Path:
    safe = scenario_name.replace("/", "_").replace(" ", "_")
    return base / f"{safe}.json"


def load_fixture(path: str | Path) -> ToolFixture:
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"fixture not found: {file_path}")
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("fixture root must be an object")
    return ToolFixture.from_dict(payload)


def save_fixture(path: str | Path, fixture: ToolFixture) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps(fixture.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def trajectory_to_fixture(scenario: str, trajectory: Trajectory) -> ToolFixture:
    calls: list[ToolFixtureCall] = []
    for step in trajectory.steps:
        if step.kind != "tool" or not step.name:
            continue
        calls.append(
            ToolFixtureCall(
                name=step.name,
                arguments=dict(step.payload.get("arguments") or {}),
                output=str(step.payload.get("output", "")),
                ok=bool(step.payload.get("ok", True)),
            ),
        )
    return ToolFixture(scenario=scenario, calls=calls)


class FixtureReplayer:
    """Replay recorded tool responses in call order."""

    __slots__ = ("_calls", "_cursor")

    def __init__(self, fixture: ToolFixture) -> None:
        self._calls = list(fixture.calls)
        self._cursor = 0

    def next_response(self, name: str, arguments: dict[str, Any]) -> str | None:
        for index in range(self._cursor, len(self._calls)):
            call = self._calls[index]
            if call.name == name and call.arguments == arguments:
                self._cursor = index + 1
                return call.output
            if call.name == name:
                self._cursor = index + 1
                return call.output
        return None

    @property
    def exhausted(self) -> bool:
        return self._cursor >= len(self._calls)


__all__ = [
    "FixtureReplayer",
    "ToolFixture",
    "ToolFixtureCall",
    "fixture_path",
    "load_fixture",
    "save_fixture",
    "trajectory_to_fixture",
]
