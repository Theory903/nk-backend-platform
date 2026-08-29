"""
Multi-provider identity resolution and account linking.

An account may have multiple authentication identities:

    password:user@example.com
    google:123456789
    github:987654321
    ldap:alice
    oidc:abc123

The identity itself is globally unique:

    provider + provider_user_id

The account owns the identity.

Security rules:

    - An external identity can belong to only one account.
    - Verified identities may be linked explicitly.
    - Email matching alone never silently merges accounts.
    - Account creation and identity linking must be atomic.
    - Concurrent linking must be protected by a database uniqueness
      constraint on (provider, provider_user_id).
    - Unlinking the final usable authentication method is rejected.

The service depends on persistence protocols rather than dictionaries,
so SQL, Mongo, or another backend can implement the contract.

Next (not this turn):

    - SQL ``account_identities`` table with
      ``UNIQUE(provider, provider_user_id)``
    - Outbox events ``identity.linked`` / ``identity.unlinked``

Note: ``AccountNotFoundError`` here is a ``Problem`` subclass.
``account_lifecycle.AccountNotFoundError`` is a separate ``LookupError``.
Import from the module that owns the call site (or alias) to avoid clashes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol

from {{cookiecutter.project_name}}.core.errors import Problem
from {{cookiecutter.project_name}}.core.identifiers import new_id


__all__ = [
    "AccountLinkingConflictError",
    "AccountLinkingService",
    "AccountNotFoundError",
    "CannotUnlinkLastIdentityError",
    "IdentityAlreadyLinkedError",
    "IdentityRepository",
    "IdentityUniqueConstraintError",
    "InMemoryIdentityRepository",
    "LinkedAccount",
    "UserIdentity",
]


@dataclass(frozen=True, slots=True)
class UserIdentity:
    """External authentication identity linked to an account."""

    provider: str
    provider_user_id: str

    email: str | None = None
    verified: bool = False
    linked_at: datetime | None = None

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.provider_user_id}"


@dataclass(frozen=True, slots=True)
class LinkedAccount:
    """Account plus its linked authentication identities."""

    user_id: str
    email: str

    identities: tuple[UserIdentity, ...] = ()

    primary_provider: str = "password"
    email_verified: bool = False


class IdentityAlreadyLinkedError(Problem):
    """External identity is already owned by another account."""

    def __init__(
        self,
        provider: str,
        provider_user_id: str,
    ) -> None:
        super().__init__(
            title="Identity Already Linked",
            status_code=409,
            detail=(
                f"identity '{provider}:{provider_user_id}' "
                "is already linked to another account"
            ),
        )


class AccountLinkingConflictError(Problem):
    """Identity linking would create an unsafe account merge."""

    def __init__(self) -> None:
        super().__init__(
            title="Account Linking Conflict",
            status_code=409,
            detail=(
                "the identity cannot be automatically linked to "
                "the requested account"
            ),
        )


class CannotUnlinkLastIdentityError(Problem):
    """Removing the identity would leave the account inaccessible."""

    def __init__(self) -> None:
        super().__init__(
            title="Cannot Unlink Identity",
            status_code=409,
            detail=(
                "at least one usable authentication identity "
                "must remain linked to the account"
            ),
        )


class AccountNotFoundError(Problem):
    """Target account does not exist."""

    def __init__(
        self,
        user_id: str,
    ) -> None:
        super().__init__(
            title="Account Not Found",
            status_code=404,
            detail=f"account '{user_id}' was not found",
        )


class IdentityRepository(Protocol):
    """
    Persistence contract for identity/account resolution.

    Implementations should enforce:

        UNIQUE(provider, provider_user_id)

    at the database level.
    """

    async def get_account(
        self,
        user_id: str,
    ) -> LinkedAccount | None:
        ...

    async def find_by_identity(
        self,
        provider: str,
        provider_user_id: str,
    ) -> LinkedAccount | None:
        ...

    async def find_by_email(
        self,
        email: str,
    ) -> list[LinkedAccount]:
        ...

    async def create_account(
        self,
        account: LinkedAccount,
    ) -> LinkedAccount:
        ...

    async def add_identity(
        self,
        user_id: str,
        identity: UserIdentity,
    ) -> LinkedAccount:
        ...

    async def remove_identity(
        self,
        user_id: str,
        provider: str,
        provider_user_id: str,
    ) -> bool:
        ...

    async def count_identities(
        self,
        user_id: str,
    ) -> int:
        ...


class IdentityUniqueConstraintError(Exception):
    """Raised when UNIQUE(provider, provider_user_id) is violated."""


class InMemoryIdentityRepository:
    """
    Single-process test/dev repository for account linking.

    Enforces UNIQUE(provider, provider_user_id) in process memory.
    Not safe across processes or durable storage — production must use
    a SQL/Mongo implementation with a real unique constraint.
    """

    def __init__(self) -> None:
        self._accounts: dict[str, LinkedAccount] = {}
        # (provider, provider_user_id) -> user_id
        self._identity_index: dict[tuple[str, str], str] = {}

    def _identity_key(
        self,
        provider: str,
        provider_user_id: str,
    ) -> tuple[str, str]:
        return (provider, provider_user_id)

    async def get_account(
        self,
        user_id: str,
    ) -> LinkedAccount | None:
        return self._accounts.get(user_id)

    async def find_by_identity(
        self,
        provider: str,
        provider_user_id: str,
    ) -> LinkedAccount | None:
        user_id = self._identity_index.get(
            self._identity_key(provider, provider_user_id),
        )
        if user_id is None:
            return None
        return self._accounts.get(user_id)

    async def find_by_email(
        self,
        email: str,
    ) -> list[LinkedAccount]:
        normalized = email.strip().casefold()
        return [
            account
            for account in self._accounts.values()
            if account.email == normalized
        ]

    async def create_account(
        self,
        account: LinkedAccount,
    ) -> LinkedAccount:
        for identity in account.identities:
            key = self._identity_key(
                identity.provider,
                identity.provider_user_id,
            )
            if key in self._identity_index:
                raise IdentityUniqueConstraintError(
                    f"identity '{identity.key}' already linked",
                )

        self._accounts[account.user_id] = account
        for identity in account.identities:
            self._identity_index[
                self._identity_key(
                    identity.provider,
                    identity.provider_user_id,
                )
            ] = account.user_id
        return account

    async def add_identity(
        self,
        user_id: str,
        identity: UserIdentity,
    ) -> LinkedAccount:
        account = self._accounts.get(user_id)
        if account is None:
            raise KeyError(f"account '{user_id}' not found")

        key = self._identity_key(
            identity.provider,
            identity.provider_user_id,
        )
        if key in self._identity_index:
            raise IdentityUniqueConstraintError(
                f"identity '{identity.key}' already linked",
            )

        updated = replace(
            account,
            identities=(*account.identities, identity),
        )
        self._accounts[user_id] = updated
        self._identity_index[key] = user_id
        return updated

    async def remove_identity(
        self,
        user_id: str,
        provider: str,
        provider_user_id: str,
    ) -> bool:
        account = self._accounts.get(user_id)
        if account is None:
            return False

        remaining = tuple(
            item
            for item in account.identities
            if not (
                item.provider == provider
                and item.provider_user_id == provider_user_id
            )
        )
        if len(remaining) == len(account.identities):
            return False

        self._accounts[user_id] = replace(
            account,
            identities=remaining,
        )
        self._identity_index.pop(
            self._identity_key(provider, provider_user_id),
            None,
        )
        return True

    async def count_identities(
        self,
        user_id: str,
    ) -> int:
        account = self._accounts.get(user_id)
        if account is None:
            return 0
        return len(account.identities)


class AccountLinkingService:
    """
    Resolves external identities into platform accounts.

    This class contains policy. Persistence remains in the repository.
    """

    def __init__(
        self,
        repository: IdentityRepository,
    ) -> None:
        self._repository = repository

    async def create_account(
        self,
        email: str,
        *,
        provider: str = "password",
        provider_user_id: str = "",
        verified: bool = False,
    ) -> LinkedAccount:
        normalized_email = self._normalize_email(email)

        user_id = new_id("usr")

        identity = UserIdentity(
            provider=provider,
            provider_user_id=provider_user_id,
            email=normalized_email,
            verified=verified,
            linked_at=datetime.now(UTC),
        )

        account = LinkedAccount(
            user_id=user_id,
            email=normalized_email,
            identities=(identity,),
            primary_provider=provider,
            email_verified=verified,
        )

        return await self._repository.create_account(account)

    async def resolve(
        self,
        provider: str,
        provider_user_id: str,
    ) -> LinkedAccount | None:
        """
        Resolve an external identity.

        Never resolves by email here. Identity resolution must be exact.
        """
        if not provider or not provider_user_id:
            return None

        return await self._repository.find_by_identity(
            provider,
            provider_user_id,
        )

    async def resolve_by_email(
        self,
        email: str,
    ) -> list[LinkedAccount]:
        """
        Resolve accounts by normalized email.

        Email matching is informational. It is not proof that two
        identities belong to the same person.
        """
        normalized = self._normalize_email(email)

        return await self._repository.find_by_email(
            normalized,
        )

    async def link(
        self,
        user_id: str,
        *,
        provider: str,
        provider_user_id: str,
        email: str | None = None,
        verified: bool = False,
    ) -> LinkedAccount:
        """
        Explicitly link an external identity.

        The caller must already have authenticated the account and
        completed whatever provider-specific verification is required.
        """

        account = await self._repository.get_account(user_id)

        if account is None:
            raise AccountNotFoundError(user_id)

        existing = await self._repository.find_by_identity(
            provider,
            provider_user_id,
        )

        if existing is not None:
            if existing.user_id == user_id:
                return existing

            raise IdentityAlreadyLinkedError(
                provider,
                provider_user_id,
            )

        normalized_email = (
            self._normalize_email(email)
            if email
            else None
        )

        identity = UserIdentity(
            provider=provider,
            provider_user_id=provider_user_id,
            email=normalized_email,
            verified=verified,
            linked_at=datetime.now(UTC),
        )

        try:
            return await self._repository.add_identity(
                user_id,
                identity,
            )
        except Exception as exc:
            # A concurrent request may have won the unique
            # (provider, provider_user_id) constraint.
            raise AccountLinkingConflictError() from exc

    async def unlink(
        self,
        user_id: str,
        *,
        provider: str,
        provider_user_id: str,
    ) -> bool:
        """
        Remove an external identity.

        The last authentication method cannot be removed.
        """

        account = await self._repository.get_account(user_id)

        if account is None:
            raise AccountNotFoundError(user_id)

        identity = next(
            (
                item
                for item in account.identities
                if (
                    item.provider == provider
                    and item.provider_user_id
                    == provider_user_id
                )
            ),
            None,
        )

        if identity is None:
            return False

        identity_count = await self._repository.count_identities(
            user_id,
        )

        if identity_count <= 1:
            raise CannotUnlinkLastIdentityError()

        return await self._repository.remove_identity(
            user_id,
            provider,
            provider_user_id,
        )

    async def find_or_create(
        self,
        email: str,
        *,
        provider: str,
        provider_user_id: str,
        provider_email_verified: bool = False,
    ) -> tuple[LinkedAccount, bool]:
        """
        Resolve an identity or create a new account.

        Important security behavior:

            identity match
                -> resolve existing account

            no identity + verified email
                -> do NOT silently merge

            no identity + no matching account
                -> create account

        An existing account with the same email requires an explicit
        account-linking flow.
        """

        existing = await self.resolve(
            provider,
            provider_user_id,
        )

        if existing is not None:
            return existing, False

        normalized_email = self._normalize_email(email)

        matches = await self.resolve_by_email(
            normalized_email,
        )

        if matches:
            # Do not silently merge external identities based only
            # on email. The user must prove ownership of the existing
            # account and explicitly link the provider.
            raise AccountLinkingConflictError()

        account = await self.create_account(
            normalized_email,
            provider=provider,
            provider_user_id=provider_user_id,
            verified=provider_email_verified,
        )

        return account, True

    @staticmethod
    def _normalize_email(
        email: str,
    ) -> str:
        return email.strip().casefold()
