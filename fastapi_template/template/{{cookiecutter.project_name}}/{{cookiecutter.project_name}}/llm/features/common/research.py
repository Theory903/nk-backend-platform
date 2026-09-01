"""Shared research / summarization helpers."""

from __future__ import annotations

from {{cookiecutter.project_name}}.ai.gateway.router import get_router
from {{cookiecutter.project_name}}.platform.contracts import ModelMessage


async def summarize_text(text: str, *, focus: str = "") -> str:
    """Summarize text through the model gateway."""
    model = get_router().model_for(task="fast")
    prompt = "Summarize the following text concisely."
    if focus:
        prompt += f" Focus on: {focus}."
    reply = await model.complete(
        [
            ModelMessage(role="system", content=prompt),
            ModelMessage(role="user", content=text[:50_000]),
        ],
    )
    return reply.content or ""


async def research_outline(topic: str, *, sections: int = 5) -> str:
    """Produce a structured research outline."""
    model = get_router().model_for(task="reasoning")
    reply = await model.complete(
        [
            ModelMessage(
                role="user",
                content=(
                    f"Create a {sections}-section research outline for: {topic}. "
                    "Use markdown headings only."
                ),
            ),
        ],
    )
    return reply.content or ""
