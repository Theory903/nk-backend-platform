"""PostgreSQL + pgvector implementation of the VectorStore protocol.

Requires PostgreSQL with pgvector extension and the pgvector Python package.
Selected via settings: vector_store = "pgvector"
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False


class PgVectorStore:
    """PostgreSQL-backed vector store using pgvector extension and HNSW index."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession],
                 *, table_name: str = "nk_embeddings", dimensions: int = 384) -> None:
        if not HAS_PGVECTOR:
            raise RuntimeError("pgvector package required: pip install pgvector")
        self._sf = session_factory
        self.table_name = table_name
        self.dimensions = dimensions

    async def ensure_table(self) -> None:
        """Create embedding table + HNSW index if not present."""
        async with self._sf() as session:
            await session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            create_sql = text(
                f"CREATE TABLE IF NOT EXISTS {self.table_name} ("
                f"chunk_id VARCHAR PRIMARY KEY, "
                f"embedding vector({self.dimensions}), "
                "metadata JSONB DEFAULT \'{}\'::jsonb)"
            )
            await session.execute(create_sql)
            index_sql = text(
                f"CREATE INDEX IF NOT EXISTS {self.table_name}_hnsw "
                f"ON {self.table_name} USING hnsw (embedding vector_cosine_ops)"
            )
            try:
                await session.execute(index_sql)
            except Exception:
                pass
            await session.commit()

    async def upsert(self, chunk_id: str, embedding: list[float],
                     metadata: dict[str, Any]) -> None:
        vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
        meta_json = json.dumps(metadata)
        async with self._sf() as session:
            sql = text(
                f"INSERT INTO {self.table_name} (chunk_id, embedding, metadata) "
                f"VALUES (:cid, :vec::vector, :meta::jsonb) "
                f"ON CONFLICT (chunk_id) DO UPDATE SET "
                f"embedding = :vec::vector, metadata = :meta::jsonb"
            )
            await session.execute(sql, {"cid": chunk_id, "vec": vec_str, "meta": meta_json})
            await session.commit()

    async def search(self, query_embedding: list[float], top_k: int = 5
                     ) -> list[tuple[str, float, dict[str, Any]]]:
        vec_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
        async with self._sf() as session:
            sql = text(
                f"SELECT chunk_id, "
                f"1 - (embedding <=> :qv::vector) AS similarity, "
                f"metadata FROM {self.table_name} "
                f"ORDER BY embedding <=> :qv::vector LIMIT :k"
            )
            result = await session.execute(sql, {"qv": vec_str, "k": top_k})
            rows = result.fetchall()
            return [
                (row[0], float(row[1]), json.loads(row[2]) if isinstance(row[2], str) else (row[2] or {}))
                for row in rows
            ]

    async def delete(self, chunk_id: str) -> bool:
        async with self._sf() as session:
            sql = text(f"DELETE FROM {self.table_name} WHERE chunk_id = :cid")
            result = await session.execute(sql, {"cid": chunk_id})
            await session.commit()
            return getattr(result, "rowcount", 0) > 0
