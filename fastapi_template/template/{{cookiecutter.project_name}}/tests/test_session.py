"""Tests for the canonical SessionStore (absolute/idle, rotate, limits)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from {{cookiecutter.project_name}}.identity.session import (
    SessionRevocationReason,
    SessionStatus,
    SessionStore,
)
from {{cookiecutter.project_name}}.identity.session_lifecycle import SecureSessionStore


def test_create_returns_opaque_id_get_returns_dict() -> None:
    store = SessionStore(default_ttl_s=300)
    sid = store.create("user_1", {"role": "admin"}, device_id="dev-1")
    assert isinstance(sid, str)
    assert len(sid) >= 32

    got = store.get(sid)
    assert got is not None
    assert got["principal_id"] == "user_1"
    assert got["data"]["role"] == "admin"
    assert got["device_id"] == "dev-1"
    assert got["status"] == SessionStatus.ACTIVE.value

    session = store.get_session(sid)
    assert session is not None
    assert session.session_id == sid
    assert session.principal_id == "user_1"


def test_rotate_preserves_expires_at_and_keeps_old_as_rotated() -> None:
    store = SessionStore(default_ttl_s=3600, idle_timeout_s=600)
    old_id = store.create("user_1", device_id="phone")
    old = store.get_session(old_id)
    assert old is not None
    absolute = old.expires_at

    new_id = store.rotate(old_id)
    assert new_id is not None
    assert new_id != old_id

    new = store.get_session(new_id)
    assert new is not None
    assert new.expires_at == absolute
    assert new.device_id == "phone"
    assert new.rotated_from == old_id

    assert store.get(old_id) is None
    stored_old = store._sessions[old_id]
    assert stored_old.status is SessionStatus.ROTATED
    assert stored_old.revoked_reason is SessionRevocationReason.ROTATED
    assert stored_old.rotated_to == new_id
    assert old_id in store._sessions  # not deleted


def test_absolute_expiry() -> None:
    store = SessionStore(default_ttl_s=10, idle_timeout_s=30)
    sid = store.create("user_1")
    session = store.get_session(sid)
    assert session is not None

    with patch(
        "{{cookiecutter.project_name}}.identity.session.time.time",
        return_value=session.expires_at + 0.1,
    ):
        assert store.get(sid) is None

    assert store._sessions[sid].status is SessionStatus.EXPIRED


def test_idle_expiry() -> None:
    store = SessionStore(default_ttl_s=3600, idle_timeout_s=10)
    sid = store.create("user_t")
    session = store.get_session(sid, touch=False)
    assert session is not None

    with patch(
        "{{cookiecutter.project_name}}.identity.session.time.time",
        return_value=session.idle_expires_at + 0.1,
    ):
        assert store.get(sid) is None

    assert store._sessions[sid].status is SessionStatus.EXPIRED


def test_touch_extends_idle_not_absolute() -> None:
    store = SessionStore(default_ttl_s=100, idle_timeout_s=20)
    sid = store.create("user_1")
    session = store.get_session(sid, touch=False)
    assert session is not None
    absolute = session.expires_at
    idle_before = session.idle_expires_at

    with patch(
        "{{cookiecutter.project_name}}.identity.session.time.time",
        return_value=session.created_at + 5,
    ):
        got = store.get_session(sid, touch=True)

    assert got is not None
    assert got.expires_at == absolute
    assert got.idle_expires_at > idle_before
    assert got.idle_expires_at <= absolute


def test_touch_idle_capped_by_absolute_expires_at() -> None:
    store = SessionStore(default_ttl_s=30, idle_timeout_s=100)
    sid = store.create("user_1")
    session = store.get_session(sid, touch=False)
    assert session is not None
    absolute = session.expires_at

    with patch(
        "{{cookiecutter.project_name}}.identity.session.time.time",
        return_value=session.created_at + 10,
    ):
        got = store.get_session(sid, touch=True)

    assert got is not None
    assert got.expires_at == absolute
    assert got.idle_expires_at == absolute


def test_concurrent_limit_evicts_oldest() -> None:
    store = SessionStore(max_concurrent_sessions=3)
    created = [store.create("user_z") for _ in range(5)]

    active_ids = {
        sid for sid in created if store.get(sid, touch=False) is not None
    }
    assert len(active_ids) == 3
    assert store.get(created[0], touch=False) is None
    assert store.get(created[1], touch=False) is None
    assert store._sessions[created[0]].revoked_reason is (
        SessionRevocationReason.CONCURRENT_LIMIT
    )


def test_revoke_all_for_principal() -> None:
    store = SessionStore(max_concurrent_sessions=10)
    a1 = store.create("alice")
    a2 = store.create("alice")
    b1 = store.create("bob")

    count = store.revoke_all_for_principal("alice", except_session=a2)
    assert count == 1
    assert store.get(a1) is None
    assert store.get(a2) is not None
    assert store.get(b1) is not None

    count_all = store.revoke_all_for_principal("alice")
    assert count_all == 1
    assert store.get(a2) is None


def test_update_and_delete_data() -> None:
    store = SessionStore()
    sid = store.create("user_1", {"a": 1, "b": 2})
    assert store.update_data(sid, {"b": 3, "c": 4}) is True
    got = store.get(sid)
    assert got is not None
    assert got["data"] == {"a": 1, "b": 3, "c": 4}

    assert store.delete_data(sid, "a", "missing") is True
    got = store.get(sid)
    assert got is not None
    assert got["data"] == {"b": 3, "c": 4}


def test_cleanup_expired() -> None:
    store = SessionStore(default_ttl_s=10, idle_timeout_s=5)
    live = store.create("live")
    dead = store.create("dead")
    store.revoke(dead)

    session = store.get_session(live, touch=False)
    assert session is not None

    with patch(
        "{{cookiecutter.project_name}}.identity.session.time.time",
        return_value=session.expires_at + 1,
    ):
        removed = store.cleanup_expired()

    assert removed >= 2
    assert live not in store._sessions
    assert dead not in store._sessions


def test_invalid_config_raises() -> None:
    with pytest.raises(ValueError, match="default_ttl_s"):
        SessionStore(default_ttl_s=0)
    with pytest.raises(ValueError, match="max_lifetime_s"):
        SessionStore(max_lifetime_s=0)
    with pytest.raises(ValueError, match="idle_timeout_s"):
        SessionStore(idle_timeout_s=0)
    with pytest.raises(ValueError, match="max_concurrent"):
        SessionStore(max_concurrent_sessions=0)


def test_secure_session_store_is_alias() -> None:
    assert SecureSessionStore is SessionStore
    store = SecureSessionStore(max_lifetime_s=100, idle_timeout_s=20)
    sid = store.create("user_1")
    assert store.get(sid)["principal_id"] == "user_1"


def test_expired_cannot_rotate() -> None:
    store = SessionStore(default_ttl_s=10, idle_timeout_s=5)
    sid = store.create("user_1")
    session = store.get_session(sid, touch=False)
    assert session is not None

    with patch(
        "{{cookiecutter.project_name}}.identity.session.time.time",
        return_value=session.expires_at + 1,
    ):
        assert store.rotate(sid) is None

    assert store.get(sid, touch=False) is None
    assert store._sessions[sid].status is SessionStatus.EXPIRED
