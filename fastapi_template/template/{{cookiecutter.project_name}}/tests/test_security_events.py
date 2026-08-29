"""Security audit event log tests."""

from __future__ import annotations

import time
from dataclasses import FrozenInstanceError

import pytest

from {{cookiecutter.project_name}}.identity.security_events import (
    SecurityEvent,
    SecurityEventLog,
    SecurityEventType,
    SecurityOutcome,
    configure_security_log,
    emit,
    get_security_log,
)


@pytest.fixture()
def isolated_log() -> SecurityEventLog:
    log = SecurityEventLog()
    previous = get_security_log()
    configure_security_log(log)
    yield log
    configure_security_log(previous)


def test_emit_login_success_records(isolated_log: SecurityEventLog) -> None:
    event = emit(
        SecurityEventType.LOGIN_SUCCESS,
        actor_id="u1",
        org_id="org_a",
        method="password",
    )
    assert event.event_type is SecurityEventType.LOGIN_SUCCESS
    assert event.outcome is SecurityOutcome.SUCCESS
    assert event.actor_id == "u1"
    assert event.id.startswith("sec_")
    assert isolated_log.count() == 1


def test_query_filters_by_actor_org_type_outcome_since(
    isolated_log: SecurityEventLog,
) -> None:
    t0 = time.time()
    emit(
        SecurityEventType.LOGIN_SUCCESS,
        actor_id="alice",
        org_id="org1",
    )
    emit(
        SecurityEventType.LOGIN_FAILURE,
        actor_id="bob",
        org_id="org1",
        outcome=SecurityOutcome.FAILURE,
    )
    emit(
        SecurityEventType.PERMISSION_DENIED,
        actor_id="alice",
        org_id="org2",
        outcome=SecurityOutcome.DENIED,
    )

    by_actor = isolated_log.query(actor_id="alice")
    assert len(by_actor) == 2
    assert all(e.actor_id == "alice" for e in by_actor)

    by_org = isolated_log.query(org_id="org1")
    assert len(by_org) == 2

    by_type = isolated_log.query(
        event_type=SecurityEventType.LOGIN_FAILURE
    )
    assert len(by_type) == 1
    assert by_type[0].outcome is SecurityOutcome.FAILURE

    by_outcome = isolated_log.query(
        outcome=SecurityOutcome.DENIED
    )
    assert len(by_outcome) == 1
    assert (
        by_outcome[0].event_type
        is SecurityEventType.PERMISSION_DENIED
    )

    since = isolated_log.query(since=t0)
    assert len(since) == 3


def test_count(isolated_log: SecurityEventLog) -> None:
    emit(SecurityEventType.LOGIN_SUCCESS, actor_id="a")
    emit(SecurityEventType.LOGIN_SUCCESS, actor_id="b")
    emit(
        SecurityEventType.LOGIN_FAILURE,
        actor_id="a",
        outcome=SecurityOutcome.FAILURE,
    )
    assert isolated_log.count() == 3
    assert isolated_log.count(actor_id="a") == 2
    assert (
        isolated_log.count(
            event_type=SecurityEventType.LOGIN_SUCCESS
        )
        == 2
    )


def test_max_events_truncation() -> None:
    log = SecurityEventLog(max_events=3)
    for i in range(5):
        log.record(
            SecurityEventType.LOGIN_SUCCESS,
            actor_id=f"u{i}",
        )
    assert log.count() == 3
    actors = [e.actor_id for e in log.query(limit=10)]
    assert actors == ["u2", "u3", "u4"]


def test_new_enum_members_exist() -> None:
    expected = {
        "ACCOUNT_CREATED": "auth.account.created",
        "ACCOUNT_UPDATED": "auth.account.updated",
        "ACCOUNT_SUSPENDED": "auth.account.suspended",
        "ACCOUNT_DEACTIVATED": "auth.account.deactivated",
        "ACCOUNT_DELETED": "auth.account.deleted",
        "LOGIN_BLOCKED": "auth.login.blocked",
        "PASSWORD_RESET_FAILED": "auth.password.reset_failed",
        "MFA_CHALLENGE_CREATED": "auth.mfa.challenge_created",
        "MFA_CHALLENGE_FAILED": "auth.mfa.challenge_failed",
        "API_KEY_ROTATED": "auth.api_key.rotated",
        "SESSION_REUSE_DETECTED": "auth.session.reuse_detected",
        "OAUTH_LOGIN": "auth.oauth.login",
        "SCIM_USER_CREATED": "auth.scim.user_created",
        "SCIM_USER_UPDATED": "auth.scim.user_updated",
        "SCIM_USER_DEACTIVATED": "auth.scim.user_deactivated",
        "PERMISSION_DENIED": "auth.permission.denied",
    }
    for name, value in expected.items():
        member = SecurityEventType[name]
        assert member.value == value


def test_frozen_event_immutability() -> None:
    event = SecurityEvent(
        event_type=SecurityEventType.LOGIN_SUCCESS,
        actor_id="u1",
    )
    with pytest.raises(FrozenInstanceError):
        event.actor_id = "u2"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        event.outcome = SecurityOutcome.FAILURE  # type: ignore[misc]


def test_configure_security_log_swaps_sink() -> None:
    previous = get_security_log()
    custom = SecurityEventLog(max_events=10)
    try:
        configure_security_log(custom)
        assert get_security_log() is custom
        emit(SecurityEventType.OAUTH_LOGIN, actor_id="oauth-user")
        assert custom.count() == 1
    finally:
        configure_security_log(previous)
