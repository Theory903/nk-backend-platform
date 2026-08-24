from datetime import datetime

from beanie import Document

from {{cookiecutter.project_name}}.core.time import utcnow
from {{cookiecutter.project_name}}.data.models import Record


class RecordDocument(Document):
    name: str
    created_at: datetime

    class Settings:
        name = "platform_records"

    @classmethod
    def from_domain(cls, item: Record) -> "RecordDocument":
        return cls(name=item.name, created_at=item.created_at or utcnow())

    def to_domain(self) -> Record:
        return Record(id=str(self.id), name=self.name, created_at=self.created_at)
