"""Account linking identity-graph security rules."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from {{cookiecutter.project_name}}.identity.account_linking import (
    AccountLinkingConflictError,
    AccountLinkingService,
    AccountNotFoundError,
    CannotUnlinkLastIdentityError,
    IdentityAlreadyLinkedError,
    IdentityUniqueConstraintError,
    InMemoryIdentityRepository,
    LinkedAccount,
    UserIdentity,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def repo() -> InMemoryIdentityRepository:
    return InMemoryIdentityRepository()


@pytest.fixture
def svc(repo: InMemoryIdentityRepository) -> AccountLinkingService:
    return AccountLinkingService(repo)


async def test_email_normalize_casefold(svc: AccountLinkingService) -> None:
    account = await svc.create_account(
        "  User@Example.COM ",
        provider="password",
        provider_user_id="pw_1",
    )
    assert account.email == "user@example.com"

    matches = await svc.resolve_by_email("USER@example.com")
    assert len(matches) == 1
    assert matches[0].user_id == account.user_id


async def test_find_or_create_creates_when_no_match(
    svc: AccountLinkingService,
) -> None:
    account, created = await svc.find_or_create(
        "new@example.com",
        provider="google",
        provider_user_id="g_1",
        provider_email_verified=True,
    )
    assert created is True
    assert account.email == "new@example.com"
    assert len(account.identities) == 1
    assert account.identities[0].provider == "google"


async def test_find_or_create_resolves_existing_identity(
    svc: AccountLinkingService,
) -> None:
    first, created = await svc.find_or_create(
        "a@example.com",
        provider="google",
        provider_user_id="g_99",
    )
    assert created is True

    again, created2 = await svc.find_or_create(
        "a@example.com",
        provider="google",
        provider_user_id="g_99",
    )
    assert created2 is False
    assert again.user_id == first.user_id


async def test_find_or_create_never_silently_merges_by_email(
    svc: AccountLinkingService,
) -> None:
    """Email match alone must not auto-link a new provider identity."""
    await svc.create_account(
        "user@example.com",
        provider="password",
        provider_user_id="pw_user",
    )

    with pytest.raises(AccountLinkingConflictError):
        await svc.find_or_create(
            "user@example.com",
            provider="google",
            provider_user_id="g_123",
            provider_email_verified=True,
        )


async def test_find_or_create_conflict_casefold_email(
    svc: AccountLinkingService,
) -> None:
    await svc.create_account(
        "User@Example.com",
        provider="password",
        provider_user_id="pw_x",
    )

    with pytest.raises(AccountLinkingConflictError):
        await svc.find_or_create(
            "user@example.com",
            provider="microsoft",
            provider_user_id="ms_1",
        )


async def test_identity_uniqueness_blocks_takeover(
    svc: AccountLinkingService,
) -> None:
    owner = await svc.create_account(
        "a@x.com",
        provider="github",
        provider_user_id="gh_1",
    )
    other = await svc.create_account(
        "b@x.com",
        provider="password",
        provider_user_id="pw_other",
    )

    with pytest.raises(IdentityAlreadyLinkedError):
        await svc.link(
            other.user_id,
            provider="github",
            provider_user_id="gh_1",
        )

    # Owner still owns the identity
    resolved = await svc.resolve("github", "gh_1")
    assert resolved is not None
    assert resolved.user_id == owner.user_id


async def test_link_idempotent_when_already_linked_same_account(
    svc: AccountLinkingService,
) -> None:
    account = await svc.create_account(
        "solo@x.com",
        provider="password",
        provider_user_id="p1",
    )
    linked = await svc.link(
        account.user_id,
        provider="google",
        provider_user_id="g_same",
    )
    again = await svc.link(
        account.user_id,
        provider="google",
        provider_user_id="g_same",
    )
    assert again.user_id == linked.user_id
    google_ids = [
        i for i in again.identities if i.provider == "google"
    ]
    assert len(google_ids) == 1


async def test_cannot_unlink_last_identity(
    svc: AccountLinkingService,
) -> None:
    account = await svc.create_account(
        "solo@x.com",
        provider="password",
        provider_user_id="p1",
    )
    with pytest.raises(CannotUnlinkLastIdentityError):
        await svc.unlink(
            account.user_id,
            provider="password",
            provider_user_id="p1",
        )


async def test_unlink_succeeds_when_multiple_identities(
    svc: AccountLinkingService,
) -> None:
    account = await svc.create_account(
        "multi@x.com",
        provider="password",
        provider_user_id="p1",
    )
    await svc.link(
        account.user_id,
        provider="google",
        provider_user_id="g_2",
    )
    ok = await svc.unlink(
        account.user_id,
        provider="google",
        provider_user_id="g_2",
    )
    assert ok is True
    remaining = await svc.resolve("password", "p1")
    assert remaining is not None
    assert len(remaining.identities) == 1


async def test_resolve_never_uses_email(
    svc: AccountLinkingService,
) -> None:
    account = await svc.create_account(
        "resolve@x.com",
        provider="password",
        provider_user_id="pw_r",
    )
    # Exact identity resolves
    found = await svc.resolve("password", "pw_r")
    assert found is not None
    assert found.user_id == account.user_id

    # Email string is not an identity key — resolve ignores email
    by_email_as_id = await svc.resolve("password", "resolve@x.com")
    assert by_email_as_id is None

    # Empty provider / provider_user_id short-circuits without email lookup
    assert await svc.resolve("", "pw_r") is None
    assert await svc.resolve("password", "") is None


async def test_link_unknown_account_raises(
    svc: AccountLinkingService,
) -> None:
    with pytest.raises(AccountNotFoundError):
        await svc.link(
            "usr_missing",
            provider="google",
            provider_user_id="g_x",
        )


async def test_concurrent_unique_constraint_maps_to_conflict(
    repo: InMemoryIdentityRepository,
) -> None:
    """Simulate a lost race on UNIQUE(provider, provider_user_id)."""
    svc = AccountLinkingService(repo)
    account = await svc.create_account(
        "race@x.com",
        provider="password",
        provider_user_id="pw_race",
    )

    failing_repo = AsyncMock()
    failing_repo.get_account = AsyncMock(return_value=account)
    failing_repo.find_by_identity = AsyncMock(return_value=None)
    failing_repo.add_identity = AsyncMock(
        side_effect=IdentityUniqueConstraintError("unique"),
    )

    racing = AccountLinkingService(failing_repo)
    with pytest.raises(AccountLinkingConflictError):
        await racing.link(
            account.user_id,
            provider="google",
            provider_user_id="g_race",
        )


async def test_inmemory_enforces_unique_provider_user_id(
    repo: InMemoryIdentityRepository,
) -> None:
    first = LinkedAccount(
        user_id="usr_a",
        email="a@x.com",
        identities=(
            UserIdentity(provider="google", provider_user_id="same"),
        ),
    )
    await repo.create_account(first)

    second = LinkedAccount(
        user_id="usr_b",
        email="b@x.com",
        identities=(
            UserIdentity(provider="google", provider_user_id="same"),
        ),
    )
    with pytest.raises(IdentityUniqueConstraintError):
        await repo.create_account(second)
