import math
from dataclasses import dataclass, field
from typing import Any

from {{cookiecutter.project_name}}.ai.embeddings import EmbeddingProvider
from {{cookiecutter.project_name}}.ai.knowledge.chunking import Chunk, TextChunker
from {{cookiecutter.project_name}}.ai.knowledge.vector_store import VectorStore


@dataclass
class RetrievedChunk:
    chunk_id: str
    score: float
    text: str
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def _keyword_score(query: str, text: str) -> float:
    if not query or not text:
        return 0.0
    q_terms = set(query.lower().split())
    t_words = text.lower().split()
    if not t_words:
        return 0.0
    matches = sum(1 for w in t_words if w in q_terms)
    return matches / math.sqrt(len(t_words))


class HybridRetriever:
    """Dense (vector) + keyword fusion with reciprocal rank scoring."""

    def __init__(
        self,
        embeddings: EmbeddingProvider,
        store: VectorStore,
        chunker: TextChunker | None = None,
        keyword_weight: float = 0.3,
        dense_weight: float = 0.7,
    ) -> None:
        self.embeddings = embeddings
        self.store = store
        self.chunker = chunker or TextChunker()
        self.keyword_weight = keyword_weight
        self.dense_weight = dense_weight
        self._chunks: dict[str, Chunk] = {}  # type: ignore[type-arg]

    async def ingest(self, doc_id: str, text: str, source: str = "") -> int:
        chunks = self.chunker.chunk(text, source=source)
        count = 0
        for chunk in chunks:
            chunk_id = f"{doc_id}:{chunk.index}"
            embedding = self.embeddings.embed(chunk.text)
            await self.store.upsert(chunk_id, embedding, {"text": chunk.text, "source": source})
            self._chunks[chunk_id] = chunk
            count += 1
        return count

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        keyword_bonus: float | None = None,
    ) -> list[RetrievedChunk]:
        kw = keyword_bonus if keyword_bonus is not None else self.keyword_weight
        dense_w = 1.0 - kw
        query_embedding = self.embeddings.embed(query)
        raw = await self.store.search(query_embedding, top_k=top_k * 2)
        results: list[RetrievedChunk] = []
        for chunk_id, dense_score, meta in raw:
            text = meta.get("text", "")
            k_score = _keyword_score(query, text)
            combined = dense_w * max(0.0, dense_score) + kw * min(1.0, k_score)
            results.append(RetrievedChunk(
                chunk_id=chunk_id,
                score=combined,
                text=text,
                source=meta.get("source", ""),
                metadata=dict(meta),
            ))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]
