"""NK feature pack: Memory Chat."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.llm.features.base import FeaturePackMeta
from {{cookiecutter.project_name}}.llm.features.common.context import FeatureContext
from {{cookiecutter.project_name}}.llm.features.common.memory_tools import (
    format_memory_context,
    recall_facts,
    remember_fact,
)


class _Pack:
    meta = FeaturePackMeta(
        id="memory_chat",
        name="Memory Chat",
        requires=("llm", "agents"),
    )

    def register_tools(
        self,
        registry: ToolRegistry,
        *,
        ctx: FeatureContext | None = None,
    ) -> None:
        @agent_tool("Store a short fact in the current thread memory keyspace")
        async def remember_fact_tool(fact: str, user_id: str = "default") -> str:
            if ctx is None or ctx.memory_store is None:
                return "Memory store not configured"
            uid = user_id or ctx.default_user_id
            return remember_fact(ctx, user_id=uid, fact=fact)

        registry.register(remember_fact_tool)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/memory-chat", tags=["llm-features"])

        class Payload(BaseModel):
            input: str = Field(min_length=1, max_length=100_000)
            user_id: str = Field(default="default", max_length=256)

        @router.post("/chat")
        async def _handle(payload: Payload, request: Request) -> dict[str, str]:
            ctx = getattr(request.app.state, "feature_context", None)
            if ctx is None or ctx.memory_store is None:
                raise HTTPException(status_code=503, detail="Memory store unavailable")
            from {{cookiecutter.project_name}}.ai.gateway.router import get_router
            from {{cookiecutter.project_name}}.platform.contracts import ModelMessage

            facts = recall_facts(ctx, user_id=payload.user_id, query=payload.input)
            memory_block = format_memory_context(facts)
            prompt = payload.input
            if memory_block:
                prompt = f"{memory_block}\n\nUser message:\n{payload.input}"
            model = get_router().model_for(task="default")
            reply = await model.complete([ModelMessage(role="user", content=prompt)])
            return {"output": reply.content or ""}

        return router


PACK = _Pack()
