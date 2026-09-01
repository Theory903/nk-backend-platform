"""Shared agent runtime types (P3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from {{cookiecutter.project_name}}.ai.llm import Message


class RuntimeMode(StrEnum):
    """Routing ladder modes for agent execution."""

    AUTO = "auto"
    LOOP = "loop"
    GRAPH = "graph"
    SUPERVISOR = "supervisor"


@dataclass(slots=True)
class AgentResult:
    """Stable result contract shared by NK runtimes."""

    content: str | None
    trace: list[tuple[Any, ...]] = field(default_factory=list)
    transcript: list[Message] = field(default_factory=list)
    steps: int = 0
    runtime_mode: RuntimeMode = RuntimeMode.LOOP


@dataclass(frozen=True, slots=True)
class WorkerSpec:
    """Worker agent bound to a model capability."""

    name: str
    capability: str = "chat"
    system_prompt: str = "You are a focused worker agent. Complete the assigned subtask."


__all__ = ["AgentResult", "RuntimeMode", "WorkerSpec"]
