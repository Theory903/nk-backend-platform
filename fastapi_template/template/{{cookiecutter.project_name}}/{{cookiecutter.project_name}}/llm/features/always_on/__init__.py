"""NK feature pack: Always-On Agents."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.llm.features.base import FeaturePackMeta
from {{cookiecutter.project_name}}.llm.features.common.always_on import enqueue_digest
from {{cookiecutter.project_name}}.llm.features.common.context import FeatureContext


class _Pack:
    meta = FeaturePackMeta(
        id="always_on",
        name="Always-On Agents",
        requires=("llm", "agents", "taskiq"),
    )

    def register_tools(
        self,
        registry: ToolRegistry,
        *,
        ctx: FeatureContext | None = None,
    ) -> None:
        @agent_tool("Queue an always-on digest for a topic")
        async def schedule_digest(topic: str) -> str:
            return await enqueue_digest(topic)

        registry.register(schedule_digest)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/always-on", tags=["llm-features"])

        class Payload(BaseModel):
            input: str = Field(min_length=1, max_length=100_000)

        @router.post("/schedules")
        async def _handle(payload: Payload, request: Request) -> dict[str, str]:
            output = await enqueue_digest(payload.input)
            return {"output": output}

        return router


PACK = _Pack()
