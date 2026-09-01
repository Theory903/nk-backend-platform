"""Provider-neutral contracts shared by runtime and control-plane adapters."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from urllib.parse import quote
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class Scope(BaseModel):
    """Authoritative execution scope used for tenant isolation."""

    model_config = ConfigDict(frozen=True)

    principal_id: str
    organization_id: str
    project_id: str | None = None
    run_id: str | None = None
    thread_id: str | None = None

    def namespace(self, purpose: str) -> str:
        """Build a stable namespace for cache and memory providers."""
        values = [
            self.organization_id,
            self.project_id or "_",
            self.principal_id,
            purpose,
        ]
        return ":".join(quote(value, safe="") for value in values)


class ModelMessage(BaseModel):
    """Provider-neutral chat message."""

    role: str
    content: str
    name: str | None = None


class ModelRequest(BaseModel):
    """Normalized model invocation request."""

    model: str
    messages: list[ModelMessage]
    temperature: float = 0.0
    max_tokens: int | None = None
    tools: list["ToolDescriptor"] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class Usage(BaseModel):
    """Provider-normalized token and cost accounting."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float | None = None


class ModelResponse(BaseModel):
    """Normalized model response with reproducibility metadata."""

    request_id: UUID = Field(default_factory=uuid4)
    content: str = ""
    finish_reason: str = "stop"
    usage: Usage = Field(default_factory=Usage)
    model: str
    provider: str
    version: str | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentChunk(BaseModel):
    """Structure-aware indexed chunk with authorization provenance."""

    chunk_id: str
    document_id: str
    version_id: str
    text: str
    ordinal: int
    source_uri: str
    content_hash: str
    acl: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class RetrievalQuery(BaseModel):
    """Authorization-ready retrieval request."""

    query: str
    top_k: int = Field(default=5, ge=1, le=100)
    filters: dict[str, Any] = Field(default_factory=dict)
    lexical_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    dense_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    scope: Scope


class RetrievalHit(BaseModel):
    """Retrieved chunk with rank and provenance."""

    chunk: DocumentChunk
    score: float
    rank: int = Field(ge=1)
    retrieval_method: str = "hybrid"


class MemoryKind(StrEnum):
    WORKING = "working"
    CONVERSATION = "conversation"
    LONG_TERM = "long_term"


class MemoryRecord(BaseModel):
    """Scoped memory item with optimistic versioning."""

    memory_id: UUID = Field(default_factory=uuid4)
    kind: MemoryKind
    scope: Scope
    content: str
    version: int = Field(default=1, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CacheKey(BaseModel):
    """Version-aware, tenant-scoped exact/semantic cache key."""

    model_config = ConfigDict(protected_namespaces=())

    namespace: str
    operation: str
    request_hash: str
    model_version: str | None = None
    prompt_version: str | None = None
    knowledge_version: str | None = None

    def value(self) -> str:
        """Return a collision-resistant serialized key."""
        parts = (
            self.namespace,
            self.operation,
            self.request_hash,
            self.model_version or "_",
            self.prompt_version or "_",
            self.knowledge_version or "_",
        )
        return "|".join(quote(part, safe="") for part in parts)


class ToolRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ToolDescriptor(BaseModel):
    """Typed tool declaration used by every runtime adapter."""

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    risk: ToolRisk = ToolRisk.LOW
    requires_approval: bool = False
    version: str = "1"


class ToolInvocation(BaseModel):
    """A validated tool invocation request."""

    call_id: UUID = Field(default_factory=uuid4)
    descriptor: ToolDescriptor
    arguments: dict[str, Any] = Field(default_factory=dict)
    scope: Scope


class ToolResult(BaseModel):
    """Redactable tool result returned to the agent state."""

    call_id: UUID
    ok: bool
    output: str = ""
    error_code: str | None = None
    redacted: bool = False


class WorkflowStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowState(BaseModel):
    """Serializable state machine envelope for bounded workflows."""

    workflow_id: UUID = Field(default_factory=uuid4)
    scope: Scope
    status: WorkflowStatus = WorkflowStatus.CREATED
    step: str = "observe"
    revision: int = Field(default=0, ge=0)
    data: dict[str, Any] = Field(default_factory=dict)
    pending_actions: list[ToolInvocation] = Field(default_factory=list)


class PolicyDecision(BaseModel):
    """Policy result that must accompany risky execution."""

    allowed: bool
    reason: str = ""
    requires_approval: bool = False
    policy_version: str = "1"


class EvaluationResult(BaseModel):
    """Normalized quality and safety evaluation result."""

    case_id: str
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    metrics: dict[str, float] = Field(default_factory=dict)
    failures: list[str] = Field(default_factory=list)


class TraceContext(BaseModel):
    """Portable trace context without binding the app to one SDK."""

    trace_id: str
    span_id: str
    attributes: dict[str, str] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    """Human review package for a blocked action."""

    request_id: UUID = Field(default_factory=uuid4)
    invocation: ToolInvocation
    reason: str
    expires_at: datetime | None = None
    policy_version: str = "1"


@runtime_checkable
class ModelProvider(Protocol):
    async def generate(
        self,
        request: ModelRequest,
    ) -> ModelResponse: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class RetrievalProvider(Protocol):
    async def search(
        self,
        query: RetrievalQuery,
    ) -> list[RetrievalHit]: ...


@runtime_checkable
class MemoryProvider(Protocol):
    async def put(self, record: MemoryRecord) -> MemoryRecord: ...

    async def list(
        self,
        scope: Scope,
        kind: MemoryKind,
        limit: int = 50,
    ) -> list[MemoryRecord]: ...


@runtime_checkable
class CacheProvider(Protocol):
    async def get(self, key: CacheKey) -> str | None: ...

    async def put(self, key: CacheKey, value: str, ttl_seconds: int) -> None: ...

    async def invalidate(self, namespace: str) -> int: ...


@runtime_checkable
class ToolExecutor(Protocol):
    async def execute(self, invocation: ToolInvocation) -> ToolResult: ...


@runtime_checkable
class PolicyProvider(Protocol):
    async def authorize(
        self,
        invocation: ToolInvocation,
    ) -> PolicyDecision: ...


@runtime_checkable
class Evaluator(Protocol):
    async def evaluate(
        self,
        case_id: str,
        request: ModelRequest,
        response: ModelResponse,
    ) -> EvaluationResult: ...


@runtime_checkable
class TraceSink(Protocol):
    async def record(self, context: TraceContext, event: dict[str, Any]) -> None: ...


@runtime_checkable
class EscalationQueue(Protocol):
    async def enqueue(self, request: ApprovalRequest) -> None: ...


ModelRequest.model_rebuild()


__all__ = [
    "ApprovalRequest",
    "CacheKey",
    "CacheProvider",
    "DocumentChunk",
    "EmbeddingProvider",
    "EscalationQueue",
    "EvaluationResult",
    "Evaluator",
    "MemoryKind",
    "MemoryProvider",
    "MemoryRecord",
    "ModelMessage",
    "ModelProvider",
    "ModelRequest",
    "ModelResponse",
    "PolicyDecision",
    "PolicyProvider",
    "RetrievalHit",
    "RetrievalProvider",
    "RetrievalQuery",
    "Scope",
    "ToolDescriptor",
    "ToolExecutor",
    "ToolInvocation",
    "ToolResult",
    "ToolRisk",
    "TraceContext",
    "TraceSink",
    "Usage",
    "WorkflowState",
    "WorkflowStatus",
]
