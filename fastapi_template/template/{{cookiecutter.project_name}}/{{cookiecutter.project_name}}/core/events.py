from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from {{cookiecutter.project_name}}.core.identifiers import new_id
from {{cookiecutter.project_name}}.core.time import utcnow


class EventEnvelope(BaseModel):
    """
    CloudEvents 1.0 envelope wrapping every domain event.
    """

    specversion: str = "1.0"
    id: str = Field(default_factory=lambda: new_id("evt"))
    type: str
    source: str
    time: datetime = Field(default_factory=utcnow)
    data: dict[str, Any] = Field(default={})
