from datetime import datetime

from {{cookiecutter.project_name}}.core.identifiers import new_id
from {{cookiecutter.project_name}}.core.time import utcnow


def test_new_id_uses_prefix_and_is_unique() -> None:
    """
    Identifiers carry their domain prefix and never collide.
    """
    first = new_id("usr")
    second = new_id("usr")

    assert first.startswith("usr_")
    assert second.startswith("usr_")
    assert first != second


def test_utcnow_is_timezone_aware() -> None:
    """
    Timestamps are always timezone-aware UTC.
    """
    before = utcnow()
    moment = utcnow()
    after = utcnow()

    assert isinstance(moment, datetime)
    assert moment.tzinfo is not None
    assert before <= moment <= after
