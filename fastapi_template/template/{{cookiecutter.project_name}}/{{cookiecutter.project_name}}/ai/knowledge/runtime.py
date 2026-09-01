"""Adapters that compose the native knowledge contracts at application startup."""

from __future__ import annotations

import hashlib

from {{cookiecutter.project_name}}.ai.knowledge.retrieval import HybridRetriever
from {{cookiecutter.project_name}}.ai.llm import ChatModel, Message, ToolSpec
from {{cookiecutter.project_name}}.platform.contracts import (
    CacheKey,
    DocumentChunk,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    RetrievalHit,
    RetrievalProvider,
    RetrievalQuery,
    Usage,
)


class HybridRetrievalAdapter(RetrievalProvider):
    """Adapt the legacy hybrid index to the provider-neutral contract."""

    def __init__(self, retriever: HybridRetriever) -> None:
        self._retriever = retriever

    async def search(self, query: RetrievalQuery) -> list[RetrievalHit]:
        results = await self._retriever.retrieve(
            query.query,
            # Authorization is applied after the provider-neutral adapter
            # receives candidates, so over-fetch to avoid ACL crowding.
            top_k=min(query.top_k * 10, 100),
        )
        hits: list[RetrievalHit] = []
        for result in results:
            acl = tuple(result.metadata.get("acl", ()))
            result_org = result.metadata.get("organization_id")
            if not result_org or result_org != query.scope.organization_id:
                continue
            if acl and query.scope.principal_id not in acl:
                continue
            document_id = str(result.metadata.get("document_id", result.chunk_id))
            version_id = str(result.metadata.get("version_id", "local"))
            source_uri = str(result.metadata.get("source", result.source))
            rank = len(hits) + 1
            hits.append(
                RetrievalHit(
                    chunk=DocumentChunk(
                        chunk_id=result.chunk_id,
                        document_id=document_id,
                        version_id=version_id,
                        text=result.text,
                        ordinal=int(result.metadata.get("ordinal", rank - 1)),
                        source_uri=source_uri,
                        content_hash=hashlib.sha256(
                            result.text.encode("utf-8"),
                        ).hexdigest(),
                        acl=acl,
                        metadata=result.metadata,
                    ),
                    score=result.score,
                    rank=rank,
                ),
            )
        return hits[: query.top_k]


class ChatModelAdapter(ModelProvider):
    """Adapt the configured chat gateway to the normalized model contract."""

    def __init__(
        self,
        model: ChatModel,
        *,
        provider: str,
        model_name: str | None = None,
        version: str | None = None,
        router: object | None = None,
    ) -> None:
        self._model = model
        self.provider = provider
        self.model_name = model_name
        self.version = version
        self._router = router

    def identity_for(self, task: str) -> tuple[str, str, str | None]:
        """Return the configured identity for the requested logical route."""
        if self._router is not None:
            route = self._router.for_task(task)  # type: ignore[attr-defined]
            return route.provider, route.model, self.version
        return self.provider, self.model_name or task, self.version

    async def generate(self, request: ModelRequest) -> ModelResponse:
        model = self._model
        if self._router is not None:
            model = self._router.model_for(request.model)  # type: ignore[attr-defined]
        reply = await model.complete(
            [
                Message(role=message.role, content=message.content)
                for message in request.messages
            ],
            [
                ToolSpec(
                    name=tool.name,
                    description=tool.description,
                    parameters=tool.input_schema,
                )
                for tool in request.tools
            ],
        )
        identity = getattr(model, "last_identity", None)
        configured_provider, configured_model, version = self.identity_for(
            request.model,
        )
        provider = identity[0] if identity else configured_provider
        model_name = identity[1] if identity else configured_model
        return ModelResponse(
            content=reply.content or "",
            model=model_name,
            provider=provider,
            usage=Usage(),
            version=version,
        )


class InMemoryAnswerCache:
    """Development cache; production should supply a shared cache adapter."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    async def get(self, key: CacheKey) -> str | None:
        return self._values.get(key.value())

    async def put(self, key: CacheKey, value: str, ttl_seconds: int) -> None:
        del ttl_seconds
        self._values[key.value()] = value

    async def invalidate(self, namespace: str) -> int:
        keys = [key for key in self._values if key.startswith(f"{namespace}:")]
        for key in keys:
            del self._values[key]
        return len(keys)


class RedisAnswerCache:
    """Shared TTL cache for exact answers in multi-worker deployments."""

    def __init__(self, redis_client: object, *, prefix: str = "nk:answers") -> None:
        self._redis = redis_client
        self._prefix = prefix.rstrip(":")

    def _key(self, key: CacheKey) -> str:
        return f"{self._prefix}:{key.value()}"

    async def get(self, key: CacheKey) -> str | None:
        value = await self._redis.get(self._key(key))  # type: ignore[attr-defined]
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value

    async def put(self, key: CacheKey, value: str, ttl_seconds: int) -> None:
        await self._redis.set(  # type: ignore[attr-defined]
            self._key(key),
            value,
            ex=ttl_seconds,
        )

    async def invalidate(self, namespace: str) -> int:
        count = 0
        async for key in self._redis.scan_iter(  # type: ignore[attr-defined]
            match=f"{self._prefix}:{namespace}:*",
        ):
            count += int(await self._redis.delete(key))  # type: ignore[attr-defined]
        return count


__all__ = [
    "ChatModelAdapter",
    "HybridRetrievalAdapter",
    "InMemoryAnswerCache",
    "RedisAnswerCache",
]
