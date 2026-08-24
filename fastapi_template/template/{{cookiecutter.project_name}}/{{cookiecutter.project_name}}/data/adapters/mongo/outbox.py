import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from beanie import Document

from {{cookiecutter.project_name}}.core.events import EventEnvelope
from {{cookiecutter.project_name}}.core.time import utcnow

Publisher = Callable[[dict[str, Any]], Awaitable[None]]


class OutboxDocument(Document):
    id: str
    type: str
    payload: str
    created_at: datetime
    published_at: datetime | None = None

    class Settings:
        name = "platform_outbox"


async def record_event(event: EventEnvelope) -> None:
    """
    Persist an envelope for later relay. The envelope id is the primary
    key, so re-recording is naturally idempotent.
    """
    await OutboxDocument(
        id=event.id,
        type=event.type,
        payload=event.model_dump_json(),
        created_at=event.time,
        published_at=None,
    ).create()


class OutboxRelay:
    """
    Single-relay claim loop (standalone Mongo has no SKIP LOCKED).

    Delivery is at-least-once exactly as in the SQL adapter: publish
    first, mark second, consumers deduplicate on envelope id.
    """

    def __init__(self, publish: Publisher, batch_size: int = 100) -> None:
        self.publish = publish
        self.batch_size = batch_size

    async def poll_once(self) -> int:
        handled = 0
        while handled < self.batch_size:
            document = await OutboxDocument.find(
                OutboxDocument.published_at == None,  # noqa: E711
            ).sort(+OutboxDocument.created_at).first_or_none()
            if document is None:
                break
            await self.publish(json.loads(document.payload))
            document.published_at = utcnow()
            await document.save()
            handled += 1
        return handled
