"""Local identity provider for development and testing.

Supports:

- Explicit local users
- Optional password authentication
- User lookup
- Disabled-user rejection
- Normalized identity objects
- Deterministic test behavior
- No accidental arbitrary-user impersonation unless explicitly enabled

This provider is intended for development/test environments.
Production deployments should use an external identity provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

__all__ = [
    "LocalIdentityConfigurationError",
    "LocalIdentityError",
    "LocalIdentityProvider",
    "LocalUser",
]


class LocalIdentityError(RuntimeError):
    """Base local identity provider error."""


class LocalIdentityConfigurationError(LocalIdentityError):
    """Invalid local identity configuration."""


@dataclass(frozen=True, slots=True)
class LocalUser:
    """Normalized local identity.

    Passwords are stored as plaintext for local/dev/test convenience.
    Production must use an external IdP — do not hash or rely on this store.
    """

    user_id: str
    username: str | None = None
    display_name: str | None = None
    email: str | None = None
    password: str | None = None
    roles: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()
    org_id: str | None = None
    disabled: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def identity(self) -> dict[str, object]:
        """Return the platform identity representation."""
        return {
            "user_id": self.user_id,
            "username": self.username or self.user_id,
            "provider": "local",
            "display_name": self.display_name or self.username or self.user_id,
            "email": self.email or "",
            "roles": list(self.roles),
            "groups": list(self.groups),
            "org_id": self.org_id,
            "metadata": dict(self.metadata),
        }


class LocalIdentityProvider:
    """
    In-process identity provider for development and testing.

    Authentication modes:

        password:
            Credentials must contain username/user_id + password.

        trusted:
            Explicitly trusts a user_id. Useful for integration tests.
            Disabled by default — never enable in production (no silent
            impersonation).

    Trusted mode should never be enabled in production.
    """

    def __init__(
        self,
        users: Mapping[str, LocalUser | Mapping[str, Any]] | None = None,
        *,
        allow_trusted_identity: bool = False,
    ) -> None:
        self._users: dict[str, LocalUser] = {
            user_id: self._normalize(user_id, value)
            for user_id, value in (users or {}).items()
        }

        self._allow_trusted_identity = allow_trusted_identity

    @staticmethod
    def _normalize(
        user_id: str,
        value: LocalUser | Mapping[str, Any],
    ) -> LocalUser:
        if isinstance(value, LocalUser):
            return value

        data = dict(value)

        data.setdefault("user_id", user_id)

        roles = tuple(
            str(role)
            for role in data.pop("roles", ())
        )

        groups = tuple(
            str(group)
            for group in data.pop("groups", ())
        )

        return LocalUser(
            user_id=str(data.pop("user_id")),
            username=(
                str(data["username"])
                if data.get("username") is not None
                else None
            ),
            display_name=(
                str(data["display_name"])
                if data.get("display_name") is not None
                else None
            ),
            email=(
                str(data["email"])
                if data.get("email") is not None
                else None
            ),
            password=(
                str(data["password"])
                if data.get("password") is not None
                else None
            ),
            roles=roles,
            groups=groups,
            org_id=(
                str(data["org_id"])
                if data.get("org_id") is not None
                else None
            ),
            disabled=bool(data.pop("disabled", False)),
            metadata=data,
        )

    def add_user(
        self,
        user: LocalUser,
    ) -> None:
        """Register or replace a local user."""
        if not user.user_id.strip():
            raise LocalIdentityConfigurationError(
                "user_id cannot be empty"
            )

        self._users[user.user_id] = user

    def remove_user(
        self,
        user_id: str,
    ) -> bool:
        """Remove a local user."""
        return self._users.pop(user_id, None) is not None

    async def authenticate(
        self,
        credentials: dict[str, object],
    ) -> dict[str, object] | None:
        """
        Authenticate a local user.

        Password authentication is preferred.

        Trusted identity mode must be explicitly enabled.
        """
        raw_id = (
            credentials.get("user_id")
            or credentials.get("username")
        )

        if raw_id is None:
            return None

        user_id = str(raw_id).strip()

        if not user_id:
            return None

        user = self._find_user(user_id)

        if user is None:
            return None

        if user.disabled:
            return None

        password = credentials.get("password")

        if password is not None:
            if user.password is None:
                return None

            if str(password) != user.password:
                return None

            return user.identity()

        if not self._allow_trusted_identity:
            return None

        return user.identity()

    async def get_user(
        self,
        user_id: str,
    ) -> dict[str, object] | None:
        """Return a local identity without authenticating."""
        user = self._find_user(user_id)

        if user is None or user.disabled:
            return None

        return user.identity()

    def _find_user(
        self,
        identifier: str,
    ) -> LocalUser | None:
        """Resolve by user_id or username."""
        direct = self._users.get(identifier)

        if direct is not None:
            return direct

        normalized = identifier.casefold()

        for user in self._users.values():
            if (
                user.username is not None
                and user.username.casefold() == normalized
            ):
                return user

        return None

    def list_users(self) -> list[dict[str, object]]:
        """Return non-secret user representations."""
        return [
            user.identity()
            for user in self._users.values()
            if not user.disabled
        ]

    def disable_user(
        self,
        user_id: str,
    ) -> bool:
        """Disable a local identity."""
        user = self._users.get(user_id)

        if user is None:
            return False

        self._users[user_id] = LocalUser(
            user_id=user.user_id,
            username=user.username,
            display_name=user.display_name,
            email=user.email,
            password=user.password,
            roles=user.roles,
            groups=user.groups,
            org_id=user.org_id,
            disabled=True,
            metadata=user.metadata,
        )

        return True

    def enable_user(
        self,
        user_id: str,
    ) -> bool:
        """Enable a local identity."""
        user = self._users.get(user_id)

        if user is None:
            return False

        self._users[user_id] = LocalUser(
            user_id=user.user_id,
            username=user.username,
            display_name=user.display_name,
            email=user.email,
            password=user.password,
            roles=user.roles,
            groups=user.groups,
            org_id=user.org_id,
            disabled=False,
            metadata=user.metadata,
        )

        return True

    async def close(self) -> None:
        """No-op; parity with LDAP IdentityProvider lifecycle."""
        return None