"""Beanie persistence model for the Record domain entity."""

from __future__ import annotations

from datetime import datetime

from beanie import Document
from pydantic import Field

from {{cookiecutter.project_name}}.core.time import utcnow
from {{cookiecutter.project_name}}.data.models import Record


class RecordDocument(Document):
    """MongoDB representation of a Record."""

    name: str
    created_at: datetime = Field(
        default_factory=utcnow,
    )
    deleted_at: datetime | None = None
    version: int = Field(
        default=1,
        ge=1,
    )
    org_id: str | None = None

    class Settings:
        name = "platform_records"

        # Prevent Beanie from silently changing the collection shape.
        validate_on_save = True

    @classmethod
    def from_domain(
        cls,
        item: Record,
    ) -> RecordDocument:
        """Convert a domain Record into a MongoDB document."""

        return cls(
            id=item.id,
            name=item.name,
            created_at=(
                item.created_at
                if item.created_at is not None
                else utcnow()
            ),
            deleted_at=item.deleted_at,
            version=item.version,
            org_id=item.org_id,
        )

    def to_domain(self) -> Record:
        """Convert the persistence document into a domain Record."""

        return Record(
            id=str(self.id),
            name=self.name,
            created_at=self.created_at,
            deleted_at=self.deleted_at,
            version=self.version,
            org_id=self.org_id,
        )
