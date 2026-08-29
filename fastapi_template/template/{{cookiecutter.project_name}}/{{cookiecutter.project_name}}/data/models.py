"""Canonical domain record shared across storage adapters."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Record(BaseModel):
    """
    Canonical domain record.

    This model is storage-agnostic and is shared by SQLAlchemy,
    Mongo/Beanie, and other repository implementations.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    id: str | None = None
    name: str = Field(min_length=1, max_length=255)
    created_at: datetime | None = None
    deleted_at: datetime | None = None
    version: int = Field(default=1, ge=1)
    org_id: str | None = None

    @property
    def is_deleted(self) -> bool:
        """Whether the record has been soft-deleted."""
        return self.deleted_at is not None

    @property
    def is_persisted(self) -> bool:
        """Whether the record has a persistence identifier."""
        return self.id is not None


__all__ = ["Record"]
