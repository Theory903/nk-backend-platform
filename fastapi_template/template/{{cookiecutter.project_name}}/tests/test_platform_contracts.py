"""Contract and dependency-injection tests for every generated profile."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from {{cookiecutter.project_name}}.platform.contracts import (
    CacheKey,
    DocumentChunk,
    MemoryKind,
    ModelMessage,
    ModelRequest,
    Scope,
    ToolDescriptor,
    ToolInvocation,
    ToolRisk,
)
from {{cookiecutter.project_name}}.platform.di import (
    DependencyContainer,
    DependencyError,
)


def _scope() -> Scope:
    return Scope(
        principal_id="user-1",
        organization_id="org-1",
        project_id="project-1",
        run_id="run-1",
        thread_id="thread-1",
    )


def test_scope_namespaces_are_tenant_and_purpose_specific() -> None:
    scope = _scope()

    assert scope.namespace("memory") == "org-1:project-1:user-1:memory"
    assert scope.namespace("cache") != scope.namespace("memory")


def test_contracts_validate_provenance_and_cache_versions() -> None:
    chunk = DocumentChunk(
        chunk_id="doc-1:0",
        document_id="doc-1",
        version_id="v1",
        text="retrievable content",
        ordinal=0,
        source_uri="s3://bucket/doc-1",
        content_hash="sha256:abc",
        created_at=datetime.now(timezone.utc),
    )
    request = ModelRequest(
        model="test-model",
        messages=[ModelMessage(role="user", content="hello")],
        tools=[ToolDescriptor(
            name="lookup",
            description="Lookup data",
            risk=ToolRisk.LOW,
        )],
    )
    invocation = ToolInvocation(
        descriptor=request.tools[0],
        arguments={},
        scope=_scope(),
    )
    key = CacheKey(
        namespace=_scope().namespace("answer"),
        operation="answer",
        request_hash="hash",
        model_version="model-v1",
        knowledge_version=chunk.version_id,
    )

    assert request.tools[0].name == "lookup"
    assert invocation.scope.organization_id == "org-1"
    assert key.value().endswith("model-v1|_|v1")
    assert MemoryKind.WORKING.value == "working"


def test_dependency_container_supports_lazy_resolution_and_errors() -> None:
    container = DependencyContainer()
    builds = 0

    class Clock:
        pass

    def build_clock() -> Clock:
        nonlocal builds
        builds += 1
        return Clock()

    container.factory(Clock, build_clock)
    first = container.resolve(Clock)
    second = container.resolve(Clock)

    assert first is second
    assert builds == 1
    assert container.has(Clock)

    with pytest.raises(DependencyError, match="no provider"):
        container.resolve(str)
