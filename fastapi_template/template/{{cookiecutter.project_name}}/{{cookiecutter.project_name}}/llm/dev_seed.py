"""Idempotent dev-plane seed for local AI demos (P0).

Runs once at startup when ``environment`` is ``dev`` / ``development``.
Indexes a sample document for RAG and stores demo memory facts.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from {{cookiecutter.project_name}}.settings import settings

logger = logging.getLogger(__name__)

_DEMO_USER = "demo-user"
_SAMPLE_DOC = """\
# NK AI Platform (dev seed)

This project is a portable AI application runtime built on FastAPI.
Feature packs include chat_over_docs, agentic_rag, memory_chat, and advanced_agents.
Local inference uses Ollama with llama3.2 by default.
Run `uv run nk ai doctor` to verify the stack.
"""

_DEMO_FACTS = (
    "Prefers local Ollama over cloud APIs in development.",
    "Working on the NK AI platform feature packs.",
)


async def seed_dev_plane(app: FastAPI) -> None:
    """Seed RAG documents and memory facts once in dev."""
    if getattr(app.state, "dev_ai_seeded", False):
        return
    env = settings.environment.lower()
    if env not in {"dev", "development"}:
        return

    ctx = getattr(app.state, "feature_context", None)
    if ctx is None:
        return

    try:
        if ctx.hybrid_retriever is not None:
            from {{cookiecutter.project_name}}.llm.features.common.agentic import ingest_text

            await ingest_text(
                ctx,
                text=_SAMPLE_DOC,
                source="dev-seed:nk-platform",
                organization_id="default",
            )
        if ctx.memory_store is not None:
            from {{cookiecutter.project_name}}.llm.features.common.memory_tools import remember_fact

            for fact in _DEMO_FACTS:
                remember_fact(ctx, user_id=_DEMO_USER, fact=fact)
        app.state.dev_ai_seeded = True
        logger.info("dev AI plane seeded (RAG + memory)")
    except Exception:
        logger.exception("dev AI seed failed (non-fatal)")


__all__ = ["seed_dev_plane"]
