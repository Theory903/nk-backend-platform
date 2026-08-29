"""Transactional domain-event emitter and outbox utilities."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.core.events import EventEnvelope
from {{cookiecutter.project_name}}.data.adapters.sqlalchemy.outbox import (
    OutboxRow,
    record_event,
)


class EventEmitError(RuntimeError):
    """Raised when an event cannot be safely emitted."""


async def emit(
    event_type: str,
    source: str,
    data: Mapping[str, Any],
    *,
    session: AsyncSession,
) -> EventEnvelope:
    """
    Append an event to the transactional outbox.

    The caller must execute this inside the same database transaction as
    the business mutation. The outbox row therefore commits or rolls back
    together with the business operation.
    """

    if not event_type.strip():
        raise ValueError(
            "event_type must not be empty"
        )

    if not source.strip():
        raise ValueError(
            "source must not be empty"
        )

    if session.in_transaction() is False:
        raise EventEmitError(
            "emit() requires an active database transaction"
        )

    envelope = EventEnvelope(
        type=event_type,
        source=source,
        data=dict(data),
    )

    await record_event(
        session,
        envelope,
    )

    return envelope


async def count_pending(
    session: AsyncSession,
) -> int:
    """Return the number of unpublished outbox events."""

    stmt = (
        select(func.count())
        .select_from(OutboxRow)
        .where(
            OutboxRow.published_at.is_(None)
        )
    )

    result = await session.execute(stmt)

    return int(
        result.scalar_one()
    )
