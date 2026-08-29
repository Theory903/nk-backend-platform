"""LDAP / Active Directory authentication provider.

Supports:

- LDAP and Active Directory
- LDAPS
- StartTLS
- TLS certificate validation
- Server pools / HA
- Connection and operation timeouts
- User authentication
- User attribute lookup
- Group membership lookup
- LDAP filter escaping (``escape_filter_chars`` on usernames)
- AD userPrincipalName / sAMAccountName
- Normalized platform identity
- Mock backend for tests

Authentication vs authorization
-------------------------------
This module authenticates identity (who the principal is) and may
surface directory groups as attributes. Authorization (what the
principal may do) stays in the platform RBAC / permissions layer.

Bind model
----------
``Ldap3Backend.authenticate`` binds with ``user=username`` then looks
up the entry. That works for AD UPN-style usernames
(``user@domain``). Production deployments that bind with a constructed
DN or UPN *after* a service-account search should keep that flow
outside this short-lived direct-bind path — this provider does not
implement search-then-bind by default.

The provider intentionally keeps ldap3 behind a small protocol so the
rest of the authentication system does not depend on ldap3 directly.
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "LdapAuthenticationError",
    "LdapBackend",
    "LdapConfig",
    "LdapConfigurationError",
    "LdapIdentityProvider",
    "LdapUser",
    "Ldap3Backend",
    "MockLdapBackend",
]


class LdapAuthenticationError(RuntimeError):
    """LDAP authentication infrastructure failure."""


class LdapConfigurationError(ValueError):
    """Invalid LDAP configuration."""


@dataclass(frozen=True, slots=True)
class LdapUser:
    """Normalized LDAP identity."""

    user_id: str
    username: str
    display_name: str
    email: str = ""
    groups: tuple[str, ...] = ()
    dn: str = ""


@dataclass(frozen=True, slots=True)
class LdapConfig:
    """LDAP / Active Directory connection configuration."""

    servers: tuple[str, ...] = ("localhost",)

    port: int = 636

    use_ssl: bool = True

    start_tls: bool = False

    verify_certificates: bool = True

    ca_file: str | None = None

    base_dn: str = "dc=example,dc=com"

    user_search_base: str | None = None

    user_filter: str = (
        "(&(objectClass=user)(|(uid={username})"
        "(sAMAccountName={username})"
        "(userPrincipalName={username})))"
    )

    username_attribute: str = "sAMAccountName"

    user_id_attribute: str = "objectGUID"

    display_name_attribute: str = "displayName"

    email_attribute: str = "mail"

    group_attribute: str = "memberOf"

    connect_timeout_s: float = 5.0

    receive_timeout_s: float = 10.0

    bind_dn: str | None = None

    bind_password: str | None = None

    @classmethod
    def validate(cls, config: LdapConfig) -> None:
        if not config.servers:
            raise LdapConfigurationError(
                "at least one LDAP server is required"
            )

        if not 1 <= config.port <= 65535:
            raise LdapConfigurationError(
                f"invalid LDAP port: {config.port}"
            )

        if config.use_ssl and config.start_tls:
            raise LdapConfigurationError(
                "use_ssl and start_tls cannot both be enabled"
            )

        if config.connect_timeout_s <= 0:
            raise LdapConfigurationError(
                "connect_timeout_s must be positive"
            )

        if config.receive_timeout_s <= 0:
            raise LdapConfigurationError(
                "receive_timeout_s must be positive"
            )


@runtime_checkable
class LdapBackend(Protocol):
    async def authenticate(
        self,
        username: str,
        password: str,
    ) -> LdapUser | None:
        ...

    async def search_user(
        self,
        username: str,
    ) -> LdapUser | None:
        ...

    async def close(self) -> None:
        ...


class MockLdapBackend:
    """Deterministic test backend."""

    def __init__(
        self,
        users: dict[str, dict[str, Any]],
    ) -> None:
        self.users = users
        self.bound: list[str] = []

    async def authenticate(
        self,
        username: str,
        password: str,
    ) -> LdapUser | None:
        user = self.users.get(username)

        if user is None:
            return None

        if user.get("password") != password:
            return None

        self.bound.append(username)

        return self._identity(username, user)

    async def search_user(
        self,
        username: str,
    ) -> LdapUser | None:
        user = self.users.get(username)

        if user is None:
            return None

        return self._identity(username, user)

    async def close(self) -> None:
        return None

    @staticmethod
    def _identity(
        username: str,
        user: dict[str, Any],
    ) -> LdapUser:
        return LdapUser(
            user_id=str(user.get("user_id", username)),
            username=username,
            display_name=str(
                user.get("display_name", username)
            ),
            email=str(user.get("email", "")),
            groups=tuple(user.get("groups", ())),
            dn=str(user.get("dn", "")),
        )


class Ldap3Backend:
    """
    Production ldap3 backend.

    Each authentication creates a short-lived connection and binds
    with the supplied credentials. This avoids keeping authenticated
    user passwords in a long-lived connection.

    A service account is used only for directory lookups when configured.
    """

    def __init__(self, config: LdapConfig) -> None:
        LdapConfig.validate(config)

        self.config = config
        self._servers: list[Any] | None = None

    def _build_servers(self) -> list[Any]:
        from ldap3 import Server

        tls = self._build_tls()

        return [
            Server(
                host,
                port=self.config.port,
                use_ssl=self.config.use_ssl,
                tls=tls,
                connect_timeout=self.config.connect_timeout_s,
            )
            for host in self.config.servers
        ]

    def _build_tls(self) -> Any:
        from ldap3 import Tls

        validate = (
            ssl.CERT_REQUIRED
            if self.config.verify_certificates
            else ssl.CERT_NONE
        )

        return Tls(
            validate=validate,
            ca_certs_file=self.config.ca_file,
        )

    def _build_pool(self) -> Any:
        from ldap3 import ServerPool

        return ServerPool(
            self._build_servers(),
            active=True,
            exhaust=True,
        )

    def _new_connection(
        self,
        *,
        user: str,
        password: str,
    ) -> Any:
        from ldap3 import Connection

        connection = Connection(
            self._build_pool(),
            user=user,
            password=password,
            auto_bind=False,
            receive_timeout=self.config.receive_timeout_s,
        )

        if not connection.open():
            raise LdapAuthenticationError(
                "failed to open LDAP connection"
            )

        if self.config.start_tls:
            if not connection.start_tls():
                connection.unbind()
                raise LdapAuthenticationError(
                    "LDAP StartTLS negotiation failed"
                )

        return connection

    async def authenticate(
        self,
        username: str,
        password: str,
    ) -> LdapUser | None:
        """
        Authenticate directly against LDAP/AD.

        Binds with ``user=username`` (UPN-style for AD is typical).
        Passwords are never persisted by this backend.

        Note: some directories prefer search-then-bind with a constructed
        DN after a service-account lookup; this backend keeps the
        short-lived direct-bind approach instead.
        """
        if not username or not password:
            return None

        connection = None

        try:
            connection = self._new_connection(
                user=username,
                password=password,
            )

            if not connection.bind():
                return None

            return await self._lookup_bound_user(
                connection,
                username,
            )

        except LdapAuthenticationError:
            raise
        except Exception as exc:
            raise LdapAuthenticationError(
                "LDAP authentication failed"
            ) from exc
        finally:
            if connection is not None:
                connection.unbind()

    async def search_user(
        self,
        username: str,
    ) -> LdapUser | None:
        """
        Search using the configured service account.

        This is useful when the login bind and directory lookup
        credentials are different.
        """
        if not self.config.bind_dn:
            raise LdapConfigurationError(
                "bind_dn is required for service-account lookup"
            )

        connection = None

        try:
            connection = self._new_connection(
                user=self.config.bind_dn,
                password=self.config.bind_password or "",
            )

            if not connection.bind():
                raise LdapAuthenticationError(
                    "LDAP service-account bind failed"
                )

            return await self._lookup_bound_user(
                connection,
                username,
            )

        except LdapAuthenticationError:
            raise
        except Exception as exc:
            raise LdapAuthenticationError(
                "LDAP directory lookup failed"
            ) from exc
        finally:
            if connection is not None:
                connection.unbind()

    def build_user_filter(self, username: str) -> str:
        """Build a search filter with LDAP-special characters escaped.

        Always runs ``escape_filter_chars`` on ``username`` before
        interpolating into ``user_filter`` so raw filter injection is
        not possible via username input.
        """
        from ldap3.utils.conv import escape_filter_chars

        escaped_username = escape_filter_chars(username)
        return self.config.user_filter.format(
            username=escaped_username,
        )

    async def _lookup_bound_user(
        self,
        connection: Any,
        username: str,
    ) -> LdapUser | None:
        search_base = (
            self.config.user_search_base
            or self.config.base_dn
        )

        filter_str = self.build_user_filter(username)

        attributes = [
            self.config.username_attribute,
            self.config.user_id_attribute,
            self.config.display_name_attribute,
            self.config.email_attribute,
            self.config.group_attribute,
            "distinguishedName",
        ]

        ok = connection.search(
            search_base=search_base,
            search_filter=filter_str,
            attributes=attributes,
        )

        if not ok or not connection.entries:
            return None

        entry = connection.entries[0]

        return LdapUser(
            user_id=self._attribute(
                entry,
                self.config.user_id_attribute,
                fallback=username,
            ),
            username=self._attribute(
                entry,
                self.config.username_attribute,
                fallback=username,
            ),
            display_name=self._attribute(
                entry,
                self.config.display_name_attribute,
                fallback=username,
            ),
            email=self._attribute(
                entry,
                self.config.email_attribute,
            ),
            groups=self._multi_attribute(
                entry,
                self.config.group_attribute,
            ),
            dn=self._attribute(
                entry,
                "distinguishedName",
            ),
        )

    @staticmethod
    def _attribute(
        entry: Any,
        name: str,
        *,
        fallback: str = "",
    ) -> str:
        try:
            value = entry[name].value
        except Exception:
            return fallback

        if value is None:
            return fallback

        return str(value)

    @staticmethod
    def _multi_attribute(
        entry: Any,
        name: str,
    ) -> tuple[str, ...]:
        try:
            values = entry[name].values
        except Exception:
            return ()

        return tuple(
            str(value)
            for value in values
            if value
        )

    async def close(self) -> None:
        """No persistent connections to close."""
        return None


class LdapIdentityProvider:
    """
    Platform identity provider backed by LDAP/Active Directory.
    """

    def __init__(
        self,
        backend: LdapBackend,
        *,
        provider_name: str = "ldap",
    ) -> None:
        self.backend = backend
        self.provider_name = provider_name

    async def authenticate(
        self,
        credentials: dict[str, Any],
    ) -> dict[str, Any] | None:
        username = str(
            credentials.get("username", "")
        ).strip()

        password = credentials.get("password")

        if not username or not isinstance(password, str):
            return None

        identity = await self.backend.authenticate(
            username,
            password,
        )

        if identity is None:
            return None

        return {
            "user_id": identity.user_id,
            "username": identity.username,
            "provider": self.provider_name,
            "display_name": identity.display_name,
            "email": identity.email,
            "groups": list(identity.groups),
            "dn": identity.dn,
        }

    async def get_user(
        self,
        user_id: str,
    ) -> dict[str, Any] | None:
        """Directory lookup without password bind (service account)."""
        identity = await self.backend.search_user(user_id)
        if identity is None:
            return None
        return {
            "user_id": identity.user_id,
            "username": identity.username,
            "provider": self.provider_name,
            "display_name": identity.display_name,
            "email": identity.email,
            "groups": list(identity.groups),
            "dn": identity.dn,
        }

    async def close(self) -> None:
        await self.backend.close()