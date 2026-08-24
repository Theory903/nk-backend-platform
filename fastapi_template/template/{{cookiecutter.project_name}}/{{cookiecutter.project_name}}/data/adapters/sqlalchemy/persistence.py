from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from {{cookiecutter.project_name}}.core.identifiers import new_id
from {{cookiecutter.project_name}}.core.time import utcnow
from {{cookiecutter.project_name}}.data.models import Record
from {{cookiecutter.project_name}}.db.base import Base


class RecordRow(Base):
    __tablename__ = "platform_records"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    created_at: Mapped[datetime]

    @classmethod
    def from_domain(cls, item: Record) -> "RecordRow":
        return cls(
            id=item.id or new_id("rec"),
            name=item.name,
            created_at=item.created_at or utcnow(),
        )

    def to_domain(self) -> Record:
        return Record(id=self.id, name=self.name, created_at=self.created_at)
