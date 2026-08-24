import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from {{cookiecutter.project_name}}.core.events import EventEnvelope
from {{cookiecutter.project_name}}.core.time import utcnow
from {{cookiecutter.project_name}}.db.base import Base

Publisher = Callable[[dict[str, Any]], Awaitable[None]]


class OutboxRow(Base):
    __tablename__ = "platform_outbox"

    id: Mapped[str] = mapped_column(primary_key=True)
    type: Mapped[str]
    payload: Mapped[str]
    created_at: Mapped[datetime]
    published_at: Mapped[datetime | None] = mapped_column(default=None)


async def record_event(session: AsyncSession, event: EventEnvelope) -> None:
    """
    Stage an envelope inside the caller's open transaction.
    """
    session.add(
        OutboxRow(
            id=event.id,
            type=event.type,
            payload=event.model_dump_json(),
            created_at=event.time,
            published_at=None,
        ),
    )


class OutboxRelay:
    """
    Polling publisher claiming pending rows with FOR UPDATE SKIP LOCKED.

    Publishes before marking: a crash between the two re-delivers later,
    making delivery at-least-once; consumers deduplicate on envelope id.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        publish: Publisher,
        batch_size: int = 100,
    ) -> None:
        self._session_factory = session_factory
        self.publish = publish
        self.batch_size = batch_size

    async def poll_once(self) -> int:
        handled = 0
        async with self._session_factory() as session:
            async with session.begin():
                rows = (
                    (
                        await session.execute(
                            select(OutboxRow)
                            .where(OutboxRow.published_at.is_(None))
                            .order_by(OutboxRow.created_at)
                            .limit(self.batch_size)
                            .with_for_update(skip_locked=True),
                        )
                    )
                    .scalars()
                    .all()
                )
                for row in rows:
                    await self.publish(json.loads(row.payload))
                    row.published_at = utcnow()
                handled = len(rows)
        return handled


async def cleanup_published(
    session_factory: async_sessionmaker[AsyncSession],
    older_than_days: int = 7,
) -> int:
    """
    Delete published rows older than the retention window.
    """
    cutoff = utcnow() - timedelta(days=older_than_days)
    async with session_factory() as session:
        async with session.begin():
            result = await session.execute(
                sa_delete(OutboxRow).where(
                    OutboxRow.published_at.is_not(None),
                    OutboxRow.published_at < cutoff,
                ),
            )
        return result.rowcount or 0
