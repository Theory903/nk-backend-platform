"""Light validation tests for the canonical Record domain model."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from {{cookiecutter.project_name}}.data.models import Record


def test_record_defaults_version_to_one() -> None:
    record = Record(name="alpha")

    assert record.version == 1
    assert record.id is None
    assert record.deleted_at is None
    assert record.org_id is None


def test_record_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        Record(name="")


def test_record_rejects_version_below_one() -> None:
    with pytest.raises(ValidationError):
        Record(name="alpha", version=0)


def test_record_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Record.model_validate(
            {
                "name": "alpha",
                "unexpected": True,
            },
        )


def test_record_is_deleted_and_is_persisted() -> None:
    live = Record(name="alpha")
    assert live.is_deleted is False
    assert live.is_persisted is False

    deleted = Record(
        id="rec_1",
        name="alpha",
        deleted_at=datetime.now(timezone.utc),
    )
    assert deleted.is_deleted is True
    assert deleted.is_persisted is True
