"""Multi-agent planner + executor helper."""

from __future__ import annotations

from {{cookiecutter.project_name}}.ai.gateway.router import get_router
from {{cookiecutter.project_name}}.llm.features.common.research import research_outline
from {{cookiecutter.project_name}}.platform.contracts import ModelMessage


async def run_team_goal(goal: str) -> str:
    """Two-step team: planner outline, then executor synthesis."""
    plan = await research_outline(goal, sections=4)
    model = get_router().model_for(task="reasoning")
    reply = await model.complete(
        [
            ModelMessage(
                role="system",
                content=(
                    "You are the executor on a small agent team. "
                    "Follow the plan and produce a concise final answer."
                ),
            ),
            ModelMessage(
                role="user",
                content=f"Goal:\n{goal}\n\nPlan:\n{plan}\n\nExecute the plan.",
            ),
        ],
    )
    execution = reply.content or ""
    return f"## Plan\n{plan}\n\n## Result\n{execution}"


__all__ = ["run_team_goal"]
