"""Identity domain: providers, credentials, sessions, and authorization.

HTTP surface (next; replace legacy ``web.api.users`` fastapi-users adapter)::

    /auth/register
    /auth/login
    /auth/logout
    /auth/refresh
    /auth/password/*
    /auth/mfa/*
    /auth/oauth/*
    /auth/sessions/*
    /auth/api-keys/*

Single JWT/session authority lives here — not in fastapi-users.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class IdentityProvider(Protocol):
    """Verifies credentials and returns a principal.

    Implementations are swapped via settings (local first, then OAuth/LDAP/SCIM).
    """

    async def authenticate(self, credentials: dict[str, object]) -> dict[str, object] | None: ...

    async def get_user(self, user_id: str) -> dict[str, object] | None: ...
