"""Connector-to-index knowledge lifecycle with authorization-first search."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from {{cookiecutter.project_name}}.platform.contracts import (
    DocumentChunk,
    RetrievalHit,
    RetrievalQuery,
)


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PUBLISHED = "published"
    REVOKED = "revoked"
    DELETED = "deleted"


class DocumentVersion(BaseModel):
    """Immutable source version and lineage metadata."""

    version_id: str
    content_hash: str
    source_uri: str
    acl: tuple[str, ...] = ()
    connector: str = "manual"
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    freshness_ttl_seconds: int = Field(default=3600, ge=1)

    @property
    def stale(self) -> bool:
        return datetime.now(timezone.utc) > self.fetched_at + timedelta(
            seconds=self.freshness_ttl_seconds,
        )


class KnowledgeDocument(BaseModel):
    """Document lifecycle record independent of a particular index."""

    document_id: str
    organization_id: str
    title: str
    status: DocumentStatus = DocumentStatus.UPLOADED
    version: DocumentVersion
    chunks: list[DocumentChunk] = Field(default_factory=list)


class KnowledgeConnector(Protocol):
    async def fetch(self, source_uri: str) -> tuple[str, DocumentVersion]: ...


class KnowledgeIndex(Protocol):
    async def upsert(self, chunks: list[DocumentChunk]) -> int: ...

    async def delete_document(self, document_id: str) -> int: ...

    async def search(self, query: RetrievalQuery) -> list[RetrievalHit]: ...


class InMemoryKnowledgeCatalog:
    """Deterministic catalog/index adapter for tests and local development."""

    def __init__(self) -> None:
        self._documents: dict[str, KnowledgeDocument] = {}
        self._chunks: dict[str, DocumentChunk] = {}

    async def upload(
        self,
        *,
        organization_id: str,
        title: str,
        source_uri: str,
        content: str,
        acl: tuple[str, ...] = (),
        connector: str = "manual",
        document_id: str | None = None,
    ) -> KnowledgeDocument:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        document = KnowledgeDocument(
            document_id=document_id or str(uuid4()),
            organization_id=organization_id,
            title=title,
            version=DocumentVersion(
                version_id=str(uuid4()),
                content_hash=digest,
                source_uri=source_uri,
                acl=acl,
                connector=connector,
            ),
        )
        self._documents[document.document_id] = document
        return document

    async def publish(self, document_id: str) -> KnowledgeDocument:
        document = self._require(document_id)
        document.status = DocumentStatus.PUBLISHED
        return document

    async def revoke(self, document_id: str) -> KnowledgeDocument:
        document = self._require(document_id)
        document.status = DocumentStatus.REVOKED
        await self.delete_index(document_id)
        return document

    async def delete(self, document_id: str) -> bool:
        document = self._documents.pop(document_id, None)
        await self.delete_index(document_id)
        if document is None:
            return False
        document.status = DocumentStatus.DELETED
        return True

    async def reindex(self, document_id: str, content: str) -> KnowledgeDocument:
        document = self._require(document_id)
        document.status = DocumentStatus.PROCESSING
        await self.delete_index(document_id)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        document.version = DocumentVersion(
            version_id=str(uuid4()),
            content_hash=digest,
            source_uri=document.version.source_uri,
            acl=document.version.acl,
            connector=document.version.connector,
        )
        document.status = DocumentStatus.PUBLISHED
        document.chunks = self._chunk(document, content)
        self._chunks.update({chunk.chunk_id: chunk for chunk in document.chunks})
        return document

    async def search(self, query: RetrievalQuery) -> list[RetrievalHit]:
        """Filter tenant/status/ACL before scoring any candidate."""
        allowed = []
        principal = query.scope.principal_id
        for chunk in self._chunks.values():
            document = self._documents.get(chunk.document_id)
            if document is None or document.status is not DocumentStatus.PUBLISHED:
                continue
            if document.organization_id != query.scope.organization_id:
                continue
            if chunk.acl and principal not in chunk.acl:
                continue
            terms = set(query.query.casefold().split())
            score = sum(term in chunk.text.casefold() for term in terms)
            if score:
                allowed.append((float(score), chunk))
        allowed.sort(key=lambda item: item[0], reverse=True)
        return [
            RetrievalHit(chunk=chunk, score=score, rank=index, retrieval_method="lexical")
            for index, (score, chunk) in enumerate(allowed[: query.top_k], start=1)
        ]

    async def delete_index(self, document_id: str) -> int:
        keys = [
            chunk_id
            for chunk_id, chunk in self._chunks.items()
            if chunk.document_id == document_id
        ]
        for key in keys:
            del self._chunks[key]
        return len(keys)

    def _require(self, document_id: str) -> KnowledgeDocument:
        document = self._documents.get(document_id)
        if document is None:
            raise KeyError(f"unknown document {document_id!r}")
        return document

    @staticmethod
    def _chunk(document: KnowledgeDocument, content: str) -> list[DocumentChunk]:
        chunks = []
        for ordinal, text in enumerate(
            part.strip() for part in content.split("\n\n") if part.strip()
        ):
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{document.document_id}:{document.version.version_id}:{ordinal}",
                    document_id=document.document_id,
                    version_id=document.version.version_id,
                    text=text,
                    ordinal=ordinal,
                    source_uri=document.version.source_uri,
                    content_hash=document.version.content_hash,
                    acl=document.version.acl,
                )
            )
        return chunks


__all__ = [
    "DocumentStatus",
    "DocumentVersion",
    "InMemoryKnowledgeCatalog",
    "KnowledgeConnector",
    "KnowledgeDocument",
    "KnowledgeIndex",
]
