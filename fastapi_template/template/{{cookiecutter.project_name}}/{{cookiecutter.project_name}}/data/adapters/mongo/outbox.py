"""MongoDB transactional outbox with reliable at-least-once delivery."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from beanie import Document
from pydantic import Field
from pymongo import ReturnDocument

from {{cookiecutter.project_name}}.core.events import EventEnvelope
from {{cookiecutter.project_name}}.core.time import utcnow

logger = logging.getLogger(__name__)

Publisher = Callable[[dict[str, Any]], Awaitable[None]]


class OutboxDocument(Document):
    """
    Durable MongoDB representation of a domain event.

    Claim fields (``claim_id``, ``claim_until``, ``attempts``, ``failed_at``)
    are written by the relay via raw PyMongo and must live on the model so
    ``model_validate`` after ``find_one_and_update`` succeeds.

    Recommended compound index for claim polling (create in ops/migration)::

        (published_at, claim_until, created_at)

    Delivery is at-least-once: consumers must deduplicate by EventEnvelope.id.
    """

    id: str
    type: str
    payload: str
    created_at: datetime = Field(default_factory=utcnow)
    published_at: datetime | None = None
    claim_id: str | None = None
    claim_until: datetime | None = None
    attempts: int = 0
    failed_at: datetime | None = None

    class Settings:
        name = "platform_outbox"
        validate_on_save = True


async def record_event(
    event: EventEnvelope,
) -> OutboxDocument:
    """
    Persist an event for asynchronous delivery.

    The event ID is the document ID, making repeated writes idempotent.
    Uses EventEnvelope ``id``, ``type``, ``time``, and ``model_dump_json``.
    """

    document = OutboxDocument(
        id=event.id,
        type=event.type,
        payload=event.model_dump_json(),
        created_at=event.time,
    )

    try:
        return await document.create()
    except Exception as exc:
        # Duplicate event IDs are safe: the original event already exists.
        if _is_duplicate_key_error(exc):
            existing = await OutboxDocument.get(event.id)
            if existing is not None:
                return existing
        raise


def _is_duplicate_key_error(exc: Exception) -> bool:
    """
    Detect MongoDB duplicate-key errors without hard PyMongo coupling.

    DuplicateKeyError is often nested (``__cause__`` / ``args``) or only
    visible as an ``E11000`` message after Beanie wraps the driver error.
    """

    if getattr(exc, "code", None) == 11000:
        return True

    cause = getattr(exc, "__cause__", None)
    if cause is not None and getattr(cause, "code", None) == 11000:
        return True
    if cause is not None and "E11000" in str(cause):
        return True

    for arg in getattr(exc, "args", ()):
        if getattr(arg, "code", None) == 11000:
            return True
        if isinstance(arg, BaseException) and getattr(arg, "code", None) == 11000:
            return True
        if "E11000" in str(arg):
            return True

    return "E11000" in str(exc)


class OutboxRelay:
    """
    Reliable outbox relay.

    Delivery semantics are at-least-once:

        claim -> publish -> mark published

    If the process crashes after publishing but before marking the row,
    the event can be published again. Consumers must therefore deduplicate
    by EventEnvelope.id.

    Multiple relay instances are supported through an atomic claim lease.
    Permanently failed events (``failed_at`` set after max_attempts) are
    never reclaimed.
    """

    def __init__(
        self,
        publish: Publisher,
        *,
        batch_size: int = 100,
        claim_timeout_s: float = 60.0,
        poll_interval_s: float = 1.0,
        max_attempts: int = 10,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")

        if claim_timeout_s <= 0:
            raise ValueError("claim_timeout_s must be greater than zero")

        if poll_interval_s < 0:
            raise ValueError("poll_interval_s cannot be negative")

        if max_attempts <= 0:
            raise ValueError("max_attempts must be greater than zero")

        self.publish = publish
        self.batch_size = batch_size
        self.claim_timeout_s = claim_timeout_s
        self.poll_interval_s = poll_interval_s
        self.max_attempts = max_attempts
        self.worker_id = secrets.token_urlsafe(16)

    async def poll_once(self) -> int:
        """Claim and process one bounded batch of outbox events."""

        handled = 0

        for _ in range(self.batch_size):
            document = await self._claim()

            if document is None:
                break

            try:
                payload = self._decode_payload(document)

                await self.publish(payload)

                await self._mark_published(document)

                handled += 1

            except Exception:
                logger.exception(
                    "outbox delivery failed",
                    extra={
                        "event_id": document.id,
                        "event_type": document.type,
                        "worker_id": self.worker_id,
                    },
                )

                await self._release_claim(document)

        return handled

    async def run(
        self,
        *,
        stop_event: asyncio.Event,
    ) -> None:
        """Continuously relay events until the stop event is set."""

        while not stop_event.is_set():
            try:
                handled = await self.poll_once()

                if handled == 0:
                    try:
                        await asyncio.wait_for(
                            stop_event.wait(),
                            timeout=self.poll_interval_s,
                        )
                    except asyncio.TimeoutError:
                        pass

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception("outbox relay iteration failed")

                try:
                    await asyncio.wait_for(
                        stop_event.wait(),
                        timeout=self.poll_interval_s,
                    )
                except asyncio.TimeoutError:
                    pass

    async def _claim(self) -> OutboxDocument | None:
        """
        Atomically claim one unpublished event.

        A lease prevents two relay workers from processing the same event
        concurrently while still allowing recovery after worker failure.
        Documents with ``failed_at`` set are dead-lettered and skipped.
        """

        now = utcnow()
        lease_until = now + timedelta(seconds=self.claim_timeout_s)

        collection = OutboxDocument.get_pymongo_collection()

        document = await collection.find_one_and_update(
            {
                "published_at": None,
                "failed_at": None,
                "$or": [
                    {"claim_until": None},
                    {"claim_until": {"$exists": False}},
                    {"claim_until": {"$lte": now}},
                ],
            },
            {
                "$set": {
                    "claim_id": self.worker_id,
                    "claim_until": lease_until,
                },
                "$inc": {
                    "attempts": 1,
                },
            },
            sort=[
                ("created_at", 1),
                ("_id", 1),
            ],
            return_document=ReturnDocument.AFTER,
        )

        if document is None:
            return None

        attempts = int(document.get("attempts", 0))

        if attempts > self.max_attempts:
            logger.error(
                "outbox event exceeded maximum delivery attempts",
                extra={
                    "event_id": document["_id"],
                    "attempts": attempts,
                },
            )

            await collection.update_one(
                {
                    "_id": document["_id"],
                    "claim_id": self.worker_id,
                },
                {
                    "$set": {
                        "failed_at": utcnow(),
                    },
                    "$unset": {
                        "claim_id": "",
                        "claim_until": "",
                    },
                },
            )

            return None

        return OutboxDocument.model_validate(
            document,
        )

    @staticmethod
    def _decode_payload(
        document: OutboxDocument,
    ) -> dict[str, Any]:
        payload = json.loads(document.payload)

        if not isinstance(payload, dict):
            raise ValueError(
                "outbox payload must decode to an object"
            )

        return payload

    async def _mark_published(
        self,
        document: OutboxDocument,
    ) -> None:
        collection = OutboxDocument.get_pymongo_collection()

        result = await collection.update_one(
            {
                "_id": document.id,
                "claim_id": self.worker_id,
                "published_at": None,
            },
            {
                "$set": {
                    "published_at": utcnow(),
                },
                "$unset": {
                    "claim_id": "",
                    "claim_until": "",
                },
            },
        )

        if result.modified_count != 1:
            raise RuntimeError(
                f"lost outbox claim for event '{document.id}'"
            )

    async def _release_claim(
        self,
        document: OutboxDocument,
    ) -> None:
        collection = OutboxDocument.get_pymongo_collection()

        await collection.update_one(
            {
                "_id": document.id,
                "claim_id": self.worker_id,
                "published_at": None,
            },
            {
                "$unset": {
                    "claim_id": "",
                    "claim_until": "",
                },
            },
        )


__all__ = [
    "OutboxDocument",
    "OutboxRelay",
    "Publisher",
    "record_event",
]
