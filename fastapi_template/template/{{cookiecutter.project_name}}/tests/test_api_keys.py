"""Tests for the sync ApiKeyStore primitive (identity.api_keys)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from {{cookiecutter.project_name}}.identity.api_keys import ApiKeyStore


def test_create_verify_success() -> None:
    store = ApiKeyStore()
    raw, record = store.create(
        "ci-bot",
        owner_id="owner_1",
        scopes={"read", "users.read"},
    )

    assert raw.startswith("nk_")
    parts = raw.split("_", 2)
    assert len(parts) == 3
    prefix, key_id, secret = parts
    assert prefix == "nk"
    assert key_id == record.key_id
    assert secret
    assert record.digest
    assert len(record.digest) == 64
    assert record.digest != raw
    assert raw not in (record.metadata or {})

    verified = store.verify(raw)
    assert verified is not None
    assert verified.key_id == record.key_id
    assert verified.name == "ci-bot"
    assert verified.last_used_at is not None


def test_parse_format_prefix_keyid_secret() -> None:
    store = ApiKeyStore()
    raw, record = store.create("fmt", prefix="nk")
    prefix, key_id, secret = raw.split("_", 2)
    assert prefix == "nk"
    assert key_id == record.key_id
    assert secret
    assert store._parse(raw) == (key_id, secret)
    assert store._parse("not-a-key") is None
    assert store._parse("nk_onlytwo") is None
    assert store._parse("nk__secret") is None


def test_bad_key_revoked_expired_return_none() -> None:
    store = ApiKeyStore()
    raw, record = store.create("temp", owner_id="o1")

    assert store.verify("nk_deadbeef_wrongsecret") is None
    assert store.verify("") is None
    assert store.verify("malformed") is None

    assert store.revoke(raw) is True
    assert store.verify(raw) is None
    assert store.get(record.key_id) is not None
    assert store.get(record.key_id).is_revoked is True  # type: ignore[union-attr]

    raw2, rec2 = store.create(
        "expires",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    assert rec2.is_expired is True
    assert store.verify(raw2) is None


def test_constant_time_path_wrong_secret_same_key_id() -> None:
    store = ApiKeyStore()
    raw, record = store.create("ct")
    _prefix, key_id, _secret = raw.split("_", 2)
    forged = f"nk_{key_id}_totally-wrong-secret-value"

    with patch.object(
        ApiKeyStore,
        "_constant_time_equal",
        wraps=ApiKeyStore._constant_time_equal,
    ) as compare:
        assert store.verify(forged) is None
        compare.assert_called_once()
        supplied, expected = compare.call_args[0]
        assert expected == record.digest
        assert supplied != expected

    assert store.verify(raw) is not None


def test_revoke_all_for_owner() -> None:
    store = ApiKeyStore()
    raw_a, _ = store.create("a", owner_id="alice")
    raw_b, _ = store.create("b", owner_id="alice")
    raw_c, _ = store.create("c", owner_id="bob")

    revoked = store.revoke_all_for_owner("alice")
    assert revoked == 2
    assert store.verify(raw_a) is None
    assert store.verify(raw_b) is None
    assert store.verify(raw_c) is not None
    assert store.revoke_all_for_owner("alice") == 0


def test_hierarchical_scopes_via_has_scope() -> None:
    store = ApiKeyStore()
    raw, record = store.create(
        "scoped",
        scopes={"users.*", "billing.read"},
    )

    assert record.has_scope("users.read") is True
    assert record.has_scope("users.write") is True
    assert record.has_scope("billing.read") is True
    assert record.has_scope("billing.write") is False
    assert record.has_scope("admin") is False

    assert store.has_scope(raw, "users.delete") is True
    assert store.has_scope(raw, "billing.write") is False

    star_raw, star_rec = store.create("admin", scopes={"*"})
    assert star_rec.has_scope("anything.nested") is True
    assert store.has_scope(star_raw, "x") is True
