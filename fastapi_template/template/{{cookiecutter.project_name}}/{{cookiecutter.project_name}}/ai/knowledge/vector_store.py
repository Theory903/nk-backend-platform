import math
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class VectorStore(Protocol):
    """Abstract vector index; pgvector/qdrant adapters implement this."""

    async def upsert(self, chunk_id: str, embedding: list[float], metadata: dict[str, Any]) -> None: ...

    async def search(self, query_embedding: list[float], top_k: int) -> list[tuple[str, float, dict[str, Any]]]: ...

    async def delete(self, chunk_id: str) -> bool: ...


class InMemoryVectorStore:
    """Cosine-similarity store for dev/test; production swaps to pgvector."""

    def __init__(self) -> None:
        self._vectors: dict[str, tuple[list[float], dict[str, Any]]] = {}

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    async def upsert(self, chunk_id: str, embedding: list[float], metadata: dict[str, Any]) -> None:
        self._vectors[chunk_id] = (embedding, metadata)

    async def search(self, query_embedding: list[float], top_k: int) -> list[tuple[str, float, dict[str, Any]]]:
        scored = [
            (chunk_id, self._cosine(query_embedding, emb), meta)
            for chunk_id, (emb, meta) in self._vectors.items()
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    async def delete(self, chunk_id: str) -> bool:
        return bool(self._vectors.pop(chunk_id, None) is not None)
