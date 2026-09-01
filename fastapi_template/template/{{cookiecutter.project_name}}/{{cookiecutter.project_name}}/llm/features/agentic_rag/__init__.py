"""NK feature pack: Agentic RAG."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.llm.features.base import FeaturePackMeta
from {{cookiecutter.project_name}}.llm.features.common.agentic import (
    format_agentic_result,
    run_agentic_rag,
)
from {{cookiecutter.project_name}}.llm.features.common.context import FeatureContext


class _Pack:
    meta = FeaturePackMeta(
        id="agentic_rag",
        name="Agentic RAG",
        requires=("llm", "rag_traditional", "vector", "agents"),
    )

    def register_tools(
        self,
        registry: ToolRegistry,
        *,
        ctx: FeatureContext | None = None,
    ) -> None:
        @agent_tool("Run agentic RAG with plan/retrieve/grade loops")
        async def plan_retrieval(query: str) -> str:
            if ctx is None or ctx.hybrid_retriever is None:
                return "Agentic RAG retriever not configured"
            result = await run_agentic_rag(ctx, query)
            return format_agentic_result(result)

        registry.register(plan_retrieval)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/agentic-rag", tags=["llm-features"])

        class Payload(BaseModel):
            input: str = Field(min_length=1, max_length=100_000)

        @router.post("/run")
        async def _handle(payload: Payload, request: Request) -> dict[str, str]:
            ctx = getattr(request.app.state, "feature_context", None)
            if ctx is None or ctx.hybrid_retriever is None:
                raise HTTPException(
                    status_code=503,
                    detail="Agentic RAG retriever unavailable",
                )
            result = await run_agentic_rag(ctx, payload.input)
            return {"output": format_agentic_result(result)}

        return router


PACK = _Pack()
