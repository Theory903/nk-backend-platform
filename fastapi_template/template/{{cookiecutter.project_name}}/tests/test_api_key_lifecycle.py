"""Tests for production ApiKeyLifecycleService."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from {{cookiecutter.project_name}}.core.identifiers import new_id
from {{cookiecutter.project_name}}.identity.api_key_lifecycle import (
    ApiKeyInvalidError,
    ApiKeyIpRestrictedError,
    ApiKeyLifecycleService,
    ApiKeyRecord,
    ApiKeyScopeError,
)


class InMemoryApiKeyRepository:
    """In-memory ApiKeyRepository for unit tests."""

    def __init__(self) -> None:
        self._by_id: dict[str, ApiKeyRecord] = {}

    async def get_by_id(self, key_id: str) -> ApiKeyRecord | None:
        return self._by_id.get(key_id)

    async def get_by_hash(self, secret_hash: str) -> ApiKeyRecord | None:
        for record in self._by_id.values():
            if record.secret_hash == secret_hash:
                return record
        return None

    async def create(self, record: ApiKeyRecord) -> ApiKeyRecord:
        self._by_id[record.key_id] = record
        return record

    async def revoke(
        self,
        key_id: str,
        *,
        reason: str | None = None,
    ) -> bool:
        record = self._by_id.get(key_id)
        if record is None:
            return False
        self._by_id[key_id] = replace(
            record,
            revoked_at=datetime.now(UTC),
            revoked_reason=reason,
        )
        return True

    async def list_for_owner(
        self,
        owner_id: str,
        *,
        org_id: str | None = None,
        include_revoked: bool = False,
    ) -> list[ApiKeyRecord]:
        results: list[ApiKeyRecord] = []
        for record in self._by_id.values():
            if record.owner_id != owner_id:
                continue
            if org_id is not None and record.org_id != org_id:
                continue
            if not include_revoked and record.is_revoked:
                continue
            results.append(record)
        return results

    async def revoke_all_for_owner(
        self,
        owner_id: str,
        *,
        reason: str | None = None,
    ) -> int:
        count = 0
        for key_id, record in list(self._by_id.items()):
            if record.owner_id != owner_id or record.is_revoked:
                continue
            self._by_id[key_id] = replace(
                record,
                revoked_at=datetime.now(UTC),
                revoked_reason=reason,
            )
            count += 1
        return count

    async def update_last_used(
        self,
        key_id: str,
        *,
        used_at: datetime,
    ) -> None:
        record = self._by_id.get(key_id)
        if record is None:
            return
        self._by_id[key_id] = replace(record, last_used_at=used_at)


@pytest.fixture
def service() -> ApiKeyLifecycleService:
    return ApiKeyLifecycleService(InMemoryApiKeyRepository())


@pytest.mark.anyio
async def test_create_returns_plaintext_once_no_secret_on_record(
    service: ApiKeyLifecycleService,
) -> None:
    plaintext, record = await service.create(
        "prod-key",
        owner_id="usr_1",
        scopes={"read"},
    )

    assert plaintext.startswith("nk_live_key_")
    assert "_" in record.key_id
    assert record.key_id.startswith("key_")
    assert record.key_id in plaintext
    assert not hasattr(record, "secret")
    assert "secret" not in record.metadata
    assert plaintext not in (record.secret_hash, record.name)
    assert record.secret_hash == service._hash_secret(plaintext)


@pytest.mark.anyio
async def test_authenticate_success(
    service: ApiKeyLifecycleService,
) -> None:
    plaintext, created = await service.create("ok", owner_id="usr_1")
    authed = await service.authenticate(plaintext)
    assert authed.key_id == created.key_id
    stored = await service._repository.get_by_id(created.key_id)
    assert stored is not None
    assert stored.last_used_at is not None


@pytest.mark.anyio
async def test_authenticate_hmac_fail(
    service: ApiKeyLifecycleService,
) -> None:
    plaintext, _ = await service.create("ok", owner_id="usr_1")
    key_id, _secret = service._parse_key(plaintext)
    tampered = f"nk_live_{key_id}_not-the-real-secret"
    with pytest.raises(ApiKeyInvalidError):
        await service.authenticate(tampered)


@pytest.mark.anyio
async def test_authenticate_revoked(
    service: ApiKeyLifecycleService,
) -> None:
    plaintext, record = await service.create("ok", owner_id="usr_1")
    await service.revoke(record.key_id, reason="test")
    with pytest.raises(ApiKeyInvalidError):
        await service.authenticate(plaintext)


@pytest.mark.anyio
async def test_authenticate_expired(
    service: ApiKeyLifecycleService,
) -> None:
    plaintext, record = await service.create(
        "ok",
        owner_id="usr_1",
        expires_in_s=3600,
    )
    expired = replace(
        record,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    await service._repository.create(expired)
    with pytest.raises(ApiKeyInvalidError):
        await service.authenticate(plaintext)


@pytest.mark.anyio
async def test_scope_hierarchical(
    service: ApiKeyLifecycleService,
) -> None:
    plaintext, _ = await service.create(
        "scoped",
        owner_id="usr_1",
        scopes={"crm.*", "billing.read"},
    )
    await service.authenticate(plaintext, required_scope="crm.write")
    await service.authenticate(plaintext, required_scope="billing.read")
    with pytest.raises(ApiKeyScopeError):
        await service.authenticate(plaintext, required_scope="billing.write")

    star_plain, _ = await service.create(
        "star",
        owner_id="usr_1",
        scopes={"*"},
    )
    await service.authenticate(star_plain, required_scope="anything.at.all")


@pytest.mark.anyio
async def test_cidr_allowlist_allow_deny_and_empty(
    service: ApiKeyLifecycleService,
) -> None:
    restricted, _ = await service.create(
        "cidr",
        owner_id="usr_1",
        ip_allowlist=["10.0.0.0/8"],
    )
    await service.authenticate(restricted, client_ip="10.1.2.3")
    with pytest.raises(ApiKeyIpRestrictedError):
        await service.authenticate(restricted, client_ip="192.168.1.1")

    open_key, record = await service.create(
        "open",
        owner_id="usr_1",
        ip_allowlist=None,
    )
    assert record.ip_allowlist == ()
    await service.authenticate(open_key, client_ip="203.0.113.9")


@pytest.mark.anyio
async def test_rotate_revokes_old_preserves_ttl(
    service: ApiKeyLifecycleService,
) -> None:
    plaintext, old = await service.create(
        "rot",
        owner_id="usr_1",
        scopes={"read", "write"},
        expires_in_s=3600,
        ip_allowlist=["127.0.0.1/32"],
    )
    result = await service.rotate(plaintext)
    assert result is not None
    new_plain, new_rec = result

    with pytest.raises(ApiKeyInvalidError):
        await service.authenticate(plaintext)

    authed = await service.authenticate(new_plain, client_ip="127.0.0.1")
    assert authed.key_id == new_rec.key_id
    assert new_rec.rotated_from == old.key_id
    assert new_rec.metadata.get("rotated_from") == old.key_id
    assert new_rec.scopes == old.scopes
    assert new_rec.expires_at is not None
    remaining = (new_rec.expires_at - datetime.now(UTC)).total_seconds()
    assert 3500 < remaining <= 3600


@pytest.mark.anyio
async def test_revoke_all_for_owner(
    service: ApiKeyLifecycleService,
) -> None:
    p1, _ = await service.create("a", owner_id="usr_1")
    p2, _ = await service.create("b", owner_id="usr_1")
    p3, _ = await service.create("c", owner_id="usr_2")

    revoked = await service.revoke_all_for_owner("usr_1", reason="cascade")
    assert revoked == 2

    with pytest.raises(ApiKeyInvalidError):
        await service.authenticate(p1)
    with pytest.raises(ApiKeyInvalidError):
        await service.authenticate(p2)
    await service.authenticate(p3)


@pytest.mark.anyio
async def test_parse_key_roundtrip_with_real_new_id(
    service: ApiKeyLifecycleService,
) -> None:
    key_id = new_id("key")
    assert key_id.startswith("key_")
    assert key_id.count("_") == 1

    secret = "s3cretTokenValue"
    plaintext = f"nk_live_{key_id}_{secret}"
    parsed_id, parsed_secret = service._parse_key(plaintext)
    assert parsed_id == key_id
    assert parsed_secret == secret

    # Old split("_", 3) would incorrectly yield key_id == "key"
    broken = plaintext.split("_", 3)
    assert broken[2] == "key"
    assert broken[2] != key_id


@pytest.mark.anyio
async def test_can_authenticate_gate() -> None:
    repo = InMemoryApiKeyRepository()

    async def deny(_owner_id: str) -> bool:
        return False

    svc = ApiKeyLifecycleService(repo, can_authenticate=deny)
    plaintext, _ = await svc.create("gated", owner_id="usr_1")
    with pytest.raises(ApiKeyInvalidError):
        await svc.authenticate(plaintext)
