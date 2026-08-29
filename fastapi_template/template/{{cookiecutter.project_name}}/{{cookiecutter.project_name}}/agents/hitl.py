"""Human-in-the-loop controls for NK agent runtimes.

Provides:
- callback-based approval for custom/loop runtimes
- LangChain HITL middleware for LangGraph runtimes
- explicit approval/rejection semantics
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from {{cookiecutter.project_name}}.ai.llm import Message


ApprovalDecision: Final = bool | None
ApprovalDecider = Callable[
    [list[Message]],
    ApprovalDecision | Awaitable[ApprovalDecision],
]
ApprovalHook = Callable[
    [list[Message]],
    Awaitable[None],
]


class HumanInTheLoopError(RuntimeError):
    """Base exception for human-in-the-loop failures."""


class HumanRejected(HumanInTheLoopError):
    """Raised when a human rejects an agent action."""

    def __init__(
        self,
        reason: str = "approval denied by human gate",
    ) -> None:
        self.reason = reason
        super().__init__(reason)


class HumanApprovalRequired(HumanInTheLoopError):
    """Raised when an action requires human approval."""


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """Structured information presented to a human approver."""

    messages: tuple[Message, ...]
    action: str = "agent_step"
    metadata: Mapping[str, Any] | None = None


async def _resolve_decision(
    decide: ApprovalDecider,
    messages: list[Message],
) -> ApprovalDecision:
    result = decide(messages)

    if hasattr(result, "__await__"):
        result = await result

    return result


def callback_gate(
    decide: ApprovalDecider,
) -> ApprovalHook:
    """
    Create an approval hook for custom runtimes.

    Decision semantics:
        True  -> approve
        False -> reject
        None  -> reject
    """
    if not callable(decide):
        raise TypeError("decide must be callable")

    async def hook(messages: list[Message]) -> None:
        verdict = await _resolve_decision(
            decide,
            messages,
        )

        if verdict is not True:
            raise HumanRejected()

    return hook


def graph_hitl_middleware(
    interrupt_on: Mapping[str, Any],
) -> Any:
    """
    Build LangChain's HumanInTheLoopMiddleware for LangGraph.

    The graph must use a checkpointer when interrupts need to be
    persisted and resumed.
    """
    if not isinstance(interrupt_on, Mapping):
        raise TypeError(
            "interrupt_on must be a mapping"
        )

    from langchain.agents.middleware import (
        HumanInTheLoopMiddleware,
    )

    return HumanInTheLoopMiddleware(
        interrupt_on=dict(interrupt_on),
    )


def require_approval(
    approved: bool,
    *,
    reason: str = "approval denied by human gate",
) -> None:
    """
    Enforce a synchronous approval decision.

    Useful at explicit application boundaries.
    """
    if not approved:
        raise HumanRejected(reason)


__all__ = [
    "ApprovalDecider",
    "ApprovalHook",
    "ApprovalRequest",
    "HumanApprovalRequired",
    "HumanInTheLoopError",
    "HumanRejected",
    "callback_gate",
    "graph_hitl_middleware",
    "require_approval",
]