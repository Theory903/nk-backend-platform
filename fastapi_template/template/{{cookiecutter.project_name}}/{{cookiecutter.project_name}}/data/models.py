from datetime import datetime

from pydantic import BaseModel


class Record(BaseModel):
    """
    Domain record used by the universal data contract suite.
    """

    id: str | None = None
    name: str
    created_at: datetime | None = None
