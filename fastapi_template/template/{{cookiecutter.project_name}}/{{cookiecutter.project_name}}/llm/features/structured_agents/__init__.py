"""NK feature pack: Structured Agents."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.llm.features.base import FeaturePackMeta
from {{cookiecutter.project_name}}.llm.features.common.context import FeatureContext
from {{cookiecutter.project_name}}.llm.features.common.research import research_outline, summarize_text



class _Pack:
    meta = FeaturePackMeta(
        id="structured_agents",
        name="Structured Agents",
        requires=('llm', 'agents'),
    )

    def register_tools(
        self,
        registry: ToolRegistry,
        *,
        ctx: FeatureContext | None = None,
    ) -> None:
        @agent_tool("Extract JSON-ready fields from unstructured text")
        async def structured_extract(text: str, schema_hint: str = ) -> str:
            from {{cookiecutter.project_name}}.ai.gateway.router import get_router
            from {{cookiecutter.project_name}}.platform.contracts import ModelMessage
            model = get_router().model_for(task="reasoning")
            prompt = f'Extract structured fields. Schema hint: {schema_hint or "key-value pairs"}. Return JSON only.'
            reply = await model.complete([
                ModelMessage(role='system', content=prompt),
                ModelMessage(role='user', content=text[:30_000]),
            ])
            return reply.content or '{}'
        registry.register(structured_extract)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/structured-agents", tags=["llm-features"])

        class Payload(BaseModel):
            input: str = Field(min_length=1, max_length=100_000)

        @router.post("/extract")
        async def _handle(payload: Payload, request: Request) -> dict[str, str]:
            from {{cookiecutter.project_name}}.ai.gateway.router import get_router
            from {{cookiecutter.project_name}}.platform.contracts import ModelMessage
            model = get_router().model_for(task="default")
            reply = await model.complete([ModelMessage(role="user", content=payload.input)])
            return {"output": reply.content or ""}

        return router


PACK = _Pack()
