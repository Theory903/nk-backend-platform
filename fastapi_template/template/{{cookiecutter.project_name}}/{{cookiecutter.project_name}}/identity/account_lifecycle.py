"""
Account lifecycle and enforcement.

Account status is persistent application state.

Suspension/deactivation triggers security cascades:

    - revoke active sessions
    - revoke refresh-token families
    - revoke API keys
    - deactivate owned service accounts

The lifecycle manager itself does not know how those systems store data.
It depends on explicit async protocols.

Production deployments should persist account status in the primary
database. Redis may be used for fast revocation/version checks, but
must not become the sole source of account lifecycle truth.

Next: outbox-driven ``account.security_revoked`` cascade + SQL
``AccountRepository`` adapter + auth middleware ``can_authenticate``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

__all__ = [
    "AUTH_ALLOWED_STATUSES",
    "VALID_TRANSITIONS",
    "AccountNotFoundError",
    "AccountRepository",
    "AccountStatus",
    "AccountLifecycleManager",
    "CascadeEffects",
    "CascadeResult",
    "InMemoryAccountRepository",
    "InvalidAccountTransition",
    "NoOpCascadeEffects",
    "RecordingCascadeEffects",
]


class AccountStatus(StrEnum):
    CREATED = "created"
    INVITED = "invited"
    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"
    DELETED = "deleted"


# Only these statuses may authenticate.
AUTH_ALLOWED_STATUSES = frozenset(
    {
        AccountStatus.ACTIVE,
    },
)


# Explicit state machine.
VALID_TRANSITIONS: dict[
    AccountStatus,
    frozenset[AccountStatus],
] = {
    AccountStatus.CREATED: frozenset(
        {
            AccountStatus.INVITED,
            AccountStatus.PENDING_VERIFICATION,
            AccountStatus.ACTIVE,
        },
    ),
    AccountStatus.INVITED: frozenset(
        {
            AccountStatus.PENDING_VERIFICATION,
            AccountStatus.ACTIVE,
        },
    ),
    AccountStatus.PENDING_VERIFICATION: frozenset(
        {
            AccountStatus.ACTIVE,
        },
    ),
    AccountStatus.ACTIVE: frozenset(
        {
            AccountStatus.SUSPENDED,
            AccountStatus.DEACTIVATED,
        },
    ),
    AccountStatus.SUSPENDED: frozenset(
        {
            AccountStatus.ACTIVE,
            AccountStatus.DEACTIVATED,
        },
    ),
    AccountStatus.DEACTIVATED: frozenset(
        {
            AccountStatus.DELETED,
        },
    ),
    AccountStatus.DELETED: frozenset(),
}


class AccountNotFoundError(LookupError):
    """Account does not exist."""


class InvalidAccountTransition(ValueError):
    """Requested account status transition is invalid."""

    def __init__(
        self,
        user_id: str,
        current: AccountStatus,
        requested: AccountStatus,
    ) -> None:
        allowed = VALID_TRANSITIONS.get(current, frozenset())

        allowed_values = ", ".join(
            status.value
            for status in allowed
        ) or "none"

        super().__init__(
            f"invalid account transition for '{user_id}': "
            f"{current.value} -> {requested.value}; "
            f"allowed: {allowed_values}",
        )

        self.user_id = user_id
        self.current = current
        self.requested = requested


class AccountRepository(Protocol):
    """
    Persistence boundary for account lifecycle state.

    Implement this using your existing Repository/UoW layer.
    """

    async def get_status(
        self,
        user_id: str,
    ) -> AccountStatus | None:
        ...

    async def set_status(
        self,
        user_id: str,
        *,
        expected_status: AccountStatus,
        new_status: AccountStatus,
    ) -> bool:
        """
        Atomic compare-and-set.

        Returns False when another worker changed the account first.
        """
        ...


class CascadeEffects(Protocol):
    """
    Security side effects triggered by lifecycle changes.

    All operations are async because they may hit Redis/SQL/etc.
    """

    async def revoke_all_sessions(
        self,
        user_id: str,
    ) -> int:
        ...

    async def revoke_all_refresh_tokens(
        self,
        user_id: str,
    ) -> int:
        ...

    async def revoke_all_api_keys(
        self,
        owner_id: str,
    ) -> int:
        ...

    async def deactivate_service_accounts(
        self,
        *,
        org_id: str | None,
        owner_id: str,
    ) -> int:
        ...


class CascadeResult:
    """Results produced by a lifecycle security cascade."""

    __slots__ = (
        "sessions_revoked",
        "refresh_tokens_revoked",
        "api_keys_revoked",
        "service_accounts_deactivated",
    )

    def __init__(
        self,
        *,
        sessions_revoked: int = 0,
        refresh_tokens_revoked: int = 0,
        api_keys_revoked: int = 0,
        service_accounts_deactivated: int = 0,
    ) -> None:
        self.sessions_revoked = sessions_revoked
        self.refresh_tokens_revoked = refresh_tokens_revoked
        self.api_keys_revoked = api_keys_revoked
        self.service_accounts_deactivated = (
            service_accounts_deactivated
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "sessions_revoked": self.sessions_revoked,
            "refresh_tokens_revoked": (
                self.refresh_tokens_revoked
            ),
            "api_keys_revoked": self.api_keys_revoked,
            "service_accounts_deactivated": (
                self.service_accounts_deactivated
            ),
        }


class InMemoryAccountRepository:
    """
    Single-process account status store for tests only.

    Not safe across workers or processes. Production must use a
    durable ``AccountRepository`` (e.g. SQL CAS on a status column).
    """

    def __init__(self) -> None:
        self._statuses: dict[str, AccountStatus] = {}

    def seed(
        self,
        user_id: str,
        status: AccountStatus = AccountStatus.CREATED,
    ) -> None:
        self._statuses[user_id] = status

    async def get_status(
        self,
        user_id: str,
    ) -> AccountStatus | None:
        return self._statuses.get(user_id)

    async def set_status(
        self,
        user_id: str,
        *,
        expected_status: AccountStatus,
        new_status: AccountStatus,
    ) -> bool:
        current = self._statuses.get(user_id)
        if current is None or current != expected_status:
            return False
        self._statuses[user_id] = new_status
        return True


class NoOpCascadeEffects:
    """CascadeEffects that records nothing and revokes zero."""

    async def revoke_all_sessions(self, user_id: str) -> int:
        return 0

    async def revoke_all_refresh_tokens(self, user_id: str) -> int:
        return 0

    async def revoke_all_api_keys(self, owner_id: str) -> int:
        return 0

    async def deactivate_service_accounts(
        self,
        *,
        org_id: str | None,
        owner_id: str,
    ) -> int:
        return 0


class RecordingCascadeEffects:
    """
    Test CascadeEffects that returns configurable counts and
    records each call.
    """

    def __init__(
        self,
        *,
        sessions: int = 1,
        refresh_tokens: int = 1,
        api_keys: int = 1,
        service_accounts: int = 1,
    ) -> None:
        self.sessions = sessions
        self.refresh_tokens = refresh_tokens
        self.api_keys = api_keys
        self.service_accounts = service_accounts
        self.calls: list[tuple[str, object]] = []

    async def revoke_all_sessions(self, user_id: str) -> int:
        self.calls.append(("revoke_all_sessions", user_id))
        return self.sessions

    async def revoke_all_refresh_tokens(self, user_id: str) -> int:
        self.calls.append(("revoke_all_refresh_tokens", user_id))
        return self.refresh_tokens

    async def revoke_all_api_keys(self, owner_id: str) -> int:
        self.calls.append(("revoke_all_api_keys", owner_id))
        return self.api_keys

    async def deactivate_service_accounts(
        self,
        *,
        org_id: str | None,
        owner_id: str,
    ) -> int:
        self.calls.append(
            (
                "deactivate_service_accounts",
                {"org_id": org_id, "owner_id": owner_id},
            ),
        )
        return self.service_accounts


class AccountLifecycleManager:
    """
    Persistent account state machine.

    Important:

    - status changes use compare-and-set
    - concurrent transitions cannot silently overwrite each other
    - authentication is based on persistent status
    - security cascades execute asynchronously
    - this manager never holds an in-memory status dict as truth
    """

    def __init__(
        self,
        repository: AccountRepository,
        effects: CascadeEffects,
    ) -> None:
        self._repository = repository
        self._effects = effects

    async def get_status(
        self,
        user_id: str,
    ) -> AccountStatus:
        status = await self._repository.get_status(
            user_id,
        )

        if status is None:
            raise AccountNotFoundError(
                f"account '{user_id}' not found",
            )

        return status

    async def can_authenticate(
        self,
        user_id: str,
    ) -> bool:
        status = await self.get_status(user_id)

        return status in AUTH_ALLOWED_STATUSES

    async def transition(
        self,
        user_id: str,
        new_status: AccountStatus,
        *,
        org_id: str | None = None,
    ) -> CascadeResult | None:
        current = await self.get_status(user_id)

        allowed = VALID_TRANSITIONS.get(
            current,
            frozenset(),
        )

        if new_status not in allowed:
            raise InvalidAccountTransition(
                user_id,
                current,
                new_status,
            )

        changed = await self._repository.set_status(
            user_id,
            expected_status=current,
            new_status=new_status,
        )

        if not changed:
            # Another worker changed the account between
            # get_status() and set_status().
            latest = await self.get_status(user_id)

            raise InvalidAccountTransition(
                user_id,
                latest,
                new_status,
            )

        if new_status in {
            AccountStatus.SUSPENDED,
            AccountStatus.DEACTIVATED,
        }:
            return await self._cascade_revoke(
                user_id,
                org_id=org_id,
            )

        return None

    async def _cascade_revoke(
        self,
        user_id: str,
        *,
        org_id: str | None,
    ) -> CascadeResult:
        """
        Revoke every authentication surface.

        These operations should themselves be idempotent.

        Next: emit outbox ``account.security_revoked`` so cascades
        can be driven asynchronously across workers.
        """

        sessions = await (
            self._effects.revoke_all_sessions(
                user_id,
            )
        )

        refresh_tokens = await (
            self._effects.revoke_all_refresh_tokens(
                user_id,
            )
        )

        api_keys = await (
            self._effects.revoke_all_api_keys(
                user_id,
            )
        )

        service_accounts = await (
            self._effects.deactivate_service_accounts(
                org_id=org_id,
                owner_id=user_id,
            )
        )

        return CascadeResult(
            sessions_revoked=sessions,
            refresh_tokens_revoked=refresh_tokens,
            api_keys_revoked=api_keys,
            service_accounts_deactivated=service_accounts,
        )
