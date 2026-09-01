"""Agentic RAG helpers for feature packs."""

from __future__ import annotations

import hashlib
from typing import Any

from {{cookiecutter.project_name}}.agents.agentic_rag import AgenticRag, AgenticRagResult
from {{cookiecutter.project_name}}.ai.gateway.router import get_router
from {{cookiecutter.project_name}}.llm.features.common.context import FeatureContext


class HybridRetrieverSearchAdapter:
    """Adapt HybridRetriever.retrieve to AgenticRag.search()."""

    def __init__(self, retriever: Any) -> None:
        self._retriever = retriever

    async def search(self, query: str = "", top_k: int = 5) -> list[tuple[str, float, dict[str, Any]]]:
        results = await self._retriever.retrieve(query, top_k=top_k)
        rows: list[tuple[str, float, dict[str, Any]]] = []
        for item in results:
            metadata = dict(item.metadata or {})
            metadata.setdefault("text", item.text)
            metadata.setdefault("source", item.source)
            rows.append((item.chunk_id, item.score, metadata))
        return rows


def format_agentic_result(result: AgenticRagResult) -> str:
    """Format agentic RAG output for HTTP routes and tools."""
    lines = [result.answer]
    if result.citations:
        lines.append("\nSources:")
        for cite in result.citations:
            source = cite.source or "unknown"
            lines.append(f"- {source} (score={cite.score:.2f})")
    if result.trace:
        lines.append("\nTrace:")
        lines.extend(f"- {step}" for step in result.trace)
    return "\n".join(lines)


async def run_agentic_rag(ctx: FeatureContext, query: str) -> AgenticRagResult:
    """Run the LangGraph agentic RAG loop against the configured retriever."""
    if ctx.hybrid_retriever is None:
        raise RuntimeError("hybrid retriever not configured")
    model = get_router().model_for(task="default")
    rag = AgenticRag(
        model,
        HybridRetrieverSearchAdapter(ctx.hybrid_retriever),
    )
    return await rag.run(query)


async def ingest_text(
    ctx: FeatureContext,
    *,
    text: str,
    source: str = "upload",
    organization_id: str = "default",
) -> int:
    """Chunk, embed, and index text through the hybrid retriever."""
    if ctx.hybrid_retriever is None:
        raise RuntimeError("hybrid retriever not configured")
    doc_id = hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]
    from {{cookiecutter.project_name}}.platform.contracts import Scope

    scope = Scope(principal_id="ingest", organization_id=organization_id)
    return await ctx.hybrid_retriever.ingest(
        doc_id,
        text,
        source=source,
        scope=scope,
    )


__all__ = [
    "HybridRetrieverSearchAdapter",
    "format_agentic_result",
    "ingest_text",
    "run_agentic_rag",
]
