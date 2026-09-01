"""Tests for cited, cached, authorization-scoped RAG answers."""

from __future__ import annotations

from {{cookiecutter.project_name}}.ai.knowledge.answer import (
    AnswerRequest,
    RAGAnswerService,
)
from {{cookiecutter.project_name}}.platform.contracts import (
    CacheKey,
    DocumentChunk,
    ModelResponse,
    RetrievalHit,
    Scope,
    Usage,
)


class FakeRetriever:
    def __init__(self, hits: list[RetrievalHit]) -> None:
        self.hits = hits
        self.queries = []

    async def search(self, query):  # noqa: ANN001
        self.queries.append(query)
        return self.hits


class FakeModel:
    calls = 0

    async def generate(self, request):  # noqa: ANN001
        self.calls += 1
        return ModelResponse(
            content="Use the retention policy.",
            model=request.model,
            provider="fake",
            usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
        )


class FakeCache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: CacheKey) -> str | None:
        return self.values.get(key.value())

    async def put(self, key: CacheKey, value: str, ttl_seconds: int) -> None:
        self.values[key.value()] = value

    async def invalidate(self, namespace: str) -> int:
        return 0


def _hit(principal: str) -> RetrievalHit:
    return RetrievalHit(
        chunk=DocumentChunk(
            chunk_id="doc:v1:0",
            document_id="doc",
            version_id="v1",
            text="retention policy",
            ordinal=0,
            source_uri="manual://policy",
            content_hash="sha256:1",
            acl=(principal,),
        ),
        score=0.9,
        rank=1,
    )


async def test_answer_carries_citation_and_uses_versioned_cache() -> None:
    retriever = FakeRetriever([_hit("user-1")])
    model = FakeModel()
    service = RAGAnswerService(
        retriever=retriever,
        model=model,
        cache=FakeCache(),
    )
    request = AnswerRequest(
        query="What is the retention policy?",
        scope=Scope(principal_id="user-1", organization_id="org-1"),
        model_version="m1",
        knowledge_version="k1",
    )

    first = await service.answer(request)
    second = await service.answer(request)

    assert first.abstained is False
    assert first.citations[0].source_uri == "manual://policy"
    assert second.cached is True
    assert model.calls == 1
    assert retriever.queries[0].scope.organization_id == "org-1"


async def test_answer_abstains_without_authorized_evidence() -> None:
    service = RAGAnswerService(
        retriever=FakeRetriever([]),
        model=FakeModel(),
    )

    response = await service.answer(AnswerRequest(
        query="unknown",
        scope=Scope(principal_id="user-1", organization_id="org-1"),
    ))

    assert response.abstained is True
    assert response.answer == ""
