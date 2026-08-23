from datetime import UTC, datetime


def utcnow() -> datetime:
    """
    Current timezone-aware UTC timestamp.
    """
    return datetime.now(UTC)
