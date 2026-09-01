"""NK feature pack: MCP Assistant."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.llm.features.base import FeaturePackMeta
from {{cookiecutter.project_name}}.llm.features.common.context import FeatureContext
from {{cookiecutter.project_name}}.llm.features.common.research import research_outline, summarize_text



class _Pack:
    meta = FeaturePackMeta(
        id="mcp_assistant",
        name="MCP Assistant",
        requires=('llm', 'agents'),
    )

    def register_tools(
        self,
        registry: ToolRegistry,
        *,
        ctx: FeatureContext | None = None,
    ) -> None:
        pass

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/mcp-assistant", tags=["llm-features"])

        class Payload(BaseModel):
            input: str = Field(min_length=1, max_length=100_000)

        @router.post("/status")
        async def _handle(payload: Payload, request: Request) -> dict[str, str]:
            return {"output": "MCP assistant ready; connect via agents/mcp_bridge"}

        return router


PACK = _Pack()
