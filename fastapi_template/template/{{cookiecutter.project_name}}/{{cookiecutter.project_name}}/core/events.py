"""CloudEvents 1.0 envelope used by the platform event system."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from {{cookiecutter.project_name}}.core.identifiers import new_id
from {{cookiecutter.project_name}}.core.time import utcnow


class EventEnvelope(BaseModel):
    """
    CloudEvents 1.0 structured event envelope.

    The envelope is immutable after creation so the event identity and
    routing metadata cannot accidentally change before persistence.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="allow",
        validate_assignment=True,
    )

    specversion: str = Field(
        default="1.0",
        frozen=True,
    )

    id: str = Field(
        default_factory=lambda: new_id("evt"),
        min_length=1,
        frozen=True,
    )

    type: str = Field(
        min_length=1,
    )

    source: str = Field(
        min_length=1,
    )

    time: datetime = Field(
        default_factory=utcnow,
        frozen=True,
    )

    data: dict[str, Any] = Field(
        default_factory=dict,
    )

    @field_validator("type", "source")
    @classmethod
    def validate_non_empty(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "event type/source must not be empty"
            )

        return value

    @field_validator("time")
    @classmethod
    def validate_timezone(
        cls,
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            raise ValueError(
                "event time must be timezone-aware"
            )

        return value