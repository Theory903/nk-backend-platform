"""Tests for document versioning, ACL filtering, and deletion."""

from __future__ import annotations

from {{cookiecutter.project_name}}.ai.knowledge.lifecycle import (
    DocumentStatus,
    InMemoryKnowledgeCatalog,
)
from {{cookiecutter.project_name}}.platform.contracts import Scope, RetrievalQuery


def _query(principal_id: str) -> RetrievalQuery:
    return RetrievalQuery(
        query="retention policy",
        scope=Scope(principal_id=principal_id, organization_id="org-1"),
    )


async def test_lifecycle_publishes_reindexes_and_filters_acl() -> None:
    catalog = InMemoryKnowledgeCatalog()
    document = await catalog.upload(
        organization_id="org-1",
        title="Policy",
        source_uri="manual://policy",
        content="retention policy for finance\n\nsecond section",
        acl=("user-1",),
    )
    assert document.status is DocumentStatus.UPLOADED

    await catalog.reindex(document.document_id, "retention policy for finance")
    published = await catalog.publish(document.document_id)
    assert published.status is DocumentStatus.PUBLISHED
    assert len(await catalog.search(_query("user-1"))) == 1
    assert await catalog.search(_query("user-2")) == []

    await catalog.revoke(document.document_id)
    assert await catalog.search(_query("user-1")) == []


async def test_delete_removes_document_and_index() -> None:
    catalog = InMemoryKnowledgeCatalog()
    document = await catalog.upload(
        organization_id="org-1",
        title="Delete me",
        source_uri="manual://delete",
        content="retention policy",
    )
    await catalog.reindex(document.document_id, "retention policy")
    await catalog.publish(document.document_id)

    assert await catalog.delete(document.document_id) is True
    assert await catalog.search(_query("user-1")) == []
    assert await catalog.delete(document.document_id) is False
