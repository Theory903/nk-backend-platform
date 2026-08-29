"""RefreshTokenManager — family rotation + reuse detection."""

from __future__ import annotations

import time

import pytest

from {{cookiecutter.project_name}}.identity.refresh_tokens import (
    RefreshTokenManager,
)


def test_issue_validate_rotate_old_fails() -> None:
    mgr = RefreshTokenManager(ttl_s=3600)
    rt1 = mgr.issue("user_1")
    claims = mgr.validate(rt1)
    assert claims is not None
    assert claims["user_id"] == "user_1"
    assert claims["family_id"]

    # validate is non-consuming — still active
    assert mgr.validate(rt1) is not None

    result = mgr.rotate(rt1)
    assert result is not None
    rt2, meta = result
    assert meta["user_id"] == "user_1"
    assert meta["family_id"] == claims["family_id"]
    assert rt2 != rt1

    assert mgr.validate(rt1) is None
    assert mgr.validate(rt2) is not None


def test_rotate_reused_token_revokes_family() -> None:
    mgr = RefreshTokenManager(ttl_s=3600)
    rt1 = mgr.issue("user_1")
    result = mgr.rotate(rt1)
    assert result is not None
    rt2, meta = result
    family_id = meta["family_id"]

    # Reuse of consumed rt1 → family revoked
    assert mgr.rotate(rt1) is None
    assert family_id in mgr._families_revoked  # noqa: SLF001

    # Sibling current token also dead
    assert mgr.validate(rt2) is None
    assert mgr.rotate(rt2) is None


def test_expired_token_fails() -> None:
    mgr = RefreshTokenManager(ttl_s=1)
    rt = mgr.issue("user_exp")
    # Force expiry
    record = mgr._tokens[mgr._hash(rt)]  # noqa: SLF001
    record.expires_at = time.time() - 1

    assert mgr.validate(rt) is None
    assert mgr.rotate(rt) is None


def test_revoke_all_for_user() -> None:
    mgr = RefreshTokenManager(ttl_s=3600)
    r1 = mgr.issue("user_x")
    r2 = mgr.issue("user_x")
    other = mgr.issue("other")

    count = mgr.revoke_all_for_user("user_x")
    assert count == 2
    assert mgr.validate(r1) is None
    assert mgr.validate(r2) is None
    assert mgr.validate(other) is not None


def test_purge_expired() -> None:
    mgr = RefreshTokenManager(ttl_s=3600)
    live = mgr.issue("u1")
    dead = mgr.issue("u2")
    record = mgr._tokens[mgr._hash(dead)]  # noqa: SLF001
    record.expires_at = time.time() - 1

    purged = mgr.purge_expired()
    assert purged == 1
    assert mgr.validate(live) is not None
    assert mgr.validate(dead) is None


def test_ttl_s_must_be_positive() -> None:
    with pytest.raises(ValueError, match="ttl_s"):
        RefreshTokenManager(ttl_s=0)
    with pytest.raises(ValueError, match="ttl_s"):
        RefreshTokenManager(ttl_s=-1)


def test_revoke_single_then_reuse_revokes_family() -> None:
    mgr = RefreshTokenManager(ttl_s=3600)
    rt1 = mgr.issue("user_1")
    result = mgr.rotate(rt1)
    assert result is not None
    rt2, _ = result

    assert mgr.revoke(rt2) is True
    # Presenting revoked current token → family revoke
    assert mgr.rotate(rt2) is None
    assert mgr.validate(rt1) is None
