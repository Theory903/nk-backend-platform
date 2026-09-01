"""Append-only session event types for agent run replay (P13)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SessionEventKind(StrEnum):
    RUN_STARTED = "RunStarted"
    CONTEXT_BUILT = "ContextBuilt"
    MODEL_CALLED = "ModelCalled"
    TOOL_CALLED = "ToolCalled"
    MEMORY_READ = "MemoryRead"
    MEMORY_WRITE = "MemoryWrite"
    APPROVAL_REQUESTED = "ApprovalRequested"
    RUN_COMPLETED = "RunCompleted"
    RUN_FAILED = "RunFailed"


class SessionEvent(BaseModel):
    """One immutable event in a run's append-only stream."""

    event_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    thread_id: str
    sequence: int = Field(ge=0)
    kind: SessionEventKind
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    payload: dict[str, Any] = Field(default_factory=dict)


class RunMeta(BaseModel):
    """Index metadata for a durable agent run."""

    run_id: UUID
    thread_id: str
    principal_id: str
    organization_id: str
    status: str = "running"
    task: str = ""
    parent_run_id: UUID | None = None
    forked_from_sequence: int | None = None
    workflow_id: UUID | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


__all__ = ["RunMeta", "SessionEvent", "SessionEventKind"]
