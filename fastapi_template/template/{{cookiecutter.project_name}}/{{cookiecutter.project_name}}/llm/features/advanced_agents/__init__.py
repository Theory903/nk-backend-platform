"""NK feature pack: Advanced Agents."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.llm.features.base import FeaturePackMeta
from {{cookiecutter.project_name}}.llm.features.common.context import FeatureContext
from {{cookiecutter.project_name}}.llm.features.common.teams import run_team_goal


class _Pack:
    meta = FeaturePackMeta(
        id="advanced_agents",
        name="Advanced Agents",
        requires=("llm", "agents"),
    )

    def register_tools(
        self,
        registry: ToolRegistry,
        *,
        ctx: FeatureContext | None = None,
    ) -> None:
        @agent_tool("Break a goal into numbered subtasks for a team agent")
        async def delegate_subtask(goal: str) -> str:
            return await run_team_goal(goal)

        registry.register(delegate_subtask)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/advanced-agents", tags=["llm-features"])

        class Payload(BaseModel):
            input: str = Field(min_length=1, max_length=100_000)

        @router.post("/team")
        async def _handle(payload: Payload, request: Request) -> dict[str, str]:
            output = await run_team_goal(payload.input)
            return {"output": output}

        return router


PACK = _Pack()
