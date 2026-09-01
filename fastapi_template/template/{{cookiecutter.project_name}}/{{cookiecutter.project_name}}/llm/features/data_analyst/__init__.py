"""NK feature pack: Data Analyst."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.llm.features.base import FeaturePackMeta
from {{cookiecutter.project_name}}.llm.features.common.context import FeatureContext
from {{cookiecutter.project_name}}.llm.features.common.research import research_outline, summarize_text



class _Pack:
    meta = FeaturePackMeta(
        id="data_analyst",
        name="Data Analyst",
        requires=('llm', 'agents'),
    )

    def register_tools(
        self,
        registry: ToolRegistry,
        *,
        ctx: FeatureContext | None = None,
    ) -> None:
        @agent_tool("Analyze CSV or tabular text and return insights")
        async def analyze_table(table_text: str) -> str:
            return await summarize_text(table_text, focus='data patterns and anomalies')
        registry.register(analyze_table)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/data-analyst", tags=["llm-features"])

        class Payload(BaseModel):
            input: str = Field(min_length=1, max_length=100_000)

        @router.post("/analyze")
        async def _handle(payload: Payload, request: Request) -> dict[str, str]:
            from {{cookiecutter.project_name}}.ai.gateway.router import get_router
            from {{cookiecutter.project_name}}.platform.contracts import ModelMessage
            model = get_router().model_for(task="default")
            reply = await model.complete([ModelMessage(role="user", content=payload.input)])
            return {"output": reply.content or ""}

        return router


PACK = _Pack()
