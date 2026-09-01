"""Shared RAG facade for feature packs."""

from __future__ import annotations

from typing import Any

from {{cookiecutter.project_name}}.ai.knowledge.answer import AnswerRequest, AnswerResponse, RAGAnswerService
from {{cookiecutter.project_name}}.platform.contracts import Scope


async def answer_with_citations(
    service: RAGAnswerService,
    *,
    query: str,
    scope: Scope,
    top_k: int = 5,
) -> AnswerResponse:
    """Run authorized RAG with the platform answer contract."""
    return await service.answer(
        AnswerRequest(query=query, scope=scope, top_k=top_k),
    )


def format_cited_answer(response: AnswerResponse) -> str:
    """Format answer + citations for agent tool output."""
    if response.abstained:
        return response.abstention_reason or "No authorized evidence found."
    lines = [response.answer]
    if response.citations:
        lines.append("\nSources:")
        for cite in response.citations:
            lines.append(f"- {cite.source_uri} (score={cite.score:.2f})")
    return "\n".join(lines)
