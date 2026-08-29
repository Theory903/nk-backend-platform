"""Tests for the append-only platform audit layer."""

from __future__ import annotations

import pytest

from {{cookiecutter.project_name}}.platform.audit import (
    AuditEvent,
    AuditLogger,
    AuditQuery,
    InMemoryAuditSink,
    configure_audit_logger,
    emit_audit,
)


@pytest.fixture
def logger() -> AuditLogger:
    return AuditLogger(InMemoryAuditSink())


@pytest.mark.anyio
async def test_record_creates_immutable_event_with_id_and_created_at(
    logger: AuditLogger,
) -> None:
    stored = await logger.record(
        action="order.created",
        resource="order",
        resource_id="ord_1",
        org_id="org_1",
    )
    assert stored.id.startswith("aud_")
    assert stored.created_at is not None
    assert stored.sequence == 1
    assert stored.model_config.get("frozen") is True
    with pytest.raises(Exception):
        stored.action = "mutated"  # type: ignore[misc]


@pytest.mark.anyio
async def test_sanitized_strips_password_and_token_keys(
    logger: AuditLogger,
) -> None:
    stored = await logger.record(
        action="user.update",
        detail={
            "password": "secret",
            "token": "tok_abc",
            "email": "a@b.com",
            "ACCESS_TOKEN": "x",
        },
    )
    assert "password" not in stored.detail
    assert "token" not in stored.detail
    assert "ACCESS_TOKEN" not in stored.detail
    assert stored.detail["email"] == "a@b.com"

    raw = AuditEvent(
        action="raw",
        detail={"api_key": "k", "ok": 1},
    )
    cleaned = raw.sanitized()
    assert "api_key" not in cleaned.detail
    assert cleaned.detail["ok"] == 1


@pytest.mark.anyio
async def test_duplicate_id_append_fails(logger: AuditLogger) -> None:
    first = await logger.record(action="a")
    with pytest.raises(ValueError, match="already exists"):
        await logger.sink.append(
            AuditEvent(id=first.id, action="dup"),
        )


@pytest.mark.anyio
async def test_query_filters_org_actor_action_and_limit(
    logger: AuditLogger,
) -> None:
    await logger.record(action="a", org_id="org_1", actor_id="u1")
    await logger.record(action="b", org_id="org_1", actor_id="u1")
    await logger.record(action="a", org_id="org_2", actor_id="u2")
    await logger.record(action="a", org_id="org_1", actor_id="u2")

    by_org = await logger.query(AuditQuery(org_id="org_1"))
    assert len(by_org) == 3

    by_action = await logger.query(AuditQuery(action="a"))
    assert len(by_action) == 3

    by_actor = await logger.query(
        AuditQuery(org_id="org_1", actor_id="u1"),
    )
    assert len(by_actor) == 2

    limited = await logger.query(
        AuditQuery(org_id="org_1", limit=2),
    )
    assert len(limited) == 2


@pytest.mark.anyio
async def test_empty_action_raises(logger: AuditLogger) -> None:
    with pytest.raises(ValueError, match="empty"):
        await logger.record(action="   ")


@pytest.mark.anyio
async def test_emit_audit_convenience_works() -> None:
    configure_audit_logger(InMemoryAuditSink())
    event = await emit_audit(
        "file.uploaded",
        actor_id="u9",
        resource="file",
        resource_id="f_1",
        org_id="org_9",
        detail={"bytes": 12},
    )
    assert event.action == "file.uploaded"
    assert event.actor_id == "u9"
    assert event.id.startswith("aud_")
