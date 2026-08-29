"""Agentic RAG built on LangGraph.

Flow:
    plan -> retrieve -> grade -> re-retrieve -> generate

NK owns:
- result contracts
- budgets
- retrieval abstraction
- model abstraction
- citation representation

LangGraph owns:
- state
- orchestration
- conditional routing
- execution lifecycle
"""

from __future__ import annotations

from contextvars import ContextVar

import inspect
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from {{cookiecutter.project_name}}.agents.budgets import Budget, BudgetTracker

_TRACKER: ContextVar[BudgetTracker | None] = ContextVar("agentic_rag_tracker", default=None)


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    text: str
    score: float
    source: str = ""
    chunk_id: str = ""


@dataclass(slots=True)
class AgenticRagResult:
    answer: str
    citations: list[RetrievedChunk] = field(default_factory=list)
    retrieval_rounds: int = 0
    used_retrieval: bool = False
    trace: list[str] = field(default_factory=list)


class _RagState(TypedDict, total=False):
    query: str
    current_query: str
    needs_retrieval: bool
    chunks: list[RetrievedChunk]
    best_chunks: list[RetrievedChunk]
    retrieval_rounds: int
    answer: str
    trace: list[str]


class AgenticRag:
    """Production Agentic RAG graph."""

    def __init__(
        self,
        chat_model: Any,
        retriever: Any,
        *,
        max_rounds: int = 2,
        top_k: int = 5,
        relevance_threshold: float = 0.5,
        budget: Budget | None = None,
    ) -> None:
        if max_rounds < 1:
            raise ValueError("max_rounds must be >= 1")

        if top_k < 1:
            raise ValueError("top_k must be >= 1")

        if not 0.0 <= relevance_threshold <= 1.0:
            raise ValueError(
                "relevance_threshold must be between 0 and 1"
            )

        self.model = chat_model
        self.retriever = retriever
        self.max_rounds = max_rounds
        self.top_k = top_k
        self.relevance_threshold = relevance_threshold
        self.budget = budget or Budget(
            max_steps=max_rounds + 3,
        )

        self._graph = self._build_graph()

    async def run(self, query: str) -> AgenticRagResult:
        """Execute the RAG graph."""
        query = query.strip()

        if not query:
            raise ValueError("query cannot be empty")

        tracker = BudgetTracker(self.budget)
        tracker.step()
        token = _TRACKER.set(tracker)

        state: _RagState = {
            "query": query,
            "current_query": query,
            "needs_retrieval": False,
            "chunks": [],
            "best_chunks": [],
            "retrieval_rounds": 0,
            "answer": "",
            "trace": [],
        }

        try:
            final_state = await self._graph.ainvoke(
                state,
                config={
                    "configurable": {
                        "budget_tracker": tracker,
                    }
                },
            )
        finally:
            _TRACKER.reset(token)

        return AgenticRagResult(
            answer=final_state.get("answer", ""),
            citations=final_state.get("best_chunks", []),
            retrieval_rounds=final_state.get(
                "retrieval_rounds",
                0,
            ),
            used_retrieval=final_state.get(
                "retrieval_rounds",
                0,
            )
            > 0,
            trace=final_state.get("trace", []),
        )

    def _build_graph(self):
        graph = StateGraph(_RagState)

        graph.add_node("plan", self._plan)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("grade", self._grade)
        graph.add_node("reformulate", self._reformulate)
        graph.add_node("generate_direct", self._generate_direct)
        graph.add_node("generate", self._generate)

        graph.add_edge(START, "plan")

        graph.add_conditional_edges(
            "plan",
            self._route_after_plan,
            {
                "retrieve": "retrieve",
                "generate_direct": "generate_direct",
            },
        )

        graph.add_edge("retrieve", "grade")

        graph.add_conditional_edges(
            "grade",
            self._route_after_grade,
            {
                "generate": "generate",
                "reformulate": "reformulate",
            },
        )

        graph.add_edge("reformulate", "retrieve")
        graph.add_edge("generate_direct", END)
        graph.add_edge("generate", END)

        return graph.compile()

    # ------------------------------------------------------------------
    # Graph nodes
    # ------------------------------------------------------------------

    async def _plan(self, state: _RagState) -> dict[str, Any]:
        query = state["query"]

        needs_retrieval = self._should_retrieve(query)

        return {
            "needs_retrieval": needs_retrieval,
            "trace": [
                *state.get("trace", []),
                f"plan: needs_retrieval={needs_retrieval}",
            ],
        }

    async def _retrieve(
        self,
        state: _RagState,
        config: Any = None,
    ) -> dict[str, Any]:
        tracker = _get_tracker(config)
        tracker.step()

        query = state["current_query"]

        chunks = await self._search(query)

        round_number = state.get(
            "retrieval_rounds",
            0,
        ) + 1

        return {
            "chunks": chunks,
            "retrieval_rounds": round_number,
            "trace": [
                *state.get("trace", []),
                (
                    f"retrieve(r={round_number}, "
                    f"q={query!r}, "
                    f"results={len(chunks)})"
                ),
            ],
        }

    async def _grade(
        self,
        state: _RagState,
    ) -> dict[str, Any]:
        chunks = state.get("chunks", [])

        graded = [
            chunk
            for chunk in chunks
            if chunk.score >= self.relevance_threshold
        ]

        best = state.get("best_chunks", [])

        if graded:
            best = self._deduplicate_chunks(
                [*best, *graded]
            )

        trace = [
            *state.get("trace", []),
            (
                f"grade: relevant={len(graded)}/"
                f"{len(chunks)}"
            ),
        ]

        return {
            "best_chunks": best,
            "trace": trace,
        }

    async def _reformulate(
        self,
        state: _RagState,
        config: Any = None,
    ) -> dict[str, Any]:
        tracker = _get_tracker(config)
        tracker.step()

        original_query = state["query"]
        poor_chunks = state.get("chunks", [])

        query = await self._reformulate_query(
            original_query,
            poor_chunks,
        )

        return {
            "current_query": query,
            "trace": [
                *state.get("trace", []),
                f"reformulate: {query!r}",
            ],
        }

    async def _generate_direct(
        self,
        state: _RagState,
        config: Any = None,
    ) -> dict[str, Any]:
        tracker = _get_tracker(config)
        tracker.step()

        reply = await self.model.complete(
            messages=[
                {
                    "role": "user",
                    "content": state["query"],
                }
            ],
            tools=[],
        )

        answer = reply.content or ""

        return {
            "answer": answer,
            "trace": [
                *state.get("trace", []),
                "generate: direct",
            ],
        }

    async def _generate(
        self,
        state: _RagState,
        config: Any = None,
    ) -> dict[str, Any]:
        tracker = _get_tracker(config)
        tracker.step()

        chunks = state.get("best_chunks", [])

        context = self._format_context(chunks)

        prompt = (
            "Answer the question using only the provided context.\n"
            "Cite supporting context using [N].\n"
            "If the context does not contain enough information, "
            "say so instead of inventing facts.\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {state['query']}"
        )

        reply = await self.model.complete(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            tools=[],
        )

        answer = reply.content or ""

        return {
            "answer": answer,
            "trace": [
                *state.get("trace", []),
                f"generate: {len(chunks)} citations",
            ],
        }

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    @staticmethod
    def _route_after_plan(
        state: _RagState,
    ) -> str:
        if state.get("needs_retrieval", False):
            return "retrieve"

        return "generate_direct"

    def _route_after_grade(
        self,
        state: _RagState,
    ) -> str:
        if state.get("best_chunks"):
            return "generate"

        rounds = state.get(
            "retrieval_rounds",
            0,
        )

        if rounds >= self.max_rounds:
            return "generate"

        return "reformulate"

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def _search(
        self,
        query: str,
    ) -> list[RetrievedChunk]:
        method = getattr(
            self.retriever,
            "search",
            None,
        )

        if method is None or not callable(method):
            raise TypeError(
                "retriever must expose search()"
            )

        result = method(
            query=query,
            top_k=self.top_k,
        )

        if inspect.isawaitable(result):
            result = await result

        return [
            chunk
            for item in result or []
            if (chunk := self._normalize_chunk(item)) is not None
        ]

    @staticmethod
    def _normalize_chunk(
        item: Any,
    ) -> RetrievedChunk | None:
        if isinstance(item, RetrievedChunk):
            return item

        if isinstance(item, tuple) and len(item) >= 3:
            chunk_id, score, metadata = item[:3]

            if not isinstance(metadata, dict):
                metadata = {}

            return RetrievedChunk(
                text=str(metadata.get("text", "")),
                score=float(score),
                source=str(
                    metadata.get("source", "")
                ),
                chunk_id=str(chunk_id),
            )

        if hasattr(item, "text"):
            return RetrievedChunk(
                text=str(item.text),
                score=float(
                    getattr(item, "score", 0.0)
                ),
                source=str(
                    getattr(item, "source", "")
                ),
                chunk_id=str(
                    getattr(item, "chunk_id", "")
                ),
            )

        return None

    @staticmethod
    def _deduplicate_chunks(
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        seen: set[str] = set()
        result: list[RetrievedChunk] = []

        for chunk in chunks:
            identity = (
                chunk.chunk_id
                or f"{chunk.source}:{chunk.text}"
            )

            if identity in seen:
                continue

            seen.add(identity)
            result.append(chunk)

        return result

    # ------------------------------------------------------------------
    # Planning / reformulation
    # ------------------------------------------------------------------

    @staticmethod
    def _should_retrieve(query: str) -> bool:
        hints = (
            "what",
            "how",
            "why",
            "when",
            "where",
            "who",
            "which",
            "explain",
            "describe",
            "find",
            "search",
            "look up",
            "according to",
            "based on",
            "document",
            "knowledge",
        )

        normalized = query.casefold()

        return any(
            hint in normalized
            for hint in hints
        )

    async def _reformulate_query(
        self,
        original_query: str,
        poor_chunks: list[RetrievedChunk],
    ) -> str:
        # Keep this deterministic until a dedicated query-rewrite model
        # is intentionally introduced.
        return (
            f"Find authoritative information relevant to: "
            f"{original_query}"
        )

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format_context(
        chunks: list[RetrievedChunk],
    ) -> str:
        if not chunks:
            return "No relevant context was retrieved."

        parts: list[str] = []

        for index, chunk in enumerate(chunks, start=1):
            source = (
                f" [{chunk.source}]"
                if chunk.source
                else ""
            )

            parts.append(
                f"[{index}]{source} {chunk.text}"
            )

        return "\n".join(parts)


def _get_tracker(
    config: Any,
) -> BudgetTracker:
    if config:
        configurable = config.get("configurable", {}) if hasattr(config, "get") else {}
        if isinstance(config, dict):
            configurable = config.get("configurable", {})
        else:
            configurable = getattr(config, "get", lambda *a, **k: {})("configurable", {}) or getattr(config, "configurable", {}) or {}
        tracker = configurable.get("budget_tracker") if isinstance(configurable, dict) else None
        if tracker is not None:
            return tracker
    tracker = _TRACKER.get()
    if tracker is None:
        raise RuntimeError("budget_tracker is missing from graph config.")
    return tracker


# Backward-compatible name used by tests and older call sites.
AgenticRagLoop = AgenticRag

__all__ = [
    "AgenticRag",
    "AgenticRagLoop",
    "AgenticRagResult",
    "RetrievedChunk",
]