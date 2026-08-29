"""Tests for agentic RAG loop: plan, retrieve, grade, reformulate, generate."""
from typing import Any
import pytest

from {{cookiecutter.project_name}}.agents.agentic_rag import (
    AgenticRagLoop,
    AgenticRagResult,
    RetrievedChunk,
)


class FakeChatModel:
    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = responses or ["Default answer"]
        self._call_count = 0

    async def complete(self, messages: list, tools: list) -> Any:
        self._call_count += 1
        idx = min(self._call_count - 1, len(self.responses) - 1)

        class Reply:
            def __init__(self, content):
                self.content = content
                self.tool_calls = []

        return Reply(self.responses[idx])


class FakeRetriever:
    def __init__(self, chunks_per_query=None) -> None:
        self.chunks_per_query = chunks_per_query or {}

    async def search(self, query: str = "", top_k: int = 5) -> list:
        return self.chunks_per_query.get(query, [])


class TestAgenticRagLoop:
    @pytest.mark.asyncio
    async def test_simple_answer_no_retrieval_needed(self) -> None:
        model = FakeChatModel(responses=["Paris is the capital of France."])
        retriever = FakeRetriever()
        rag = AgenticRagLoop(model, retriever)
        result = await rag.run("Hello there!")
        assert not result.used_retrieval
        assert result.answer == "Paris is the capital of France."
        assert len(result.citations) == 0

    @pytest.mark.asyncio
    async def test_retrieval_triggers_on_question(self) -> None:
        model = FakeChatModel(responses=["Based on the docs, the answer is X."])
        good_chunks = [
            ("c1", 0.9, {"text": "X is documented here", "source": "docs.md"}),
        ]
        retriever = FakeRetriever(chunks_per_query={
            "what is X?": [(cid, score, meta) for cid, score, meta in [
                (f"c{i}", 0.8 + i * 0.05, {"text": f"doc {i}", "source": "d.md"})
                for i in range(3)
            ]]
        })
        rag = AgenticRagLoop(model, retriever)
        result = await rag.run("what is X?")
        assert result.used_retrieval
        assert result.retrieval_rounds >= 1
        assert len(result.citations) > 0

    @pytest.mark.asyncio
    async def test_budget_limits_rounds(self) -> None:
        model = FakeChatModel()
        # Always return low-scored chunks (never relevant enough)
        retriever = FakeRetriever(chunks_per_query={
            k: [("c", 0.1, {"text": "irrelevant"})] for k in [
                "explain complex thing",
                "Please provide more details about: explain complex thing",
            ]
        })
        rag = AgenticRagLoop(model, retriever, max_rounds=2, relevance_threshold=0.5)
        result = await rag.run("explain complex thing")
        assert result.used_retrieval
        assert result.retrieval_rounds <= 2

    @pytest.mark.asyncio
    async def test_trace_captures_pipeline_stages(self) -> None:
        model = FakeChatModel()
        retriever = FakeRetriever(chunks_per_query={
            "how does it work?": [("c1", 0.9, {"text": "it works like this"})]
        })
        rag = AgenticRagLoop(model, retriever)
        result = await rag.run("how does it work?")
        assert any("plan" in t for t in result.trace)
        assert any("retrieve" in t for t in result.trace)
        assert any("generate" in t for t in result.trace)
