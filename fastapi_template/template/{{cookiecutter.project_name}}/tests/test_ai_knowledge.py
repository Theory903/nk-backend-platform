import pytest

from tests._fakes import ScriptedEmbeddingProvider

from {{cookiecutter.project_name}}.ai.knowledge import (
    HybridRetriever,
    InMemoryVectorStore,
    TextChunker,
)


def _make_retriever() -> HybridRetriever:
    return HybridRetriever(
        embeddings=ScriptedEmbeddingProvider(),
        store=InMemoryVectorStore(),
    )


def test_chunker_splits_with_overlap() -> None:
    chunker = TextChunker(chunk_size=10, overlap=2)
    chunks = chunker.chunk("abcdefghij" * 3, source="doc.txt")
    assert len(chunks) > 1
    assert chunks[0].source == "doc.txt"
    assert all(c.text for c in chunks)


def test_chunker_empty_text() -> None:
    chunker = TextChunker(chunk_size=10, overlap=2)
    assert chunker.chunk("") == []


@pytest.mark.asyncio
async def test_retriever_ingest_and_search() -> None:
    retriever = _make_retriever()
    count = await retriever.ingest("doc_1", "the quick brown fox jumps over the lazy dog", source="test")
    assert count > 0
    results = await retriever.retrieve("quick brown fox", top_k=3)
    assert len(results) > 0
    assert results[0].score > 0
