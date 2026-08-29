"""Unit tests for Mongo outbox relay (mocked collection — no live Mongo)."""

{%- if cookiecutter.orm == "beanie" %}
from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from {{cookiecutter.project_name}}.core.events import EventEnvelope
from {{cookiecutter.project_name}}.core.time import utcnow
from {{cookiecutter.project_name}}.data.adapters.mongo.outbox import (
    OutboxDocument,
    OutboxRelay,
    _is_duplicate_key_error,
    record_event,
)


def test_is_duplicate_key_error_direct_code() -> None:
    exc = Exception("dup")
    exc.code = 11000  # type: ignore[attr-defined]
    assert _is_duplicate_key_error(exc) is True


def test_is_duplicate_key_error_nested_cause() -> None:
    cause = Exception("E11000 duplicate key")
    cause.code = 11000  # type: ignore[attr-defined]
    exc = Exception("wrapped")
    exc.__cause__ = cause
    assert _is_duplicate_key_error(exc) is True


def test_is_duplicate_key_error_string_fallback() -> None:
    assert _is_duplicate_key_error(Exception("E11000 duplicate key error")) is True
    assert _is_duplicate_key_error(Exception("something else")) is False


def test_outbox_document_accepts_claim_fields() -> None:
    now = utcnow()
    # Beanie Document.__init__ touches the collection; stub it for unit tests.
    with patch.object(
        OutboxDocument,
        "get_pymongo_collection",
        return_value=MagicMock(),
    ):
        doc = OutboxDocument.model_validate(
            {
                "_id": "evt_1",
                "type": "order.created",
                "payload": "{}",
                "created_at": now,
                "published_at": None,
                "claim_id": "worker-a",
                "claim_until": now + timedelta(seconds=30),
                "attempts": 2,
                "failed_at": None,
            },
        )
    assert doc.id == "evt_1"
    assert doc.claim_id == "worker-a"
    assert doc.attempts == 2
    assert doc.failed_at is None


@pytest.mark.asyncio
async def test_claim_filter_skips_failed_and_uses_timedelta_lease() -> None:
    now = utcnow()
    raw = {
        "_id": "evt_claim",
        "type": "t",
        "payload": json.dumps({"id": "evt_claim", "type": "t"}),
        "created_at": now,
        "published_at": None,
        "claim_id": "will-be-set",
        "claim_until": now + timedelta(seconds=60),
        "attempts": 1,
        "failed_at": None,
    }

    collection = AsyncMock()
    collection.find_one_and_update = AsyncMock(return_value=raw)

    async def sink(_payload: dict) -> None:
        return None

    relay = OutboxRelay(publish=sink, claim_timeout_s=45.0, max_attempts=10)

    with patch.object(OutboxDocument, "get_pymongo_collection", return_value=collection):
        claimed = await relay._claim()

    assert claimed is not None
    assert claimed.id == "evt_claim"

    filter_arg = collection.find_one_and_update.await_args.args[0]
    assert filter_arg["published_at"] is None
    assert filter_arg["failed_at"] is None
    assert "$or" in filter_arg

    update_arg = collection.find_one_and_update.await_args.args[1]
    assert update_arg["$set"]["claim_id"] == relay.worker_id
    lease = update_arg["$set"]["claim_until"]
    # lease ≈ now + 45s (aware UTC timedelta, not fromtimestamp)
    assert lease.tzinfo is not None
    delta = lease - now
    assert timedelta(seconds=40) <= delta <= timedelta(seconds=50)


