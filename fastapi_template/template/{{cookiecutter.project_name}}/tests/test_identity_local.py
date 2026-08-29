import pytest

from {{cookiecutter.project_name}}.identity.providers.local import (
    LocalIdentityProvider,
    LocalUser,
)

pytestmark = pytest.mark.anyio


def _users() -> dict[str, LocalUser]:
    return {
        "alice": LocalUser(
            user_id="alice",
            username="Alice",
            password="secret",
            roles=("admin",),
        ),
        "bob": LocalUser(
            user_id="bob",
            username="bob",
            password="hunter2",
        ),
        "carol": LocalUser(
            user_id="carol",
            username="carol",
            password="pw",
            disabled=True,
        ),
    }


async def test_password_auth_success() -> None:
    provider = LocalIdentityProvider(users=_users())
    result = await provider.authenticate({"user_id": "alice", "password": "secret"})
    assert result is not None
    assert result["user_id"] == "alice"
    assert result["provider"] == "local"
    assert result["roles"] == ["admin"]


async def test_password_auth_fail() -> None:
    provider = LocalIdentityProvider(users=_users())
    assert await provider.authenticate({"user_id": "alice", "password": "wrong"}) is None
    assert await provider.authenticate({"username": "alice", "password": "wrong"}) is None


async def test_disabled_user_rejected() -> None:
    provider = LocalIdentityProvider(users=_users())
    assert (
        await provider.authenticate({"user_id": "carol", "password": "pw"}) is None
    )
    assert await provider.get_user("carol") is None


async def test_trusted_mode_off_rejects_no_password() -> None:
    """Default must never allow user_id-only auth (no silent impersonation)."""
    provider = LocalIdentityProvider(users=_users())
    assert await provider.authenticate({"user_id": "alice"}) is None
    assert await provider.authenticate({"username": "Alice"}) is None


async def test_trusted_mode_on_works() -> None:
    provider = LocalIdentityProvider(
        users=_users(),
        allow_trusted_identity=True,
    )
    result = await provider.authenticate({"user_id": "alice"})
    assert result is not None
    assert result["user_id"] == "alice"


async def test_username_lookup_casefold() -> None:
    provider = LocalIdentityProvider(users=_users())
    result = await provider.authenticate(
        {"username": "alice", "password": "secret"},
    )
    assert result is not None
    assert result["user_id"] == "alice"
    assert result["username"] == "Alice"

    result_upper = await provider.authenticate(
        {"username": "ALICE", "password": "secret"},
    )
    assert result_upper is not None
    assert result_upper["user_id"] == "alice"


async def test_local_auth_missing_returns_none() -> None:
    provider = LocalIdentityProvider()
    assert await provider.authenticate({}) is None


async def test_get_user() -> None:
    provider = LocalIdentityProvider(users=_users())
    assert await provider.get_user("bob") is not None
    assert await provider.get_user("unknown") is None


async def test_close_is_noop() -> None:
    provider = LocalIdentityProvider(users=_users())
    assert await provider.close() is None
