"""Harness scenario loading (P14)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from {{cookiecutter.project_name}}.agents.evaluation import DatasetError, EvalCase, load_dataset_yaml


@dataclass(frozen=True, slots=True)
class HarnessScenario:
    """A named scenario grouping evaluation cases and optional fixtures."""

    name: str
    cases: tuple[EvalCase, ...]
    runtime_mode: str = "loop"
    description: str = ""
    fixture_file: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


def load_scenarios_yaml(path: str | Path) -> list[HarnessScenario]:
    """
    Load harness scenarios from YAML.

    Supports:
    - ``scenarios:`` list (preferred)
    - legacy ``cases:`` root list (single implicit scenario)
    """
    dataset_path = Path(path)
    if not dataset_path.is_file():
        raise DatasetError(f"Scenario file does not exist: {dataset_path}")

    try:
        import yaml
    except ImportError as exc:
        raise DatasetError("PyYAML is required to load scenario files.") from exc

    raw = yaml.safe_load(dataset_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, Mapping):
        raise DatasetError("Scenario root must be a mapping.")

    scenarios_raw = raw.get("scenarios")
    if scenarios_raw is None:
        cases = load_dataset_yaml(dataset_path)
        return [
            HarnessScenario(
                name=dataset_path.stem,
                cases=tuple(cases),
                description="legacy cases file",
            ),
        ]

    if not isinstance(scenarios_raw, list):
        raise DatasetError("'scenarios' must be a list.")

    scenarios: list[HarnessScenario] = []
    for index, item in enumerate(scenarios_raw):
        if not isinstance(item, Mapping):
            raise DatasetError(f"Scenario at index {index} must be a mapping.")
        name = str(item.get("name", "")).strip()
        if not name:
            raise DatasetError(f"Scenario at index {index} requires a name.")
        cases_path = item.get("cases_file")
        if cases_path:
            cases = tuple(load_dataset_yaml(Path(cases_path)))
        else:
            inline = item.get("cases", [])
            if not isinstance(inline, list):
                raise DatasetError(f"Scenario {name!r}: cases must be a list.")
            cases = tuple(
                EvalCase(
                    name=str(c["name"]),
                    input=str(c["input"]),
                    expected_contains=tuple(c.get("expected_contains") or ()),
                    expected_tools=tuple(c.get("expected_tools") or ()),
                    metadata=dict(c.get("metadata") or {}),
                )
                for c in inline
            )
        if not cases:
            raise DatasetError(f"Scenario {name!r} has no cases.")
        scenarios.append(
            HarnessScenario(
                name=name,
                cases=cases,
                runtime_mode=str(item.get("runtime_mode", "loop")),
                description=str(item.get("description", "")),
                fixture_file=(
                    str(item["fixture_file"]).strip()
                    if item.get("fixture_file")
                    else None
                ),
                metadata=dict(item.get("metadata") or {}),
            ),
        )
    return scenarios


__all__ = ["HarnessScenario", "load_scenarios_yaml"]
