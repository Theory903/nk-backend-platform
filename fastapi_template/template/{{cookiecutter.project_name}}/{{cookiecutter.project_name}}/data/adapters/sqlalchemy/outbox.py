"""Production transactional outbox for SQLAlchemy.

Guarantees:
- business writes and outbox writes share the caller's transaction
- concurrent relays use SELECT ... FOR UPDATE SKIP LOCKED
- delivery is at-least-once
- failed publishes do not mark events as published
- stale published events can be cleaned safely
- indexes support the relay's hot query path
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import DateTime, Index, delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from {{cookiecutter.project_name}}.core.events import EventEnvelope
from {{cookiecutter.project_name}}.core.time import utcnow
from {{cookiecutter.project_name}}.db.base import Base

logger = logging.getLogger(__name__)

Publisher = Callable[[dict[str, Any]], Awaitable[None]]


class OutboxRow(Base):
    """Durable transactional-outbox event."""

    __tablename__ = "platform_outbox"

    id: Mapped[str] = mapped_column(
        primary_key=True,
    )

    type: Mapped[str] = mapped_column(
        nullable=False,
    )

    payload: Mapped[str] = mapped_column(
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    __table_args__ = (
        Index(
            "ix_platform_outbox_pending",
            "published_at",
            "created_at",
        ),
    )


async def record_event(
    session: AsyncSession,
    event: EventEnvelope,
) -> OutboxRow:
    """
    Stage an event in the caller's active transaction.

    The caller owns commit/rollback. Do not commit here.
    """

    row = OutboxRow(
        id=event.id,
        type=event.type,
        payload=event.model_dump_json(),
        created_at=event.time,
    )

    session.add(row)

    return row


class OutboxRelay:
    """
    Concurrent-safe transactional-outbox relay.

    Multiple workers may call poll_once() concurrently.

    Rows are locked with SKIP LOCKED, published, then marked as published
    in the same database transaction.

    Delivery remains at-least-once because a process crash after publishing
    but before committing the published_at update causes redelivery.
    Consumers must therefore deduplicate by event ID.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        publish: Publisher,
        *,
        batch_size: int = 100,
    ) -> None:
        if batch_size <= 0:
            raise ValueError(
                "batch_size must be greater than zero",
            )

        self._session_factory = session_factory
        self._publish = publish
        self._batch_size = batch_size

    async def poll_once(self) -> int:
        """
        Process one bounded batch.

        Returns the number of successfully published events.
        """

        successful = 0

        async with self._session_factory() as session:
            rows = await self._claim_batch(
                session,
            )

            for row in rows:
                try:
                    payload = _decode_payload(
                        row.payload,
                    )

                    await self._publish(
                        payload,
                    )

                    row.published_at = utcnow()

                    successful += 1

                except Exception:
                    logger.exception(
                        "outbox publish failed",
                        extra={
                            "event_id": row.id,
                            "event_type": row.type,
                        },
                    )

                    # Do not mark failed events as published.
                    # The transaction is rolled back below.
                    await session.rollback()

                    # published_at updates above were rolled back, so
                    # earlier in-batch publishes are not durable either.
                    successful = 0

                    # A rollback expires the locks and allows another
                    # relay attempt.
                    break

            if successful:
                await session.commit()
            else:
                # Explicitly release the transaction/locks.
                await session.rollback()

        return successful

    async def _claim_batch(
        self,
        session: AsyncSession,
    ) -> list[OutboxRow]:
        """
        Select pending rows using row-level locks.

        PostgreSQL, MySQL 8+, and other compatible SQL backends can execute
        concurrent relay workers without processing the same row at once.
        """

        result = await session.execute(
            select(OutboxRow)
            .where(
                OutboxRow.published_at.is_(None),
            )
            .order_by(
                OutboxRow.created_at.asc(),
                OutboxRow.id.asc(),
            )
            .limit(self._batch_size)
            .with_for_update(
                skip_locked=True,
            ),
        )

        return list(
            result.scalars().all(),
        )


def _decode_payload(
    payload: str,
) -> dict[str, Any]:
    """Decode and validate an outbox payload."""

    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "invalid outbox JSON payload",
        ) from exc

    if not isinstance(value, dict):
        raise ValueError(
            "outbox payload must be a JSON object",
        )

    return value


async def cleanup_published(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    older_than_days: int = 7,
    batch_size: int = 5_000,
) -> int:
    """
    Delete published events older than the retention period.

    Deletes in bounded batches instead of issuing one potentially enormous
    DELETE transaction.
    """

    if older_than_days <= 0:
        raise ValueError(
            "older_than_days must be greater than zero",
        )

    if batch_size <= 0:
        raise ValueError(
            "batch_size must be greater than zero",
        )

    cutoff = utcnow() - timedelta(
        days=older_than_days,
    )

    deleted = 0

    async with session_factory() as session:
        while True:
            result = await session.execute(
                select(OutboxRow.id)
                .where(
                    OutboxRow.published_at.is_not(None),
                    OutboxRow.published_at < cutoff,
                )
                .order_by(
                    OutboxRow.published_at.asc(),
                    OutboxRow.id.asc(),
                )
                .limit(batch_size),
            )

            ids = list(
                result.scalars().all(),
            )

            if not ids:
                break

            result = await session.execute(
                sa_delete(OutboxRow).where(
                    OutboxRow.id.in_(ids),
                ),
            )

            deleted += int(
                result.rowcount or 0,
            )

            await session.commit()

            if len(ids) < batch_size:
                break

    return deleted


__all__ = [
    "OutboxRelay",
    "OutboxRow",
    "cleanup_published",
    "record_event",
]