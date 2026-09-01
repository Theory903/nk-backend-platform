"""NK Harness — owns agent runtime lifecycle and dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from {{cookiecutter.project_name}}.agents.budgets import Budget
from {{cookiecutter.project_name}}.agents.guardrails import Guardrails
from {{cookiecutter.project_name}}.agents.loop import LoopRuntime
from {{cookiecutter.project_name}}.agents.memory import MemoryStore
from {{cookiecutter.project_name}}.agents.tools import ToolRegistry
from {{cookiecutter.project_name}}.platform.contracts import Scope


DEFAULT_SYSTEM_PROMPT = "You are a helpful agent."


@dataclass(frozen=True, slots=True)
class HarnessConfig:
    """Immutable configuration for an agent harness."""

    system_prompt: str = DEFAULT_SYSTEM_PROMPT

    def __post_init__(self) -> None:
        if not self.system_prompt.strip():
            raise ValueError("system_prompt cannot be empty.")


class Harness:
    """
    Owns the dependencies and lifecycle of agent executions.

    Harness is intentionally lightweight:
    - owns shared infrastructure
    - creates isolated LoopRuntime instances
    - provides one composition boundary for the agent stack

    A Harness should generally be created once and reused for many runs.
    """

    __slots__ = (
        "model",
        "tools",
        "budget",
        "guardrails",
        "memory",
        "config",
        "scope",
    )

    def __init__(
        self,
        model: Any,
        *,
        tools: ToolRegistry | None = None,
        budget: Budget | None = None,
        guardrails: Guardrails | None = None,
        memory: MemoryStore | None = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        config: HarnessConfig | None = None,
        scope: Scope | None = None,
    ) -> None:
        if model is None:
            raise ValueError("model cannot be None.")

        self.model = model
        self.tools = tools if tools is not None else ToolRegistry()
        self.budget = budget if budget is not None else Budget()
        self.guardrails = (
            guardrails
            if guardrails is not None
            else Guardrails()
        )
        self.memory = (
            memory
            if memory is not None
            else MemoryStore()
        )

        self.config = config or HarnessConfig(
            system_prompt=system_prompt,
        )
        self.scope = scope

    @property
    def system_prompt(self) -> str:
        """Return the configured system prompt."""
        return self.config.system_prompt

    def loop(self) -> LoopRuntime:
        """
        Create a new runtime for one agent execution.

        Runtime state should live in LoopRuntime, not Harness.
        Shared infrastructure such as tools, memory, and policies is owned
        by the Harness.
        """
        return LoopRuntime(
            model=self.model,
            tools=self.tools,
            budget=self.budget,
            guardrails=self.guardrails,
            system_prompt=self.system_prompt,
            scope=self.scope,
        )

    def run(self, *args: Any, **kwargs: Any) -> Any:
        """
        Execute one agent run.

        This intentionally delegates execution semantics to LoopRuntime.
        The harness remains a composition/lifecycle boundary.
        """
        runtime = self.loop()

        run = getattr(runtime, "run", None)

        if run is None or not callable(run):
            raise TypeError(
                "LoopRuntime must expose a callable run() method."
            )

        return run(*args, **kwargs)

    async def arun(self, *args: Any, **kwargs: Any) -> Any:
        """
        Execute one asynchronous agent run.

        Supports LoopRuntime implementations exposing either:
        - arun()
        - run() returning an awaitable
        """
        runtime = self.loop()

        arun = getattr(runtime, "arun", None)

        if callable(arun):
            return await arun(*args, **kwargs)

        run = getattr(runtime, "run", None)

        if not callable(run):
            raise TypeError(
                "LoopRuntime must expose run() or arun()."
            )

        result = run(*args, **kwargs)

        if hasattr(result, "__await__"):
            return await result

        return result

    def health(self) -> dict[str, Any]:
        """
        Return lightweight runtime dependency health information.

        This must remain side-effect free and cheap enough for readiness
        endpoints or diagnostics.
        """
        return {
            "ready": self.model is not None,
            "tools": self.tools.__class__.__name__,
            "budget": self.budget.__class__.__name__,
            "guardrails": self.guardrails.__class__.__name__,
            "memory": self.memory.__class__.__name__,
        }


__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "Harness",
    "HarnessConfig",
]