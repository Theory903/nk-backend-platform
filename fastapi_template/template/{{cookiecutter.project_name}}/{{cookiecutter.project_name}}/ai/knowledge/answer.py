"""Authorization-first RAG answering with citations and abstention."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from {{cookiecutter.project_name}}.platform.contracts import (
    CacheKey,
    CacheProvider,
    ModelMessage,
    ModelProvider,
    ModelRequest,
    RetrievalHit,
    RetrievalProvider,
    RetrievalQuery,
    Scope,
    Usage,
)


class Citation(BaseModel):
    """Source reference returned with an answer."""

    chunk_id: str
    document_id: str
    source_uri: str
    version_id: str
    score: float


class AnswerRequest(BaseModel):
    """RAG request with explicit tenant scope and context budget."""

    model_config = ConfigDict(protected_namespaces=())

    query: str = Field(min_length=1)
    scope: Scope
    top_k: int = Field(default=5, ge=1, le=20)
    max_context_chars: int = Field(default=12_000, ge=500, le=100_000)
    min_score: float = Field(default=0.0, ge=0.0)
    model: str = "default"
    model_version: str | None = None
    prompt_version: str = "rag-v1"
    knowledge_version: str | None = None


class AnswerResponse(BaseModel):
    """Stable answer envelope for HTTP, agents, and evaluation."""

    model_config = ConfigDict(protected_namespaces=())

    answer: str = ""
    citations: list[Citation] = Field(default_factory=list)
    abstained: bool = False
    abstention_reason: str | None = None
    freshness_checked_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    usage: Usage = Field(default_factory=Usage)
    cached: bool = False
    model: str | None = None
    provider: str | None = None
    model_version: str | None = None


class RAGAnswerService:
    """Compose retrieval, model generation, exact cache, and provenance."""

    def __init__(
        self,
        *,
        retriever: RetrievalProvider,
        model: ModelProvider,
        cache: CacheProvider | None = None,
    ) -> None:
        self.retriever = retriever
        self.model = model
        self.cache = cache

    async def answer(self, request: AnswerRequest) -> AnswerResponse:
        """Return a cited answer or an explicit abstention."""
        hits = await self.retriever.search(
            RetrievalQuery(
                query=request.query,
                top_k=request.top_k,
                scope=request.scope,
            )
        )
        usable = [hit for hit in hits if hit.score >= request.min_score]
        # Retrieval and ACL filtering must happen before cache lookup.  This
        # prevents revoked documents from being served by an old answer cache.
        key = self._cache_key(request, usable)
        if self.cache is not None:
            cached = await self.cache.get(key)
            if cached is not None:
                response = AnswerResponse.model_validate_json(cached)
                response.cached = True
                return response

        if not usable:
            provider, model, adapter_version = self._model_identity(request)
            response = AnswerResponse(
                abstained=True,
                abstention_reason="no authorized evidence met the retrieval threshold",
                model=model,
                provider=provider,
                model_version=request.model_version or adapter_version,
            )
            await self._cache(key, response)
            return response

        context, selected = _fit_context(usable, request.max_context_chars)
        model_response = await self.model.generate(
            ModelRequest(
                model=request.model,
                messages=[
                    ModelMessage(
                        role="system",
                        content=(
                            "Answer only from the supplied evidence. "
                            "If evidence is insufficient, say so explicitly."
                        ),
                    ),
                    ModelMessage(
                        role="user",
                        content=f"Question: {request.query}\nEvidence:\n{context}",
                    ),
                ],
            )
        )
        response = AnswerResponse(
            answer=model_response.content,
            citations=[
                Citation(
                    chunk_id=hit.chunk.chunk_id,
                    document_id=hit.chunk.document_id,
                    source_uri=hit.chunk.source_uri,
                    version_id=hit.chunk.version_id,
                    score=hit.score,
                )
                for hit in selected
            ],
            usage=model_response.usage,
            model=model_response.model,
            provider=model_response.provider,
            model_version=model_response.version,
        )
        expected_provider, expected_model, _ = self._model_identity(request)
        if (
            model_response.provider == expected_provider
            and model_response.model == expected_model
        ):
            await self._cache(key, response)
        return response

    def _cache_key(
        self,
        request: AnswerRequest,
        evidence: list[RetrievalHit],
    ) -> CacheKey:
        provider, resolved_model, adapter_version = self._model_identity(request)
        resolved_version = request.model_version or adapter_version or "unversioned"
        payload = {
            "query": request.query.strip().casefold(),
            "requested_model": request.model,
            "model": resolved_model,
            "provider": provider,
            "model_version": resolved_version,
            "top_k": request.top_k,
            "max_context_chars": request.max_context_chars,
            "min_score": request.min_score,
            "scope": request.scope.namespace("rag"),
            "evidence": [
                {
                    "chunk_id": hit.chunk.chunk_id,
                    "version_id": hit.chunk.version_id,
                    "content_hash": hit.chunk.content_hash,
                    "score": hit.score,
                }
                for hit in evidence
            ],
        }
        request_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return CacheKey(
            namespace=request.scope.namespace("rag"),
            operation="answer",
            request_hash=request_hash,
            model_version=resolved_version,
            prompt_version=request.prompt_version,
            knowledge_version=request.knowledge_version,
        )

    def _model_identity(
        self,
        request: AnswerRequest,
    ) -> tuple[str, str, str | None]:
        identity_for = getattr(self.model, "identity_for", None)
        if callable(identity_for):
            provider, model, version = identity_for(request.model)
            return str(provider), str(model), version
        return (
            str(getattr(self.model, "provider", type(self.model).__name__)),
            str(getattr(self.model, "model_name", None) or request.model),
            getattr(self.model, "version", None),
        )

    async def _cache(self, key: CacheKey, response: AnswerResponse) -> None:
        if self.cache is not None:
            await self.cache.put(key, response.model_dump_json(), ttl_seconds=300)


def _fit_context(
    hits: list[RetrievalHit],
    max_chars: int,
) -> tuple[str, list[RetrievalHit]]:
    selected: list[RetrievalHit] = []
    parts: list[str] = []
    used = 0
    for hit in hits:
        part = f"[{hit.chunk.chunk_id}] {hit.chunk.text}"
        if selected and used + len(part) > max_chars:
            break
        selected.append(hit)
        parts.append(part)
        used += len(part)
    return "\n\n".join(parts), selected


__all__ = [
    "AnswerRequest",
    "AnswerResponse",
    "Citation",
    "RAGAnswerService",
]