@pytest.mark.asyncio
async def test_claim_dead_letters_over_max_attempts() -> None:
    now = utcnow()
    raw = {
        "_id": "evt_dead",
        "type": "t",
        "payload": "{}",
        "created_at": now,
        "published_at": None,
        "claim_id": "w",
        "claim_until": now,
        "attempts": 11,
        "failed_at": None,
    }

    collection = AsyncMock()
    collection.find_one_and_update = AsyncMock(return_value=raw)
    collection.update_one = AsyncMock()

    relay = OutboxRelay(publish=AsyncMock(), max_attempts=10)

    with patch.object(OutboxDocument, "get_pymongo_collection", return_value=collection):
        claimed = await relay._claim()

    assert claimed is None
    collection.update_one.assert_awaited_once()
    dead_update = collection.update_one.await_args.args[1]
    assert "failed_at" in dead_update["$set"]
    assert "claim_id" in dead_update["$unset"]


@pytest.mark.asyncio
async def test_poll_once_claim_publish_mark_flow() -> None:
    now = utcnow()
    envelope = EventEnvelope(type="order.created", source="/orders", data={"n": 1})
    payload_json = envelope.model_dump_json()
    raw = {
        "_id": envelope.id,
        "type": envelope.type,
        "payload": payload_json,
        "created_at": envelope.time,
        "published_at": None,
        "claim_id": "worker",
        "claim_until": now + timedelta(seconds=60),
        "attempts": 1,
        "failed_at": None,
    }

    seen: list[dict] = []

    async def sink(payload: dict) -> None:
        seen.append(payload)

    collection = AsyncMock()
    # First claim returns the doc; second returns None (batch end)
    collection.find_one_and_update = AsyncMock(side_effect=[raw, None])
    collection.update_one = AsyncMock(
        return_value=SimpleNamespace(modified_count=1),
    )

    relay = OutboxRelay(publish=sink, batch_size=10)

    with patch.object(OutboxDocument, "get_pymongo_collection", return_value=collection):
        handled = await relay.poll_once()

    assert handled == 1
    assert len(seen) == 1
    assert seen[0]["type"] == "order.created"
    assert seen[0]["id"] == envelope.id

    # mark published called once
    assert collection.update_one.await_count == 1
    mark_filter = collection.update_one.await_args.args[0]
    assert mark_filter["_id"] == envelope.id
    assert mark_filter["claim_id"] == relay.worker_id
    assert "published_at" in collection.update_one.await_args.args[1]["$set"]


@pytest.mark.asyncio
async def test_poll_once_releases_claim_on_publish_failure() -> None:
    now = utcnow()
    raw = {
        "_id": "evt_fail",
        "type": "t",
        "payload": json.dumps({"id": "evt_fail", "type": "t", "source": "/t", "data": {}}),
        "created_at": now,
        "published_at": None,
        "claim_id": "w",
        "claim_until": now + timedelta(seconds=30),
        "attempts": 1,
        "failed_at": None,
    }

    async def boom(_payload: dict) -> None:
        raise RuntimeError("broker down")

    collection = AsyncMock()
    collection.find_one_and_update = AsyncMock(side_effect=[raw, None])
    collection.update_one = AsyncMock()

    relay = OutboxRelay(publish=boom, batch_size=5)

    with patch.object(OutboxDocument, "get_pymongo_collection", return_value=collection):
        handled = await relay.poll_once()

    assert handled == 0
    # release claim (unset claim fields), not mark published
    release = collection.update_one.await_args.args[1]
    assert "$unset" in release
    assert "published_at" not in release.get("$set", {})


@pytest.mark.asyncio
async def test_record_event_duplicate_returns_existing() -> None:
    envelope = EventEnvelope(type="dup", source="/t", data={})
    existing = MagicMock(id=envelope.id)
    instance = MagicMock()
    instance.create = AsyncMock(
        side_effect=Exception("E11000 duplicate key error collection: platform_outbox"),
    )

    with patch(
        "{{cookiecutter.project_name}}.data.adapters.mongo.outbox.OutboxDocument",
    ) as Doc:
        Doc.return_value = instance
        Doc.get = AsyncMock(return_value=existing)
        result = await record_event(envelope)

    assert result is existing
    Doc.get.assert_awaited_once_with(envelope.id)


{%- endif %}
