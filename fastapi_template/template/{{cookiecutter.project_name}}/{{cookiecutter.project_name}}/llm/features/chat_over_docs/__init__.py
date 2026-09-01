"""NK feature pack: Chat Over Documents."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.llm.features.base import FeaturePackMeta
from {{cookiecutter.project_name}}.llm.features.common.agentic import ingest_text
from {{cookiecutter.project_name}}.llm.features.common.context import FeatureContext
from {{cookiecutter.project_name}}.llm.features.common.rag import (
    answer_with_citations,
    format_cited_answer,
)


class _Pack:
    meta = FeaturePackMeta(
        id="chat_over_docs",
        name="Chat Over Documents",
        requires=("llm", "rag_traditional", "vector"),
    )

    def register_tools(
        self,
        registry: ToolRegistry,
        *,
        ctx: FeatureContext | None = None,
    ) -> None:
        @agent_tool("Search the knowledge base and return a cited answer")
        async def search_knowledge(query: str) -> str:
            if ctx is None or ctx.rag_service is None:
                return "RAG service not configured"
            from {{cookiecutter.project_name}}.platform.contracts import Scope

            scope = Scope(principal_id="agent", organization_id="default")
            response = await answer_with_citations(ctx.rag_service, query=query, scope=scope)
            return format_cited_answer(response)

        registry.register(search_knowledge)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/chat-over-docs", tags=["llm-features"])

        class QueryPayload(BaseModel):
            input: str = Field(min_length=1, max_length=100_000)

        class IngestPayload(BaseModel):
            text: str = Field(min_length=1, max_length=500_000)
            source: str = Field(default="upload", max_length=512)
            organization_id: str = Field(default="default", max_length=256)

        @router.post("/query")
        async def _query(payload: QueryPayload, request: Request) -> dict[str, str]:
            service = getattr(request.app.state, "rag_service", None)
            if service is None:
                raise HTTPException(status_code=503, detail="RAG service unavailable")
            from {{cookiecutter.project_name}}.platform.contracts import Scope

            scope = getattr(request.state, "scope", None)
            if scope is None:
                scope = Scope(principal_id="http", organization_id="default")
            response = await answer_with_citations(
                service,
                query=payload.input,
                scope=scope,
            )
            return {"output": format_cited_answer(response)}

        @router.post("/ingest")
        async def _ingest(payload: IngestPayload, request: Request) -> dict[str, int | str]:
            ctx = getattr(request.app.state, "feature_context", None)
            if ctx is None or ctx.hybrid_retriever is None:
                raise HTTPException(status_code=503, detail="RAG ingest unavailable")
            count = await ingest_text(
                ctx,
                text=payload.text,
                source=payload.source,
                organization_id=payload.organization_id,
            )
            return {"chunks_indexed": count, "status": "ok"}

        return router


PACK = _Pack()
