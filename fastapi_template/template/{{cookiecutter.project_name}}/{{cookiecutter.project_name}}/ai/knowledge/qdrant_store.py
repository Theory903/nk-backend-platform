"""Qdrant implementation of the VectorStore protocol (P1 scale backend).

Requires ``qdrant-client`` (``uv sync --extra ai-platform``).
Selected via settings: ``vector_store_backend = "qdrant"``.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import NAMESPACE_URL, uuid5

logger = logging.getLogger(__name__)

try:
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.http import models as qmodels

    HAS_QDRANT = True
except ImportError:
    HAS_QDRANT = False
    AsyncQdrantClient = None  # type: ignore[assignment,misc]
    qmodels = None  # type: ignore[assignment,misc]


def _point_id(chunk_id: str) -> str:
    """Map arbitrary chunk ids to Qdrant-compatible UUID strings."""
    return str(uuid5(NAMESPACE_URL, chunk_id))


class QdrantVectorStore:
    """Async Qdrant index with cosine distance."""

    def __init__(
        self,
        *,
        url: str,
        collection: str = "nk_embeddings",
        dimensions: int = 384,
    ) -> None:
        if not HAS_QDRANT:
            raise RuntimeError(
                "qdrant-client required: uv sync --extra ai-platform",
            )
        self._client = AsyncQdrantClient(url=url)
        self.collection = collection
        self.dimensions = dimensions

    async def ensure_collection(self) -> None:
        """Create the collection if missing."""
        exists = await self._client.collection_exists(self.collection)
        if exists:
            return
        await self._client.create_collection(
            collection_name=self.collection,
            vectors_config=qmodels.VectorParams(  # type: ignore[union-attr]
                size=self.dimensions,
                distance=qmodels.Distance.COSINE,  # type: ignore[union-attr]
            ),
        )
        logger.info("created Qdrant collection %s", self.collection)

    async def upsert(
        self,
        chunk_id: str,
        embedding: list[float],
        metadata: dict[str, Any],
    ) -> None:
        await self._client.upsert(
            collection_name=self.collection,
            points=[
                qmodels.PointStruct(  # type: ignore[union-attr]
                    id=_point_id(chunk_id),
                    vector=embedding,
                    payload={**metadata, "chunk_id": chunk_id},
                ),
            ],
        )

    async def search(
        self,
        query_embedding: list[float],
        top_k: int,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        results = await self._client.query_points(
            collection_name=self.collection,
            query=query_embedding,
            limit=top_k,
            with_payload=True,
        )
        rows: list[tuple[str, float, dict[str, Any]]] = []
        for point in results.points:
            payload = dict(point.payload or {})
            chunk_id = str(payload.pop("chunk_id", point.id))
            rows.append((chunk_id, float(point.score or 0.0), payload))
        return rows

    async def delete(self, chunk_id: str) -> bool:
        await self._client.delete(
            collection_name=self.collection,
            points_selector=qmodels.PointIdsList(  # type: ignore[union-attr]
                points=[_point_id(chunk_id)],
            ),
        )
        return True


__all__ = ["HAS_QDRANT", "QdrantVectorStore"]
