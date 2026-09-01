"""NK feature pack: Voice & Multimodal."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.ai.multimodal import MediaPart, validate_media
from {{cookiecutter.project_name}}.llm.features.base import FeaturePackMeta
from {{cookiecutter.project_name}}.llm.features.common.context import FeatureContext
from {{cookiecutter.project_name}}.llm.features.common.research import summarize_text


class _MediaPayload(BaseModel):
    kind: str = Field(default="file")
    uri: str = Field(min_length=1, max_length=2048)
    mime_type: str = Field(default="application/octet-stream", max_length=256)
    size_bytes: int | None = None


class _Pack:
    meta = FeaturePackMeta(
        id="voice_multimodal",
        name="Voice & Multimodal",
        requires=("llm",),
    )

    def register_tools(
        self,
        registry: ToolRegistry,
        *,
        ctx: FeatureContext | None = None,
    ) -> None:
        @agent_tool("Describe text or transcript content for accessibility")
        async def describe_content(content: str) -> str:
            return await summarize_text(content, focus="visual and audio cues")

        registry.register(describe_content)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/voice-multimodal", tags=["llm-features"])

        class Payload(BaseModel):
            input: str = Field(min_length=1, max_length=100_000)
            media: list[_MediaPayload] = Field(default_factory=list)

        @router.post("/describe")
        async def _handle(payload: Payload, request: Request) -> dict[str, str]:
            from {{cookiecutter.project_name}}.ai.gateway.router import get_router
            from {{cookiecutter.project_name}}.platform.contracts import ModelMessage

            parts = [
                MediaPart(
                    kind=item.kind,  # type: ignore[arg-type]
                    uri=item.uri,
                    mime_type=item.mime_type,
                    size_bytes=item.size_bytes,
                )
                for item in payload.media
            ]
            validate_media(parts)
            media_lines = "\n".join(
                f"- {part.kind} {part.uri} ({part.mime_type})" for part in parts
            )
            prompt = payload.input
            if media_lines:
                prompt = f"{payload.input}\n\nAttached media:\n{media_lines}"
            model = get_router().model_for(task="default")
            reply = await model.complete([ModelMessage(role="user", content=prompt)])
            return {"output": reply.content or ""}

        return router


PACK = _Pack()
