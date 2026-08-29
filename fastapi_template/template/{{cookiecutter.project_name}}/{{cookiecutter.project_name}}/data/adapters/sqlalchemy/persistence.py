"""SQLAlchemy persistence model for the Record domain entity."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from {{cookiecutter.project_name}}.core.identifiers import new_id
from {{cookiecutter.project_name}}.core.time import utcnow
from {{cookiecutter.project_name}}.data.models import Record
from {{cookiecutter.project_name}}.db.base import Base


class RecordRow(Base):
    """PostgreSQL/SQL representation of a Record."""

    __tablename__ = "platform_records"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )

    version: Mapped[int] = mapped_column(
        nullable=False,
        default=1,
    )

    org_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    __table_args__ = (
        Index(
            "ix_platform_records_org_created",
            "org_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_platform_records_active_org_created",
            "org_id",
            "deleted_at",
            "created_at",
            "id",
        ),
    )

    @classmethod
    def from_domain(
        cls,
        item: Record,
    ) -> RecordRow:
        """Convert a domain Record into a persistence row."""

        return cls(
            id=item.id or new_id("rec"),
            name=item.name,
            created_at=item.created_at or utcnow(),
            deleted_at=item.deleted_at,
            version=item.version,
            org_id=item.org_id,
        )

    def to_domain(self) -> Record:
        """Convert the persistence row into a domain Record."""

        return Record(
            id=self.id,
            name=self.name,
            created_at=self.created_at,
            deleted_at=self.deleted_at,
            version=self.version,
            org_id=self.org_id,
        )


__all__ = [
    "RecordRow",
]