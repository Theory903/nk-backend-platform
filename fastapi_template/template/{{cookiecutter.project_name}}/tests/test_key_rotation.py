"""Tests for production KeyRotationManager (introduce → dual-accept → retire)."""

from __future__ import annotations

import time

import pytest

from {{cookiecutter.project_name}}.identity.key_rotation import (
    KeyRotationManager,
    SigningKey,
)


def test_introduce_sign_verify() -> None:
    km = KeyRotationManager()
    kid, _ = km.introduce_key()
    msg = b"hello-rotation"
    signed_kid, sig = km.sign(msg)
    assert signed_kid == kid
    assert km.verify_signature(msg, sig) == kid
    assert km.current_key_id() == kid


def test_second_introduce_dual_accept_during_grace() -> None:
    km = KeyRotationManager(grace_period_s=3600.0)
    kid1, _ = km.introduce_key()
    msg = b"dual-accept"
    _, sig1 = km.sign(msg)

    kid2, _ = km.introduce_key()
    assert kid1 != kid2
    assert km.current_key_id() == kid2

    # Old signature still verifies (grace / dual-accept).
    assert km.verify_signature(msg, sig1) == kid1

    # New signatures use K2; both keys active.
    kid_new, sig2 = km.sign(msg)
    assert kid_new == kid2
    assert km.verify_signature(msg, sig2) == kid2
    assert set(km.active_key_ids()) == {kid1, kid2}


def test_force_retire_rejects_old_key() -> None:
    km = KeyRotationManager(grace_period_s=3600.0)
    kid1, _ = km.introduce_key()
    msg = b"force-retire"
    _, sig1 = km.sign(msg)
    kid2, _ = km.introduce_key()

    assert km.verify_signature(msg, sig1) == kid1
    assert km.force_retire(kid1) is True
    assert km.verify_signature(msg, sig1) is None
    assert set(km.active_key_ids()) == {kid2}


def test_retire_expired_removes_old_key() -> None:
    km = KeyRotationManager(grace_period_s=0.01)
    kid1, _ = km.introduce_key()
    msg = b"expire"
    _, sig1 = km.sign(msg)
    kid2, _ = km.introduce_key()

    time.sleep(0.03)
    removed = km.retire_expired()
    assert removed == 1
    assert km.verify_signature(msg, sig1) is None
    assert km.key_count() == 1
    assert km.current_key_id() == kid2
    assert set(km.active_key_ids()) == {kid2}


def test_cannot_force_retire_current_signing_key() -> None:
    km = KeyRotationManager()
    kid1, _ = km.introduce_key()
    with pytest.raises(ValueError, match="cannot retire the current signing key"):
        km.force_retire(kid1)
    assert km.current_key_id() == kid1
    assert kid1 in km.active_key_ids()


def test_unsupported_algorithm_rejected() -> None:
    km = KeyRotationManager()
    with pytest.raises(ValueError, match="unsupported signing algorithm"):
        km.introduce_key(algorithm="RS256")

    kid, _ = km.introduce_key()
    msg = b"algo"
    _, sig = km.sign(msg)
    assert km.verify_signature(msg, sig, algorithm="RS256") is None
    assert km.verify_signature(msg, sig, algorithm="HS256") == kid


def test_short_secret_rejected() -> None:
    km = KeyRotationManager()
    with pytest.raises(ValueError, match="at least 32 bytes"):
        km.introduce_key(secret=b"too-short")


def test_verify_wrong_signature_returns_none() -> None:
    km = KeyRotationManager()
    km.introduce_key()
    msg = b"payload"
    _, sig = km.sign(msg)
    # Corrupt one hex nibble.
    bad = ("0" if sig[0] != "0" else "1") + sig[1:]
    assert km.verify_signature(msg, bad) is None
    assert km.verify_signature(b"other", sig) is None


def test_verify_with_explicit_key_id() -> None:
    km = KeyRotationManager(grace_period_s=3600.0)
    kid1, _ = km.introduce_key()
    msg = b"explicit-kid"
    _, sig1 = km.sign(msg)
    kid2, _ = km.introduce_key()
    _, sig2 = km.sign(msg)

    assert km.verify_signature(msg, sig1, key_id=kid1) == kid1
    assert km.verify_signature(msg, sig2, key_id=kid2) == kid2
    # Wrong key_id for a valid signature → None
    assert km.verify_signature(msg, sig1, key_id=kid2) is None
    assert km.verify_signature(msg, sig2, key_id=kid1) is None
    assert km.verify_signature(msg, sig1, key_id="missing") is None


def test_signing_key_is_valid_respects_retired_at() -> None:
    past = time.time() - 10
    key = SigningKey(
        key_id="k_old",
        secret=b"x" * 32,
        retired_at=past,
    )
    assert key.is_valid is False

    future = time.time() + 3600
    key2 = SigningKey(
        key_id="k_ok",
        secret=b"y" * 32,
        retired_at=future,
    )
    assert key2.is_valid is True
