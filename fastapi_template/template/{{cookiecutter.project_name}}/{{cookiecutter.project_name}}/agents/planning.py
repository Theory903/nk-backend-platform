"""Agent planning state and tool integration."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from {{cookiecutter.project_name}}.agents.tools import AgentTool, agent_tool


class TodoItem(BaseModel):
    """A single agent planning item."""

    model_config = {
        "extra": "forbid",
    }

    task: str = Field(min_length=1)
    done: bool = False

    @classmethod
    def validate_item(cls, value: Any) -> "TodoItem":
        if isinstance(value, cls):
            return value

        return cls.model_validate(value)


_TODO_LIST_ADAPTER = TypeAdapter(list[TodoItem])


@dataclass(slots=True)
class Planner:
    """
    Agent planning state exposed through an AgentTool.

    The planner owns task state for one agent execution. Persistence,
    checkpointing, and long-term memory should remain outside this class.
    """

    todos: list[TodoItem] = field(default_factory=list)

    def tool(self) -> AgentTool:
        """Return the planner's registry-ready tool."""
        planner = self

        @agent_tool(
            description=(
                "Replace the current todo plan for this task. "
                "Each todo must contain a task and optional done flag."
            )
        )
        def write_todos(
            todos: list[dict[str, Any]],
        ) -> dict[str, Any]:
            try:
                validated = _TODO_LIST_ADAPTER.validate_python(
                    todos
                )
            except ValidationError as exc:
                raise ValueError(
                    f"invalid todo plan: {exc}"
                ) from exc

            planner.todos = validated

            pending = [
                item.task
                for item in validated
                if not item.done
            ]

            completed = sum(
                item.done
                for item in validated
            )

            return {
                "count": len(validated),
                "completed": completed,
                "pending": pending,
            }

        return write_todos

    def summary(self) -> str:
        """Return the current plan as deterministic JSON."""
        return json.dumps(
            [
                item.model_dump()
                for item in self.todos
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def pending(self) -> list[TodoItem]:
        """Return unfinished tasks."""
        return [
            item
            for item in self.todos
            if not item.done
        ]

    def completed(self) -> list[TodoItem]:
        """Return finished tasks."""
        return [
            item
            for item in self.todos
            if item.done
        ]

    @property
    def is_complete(self) -> bool:
        """Whether every planned task is complete."""
        return bool(self.todos) and all(
            item.done
            for item in self.todos
        )

    def clear(self) -> None:
        """Clear the current plan."""
        self.todos.clear()


__all__ = [
    "Planner",
    "TodoItem",
]