"""Persistent account lifecycle state machine + async cascade tests."""

from __future__ import annotations

import pytest

from {{cookiecutter.project_name}}.identity.account_lifecycle import (
    AccountLifecycleManager,
    AccountNotFoundError,
    AccountStatus,
    InMemoryAccountRepository,
    InvalidAccountTransition,
    NoOpCascadeEffects,
    RecordingCascadeEffects,
)

pytestmark = pytest.mark.anyio


def _manager(
    *,
    status: AccountStatus = AccountStatus.ACTIVE,
    user_id: str = "u1",
    effects: RecordingCascadeEffects | NoOpCascadeEffects | None = None,
) -> tuple[AccountLifecycleManager, InMemoryAccountRepository, RecordingCascadeEffects | NoOpCascadeEffects]:
    repo = InMemoryAccountRepository()
    repo.seed(user_id, status)
    cascade = effects if effects is not None else RecordingCascadeEffects(
        sessions=2,
        refresh_tokens=3,
        api_keys=1,
        service_accounts=4,
    )
    return AccountLifecycleManager(repo, cascade), repo, cascade


async def test_active_to_suspended_cascades() -> None:
    mgr, repo, cascade = _manager()
    assert isinstance(cascade, RecordingCascadeEffects)

    result = await mgr.transition("u1", AccountStatus.SUSPENDED, org_id="org_a")

    assert await repo.get_status("u1") == AccountStatus.SUSPENDED
    assert result is not None
    assert result.sessions_revoked == 2
    assert result.refresh_tokens_revoked == 3
    assert result.api_keys_revoked == 1
    assert result.service_accounts_deactivated == 4
    assert result.as_dict() == {
        "sessions_revoked": 2,
        "refresh_tokens_revoked": 3,
        "api_keys_revoked": 1,
        "service_accounts_deactivated": 4,
    }
    assert [c[0] for c in cascade.calls] == [
        "revoke_all_sessions",
        "revoke_all_refresh_tokens",
        "revoke_all_api_keys",
        "deactivate_service_accounts",
    ]
    assert cascade.calls[-1][1] == {"org_id": "org_a", "owner_id": "u1"}
    assert await mgr.can_authenticate("u1") is False


async def test_invalid_transition_raises() -> None:
    mgr, _, _ = _manager()

    with pytest.raises(InvalidAccountTransition) as exc_info:
        await mgr.transition("u1", AccountStatus.CREATED)

    err = exc_info.value
    assert err.user_id == "u1"
    assert err.current == AccountStatus.ACTIVE
    assert err.requested == AccountStatus.CREATED
    assert "invalid account transition" in str(err)


async def test_cas_conflict_raises_invalid_transition() -> None:
    repo = InMemoryAccountRepository()
    repo.seed("u1", AccountStatus.ACTIVE)

    class ConflictRepo(InMemoryAccountRepository):
        async def set_status(
            self,
            user_id: str,
            *,
            expected_status: AccountStatus,
            new_status: AccountStatus,
        ) -> bool:
            # Simulate a concurrent writer winning the CAS race.
            self._statuses[user_id] = AccountStatus.DEACTIVATED
            return False

    conflict = ConflictRepo()
    conflict.seed("u1", AccountStatus.ACTIVE)
    mgr = AccountLifecycleManager(conflict, NoOpCascadeEffects())

    with pytest.raises(InvalidAccountTransition) as exc_info:
        await mgr.transition("u1", AccountStatus.SUSPENDED)

    assert exc_info.value.current == AccountStatus.DEACTIVATED
    assert await conflict.get_status("u1") == AccountStatus.DEACTIVATED


async def test_can_authenticate_only_active() -> None:
    repo = InMemoryAccountRepository()
    effects = NoOpCascadeEffects()
    mgr = AccountLifecycleManager(repo, effects)

    for status, expected in (
        (AccountStatus.CREATED, False),
        (AccountStatus.INVITED, False),
        (AccountStatus.PENDING_VERIFICATION, False),
        (AccountStatus.ACTIVE, True),
        (AccountStatus.SUSPENDED, False),
        (AccountStatus.DEACTIVATED, False),
        (AccountStatus.DELETED, False),
    ):
        repo.seed("u1", status)
        assert await mgr.can_authenticate("u1") is expected


async def test_account_not_found() -> None:
    mgr = AccountLifecycleManager(
        InMemoryAccountRepository(),
        NoOpCascadeEffects(),
    )

    with pytest.raises(AccountNotFoundError, match="missing"):
        await mgr.get_status("missing")

    with pytest.raises(AccountNotFoundError):
        await mgr.can_authenticate("missing")

    with pytest.raises(AccountNotFoundError):
        await mgr.transition("missing", AccountStatus.ACTIVE)


async def test_deactivated_cascades_and_deleted_is_terminal() -> None:
    mgr, repo, cascade = _manager()
    assert isinstance(cascade, RecordingCascadeEffects)

    result = await mgr.transition("u1", AccountStatus.DEACTIVATED)
    assert await repo.get_status("u1") == AccountStatus.DEACTIVATED
    assert result is not None
    assert result.sessions_revoked == 2
    assert len(cascade.calls) == 4

    cascade.calls.clear()
    none_result = await mgr.transition("u1", AccountStatus.DELETED)
    assert none_result is None
    assert cascade.calls == []
    assert await repo.get_status("u1") == AccountStatus.DELETED

    with pytest.raises(InvalidAccountTransition):
        await mgr.transition("u1", AccountStatus.ACTIVE)

    with pytest.raises(InvalidAccountTransition):
        await mgr.transition("u1", AccountStatus.DELETED)


async def test_non_revoke_transition_returns_none() -> None:
    mgr, repo, cascade = _manager(status=AccountStatus.CREATED)
    assert isinstance(cascade, RecordingCascadeEffects)

    result = await mgr.transition("u1", AccountStatus.ACTIVE)
    assert result is None
    assert cascade.calls == []
    assert await repo.get_status("u1") == AccountStatus.ACTIVE
    assert await mgr.can_authenticate("u1") is True
