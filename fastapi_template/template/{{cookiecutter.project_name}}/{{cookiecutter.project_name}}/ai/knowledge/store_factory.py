"""Auto-select vector store backend: memory · pgvector · Qdrant (P1)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from {{cookiecutter.project_name}}.ai.knowledge.vector_store import InMemoryVectorStore, VectorStore
from {{cookiecutter.project_name}}.settings import settings

logger = logging.getLogger(__name__)


def _probe_qdrant(url: str, *, timeout_s: float = 2.0) -> bool:
    try:
        with urlopen(f"{url.rstrip('/')}/readyz", timeout=timeout_s) as response:
            return response.status == 200
    except URLError:
        return False
    except Exception:
        return False


def _qdrant_url() -> str:
    host = settings.qdrant_host.strip()
    if host.startswith("http://") or host.startswith("https://"):
        return host.rstrip("/")
    return f"http://{host}:{settings.qdrant_port}"


def resolve_vector_backend(app: Any) -> str:
    """Pick a concrete backend name from settings + runtime capabilities."""
    backend = settings.vector_store_backend.strip().lower()
    if backend != "auto":
        return backend

    session_factory = getattr(app.state, "db_session_factory", None)
    {%- if cookiecutter.db_info.name == "postgresql" and cookiecutter.orm == "sqlalchemy" %}
    if session_factory is not None:
        return "pgvector"
    {%- endif %}

    if _probe_qdrant(_qdrant_url()):
        return "qdrant"
    return "memory"


async def create_vector_store(app: Any) -> VectorStore:
    """Construct and optionally initialize the configured vector store."""
    backend = resolve_vector_backend(app)
    dimensions = settings.embedding_dimensions

    if backend == "pgvector":
        session_factory = getattr(app.state, "db_session_factory", None)
        if session_factory is None:
            logger.warning("pgvector requested but no DB session; using memory")
            return InMemoryVectorStore()
        try:
            from {{cookiecutter.project_name}}.ai.knowledge.pgvector_store import PgVectorStore

            store = PgVectorStore(
                session_factory,
                dimensions=dimensions,
            )
            await store.ensure_table()
            logger.info("vector store backend: pgvector")
            return store
        except Exception as exc:
            logger.warning("pgvector unavailable, using in-memory vectors: %s", exc)
            return InMemoryVectorStore()

    if backend == "qdrant":
        url = _qdrant_url()
        try:
            from {{cookiecutter.project_name}}.ai.knowledge.qdrant_store import QdrantVectorStore

            store = QdrantVectorStore(
                url=url,
                collection=settings.qdrant_collection,
                dimensions=dimensions,
            )
            await store.ensure_collection()
            logger.info("vector store backend: qdrant (%s)", url)
            return store
        except Exception as exc:
            logger.warning("qdrant unavailable, using in-memory vectors: %s", exc)
            return InMemoryVectorStore()

    logger.info("vector store backend: memory")
    return InMemoryVectorStore()


__all__ = ["create_vector_store", "resolve_vector_backend"]
