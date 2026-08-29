"""
FastAPI authentication and authorization dependencies.

Resolves:

    Authorization: Bearer <token>
    Authorization: ApiKey <api-key>
    session cookie
    X-Session-Id

into a Principal.

Authentication is deliberately separated from authorization:

    CurrentUser()
        -> authentication

    RequirePermission(...)
        -> authorization

    RequireRole(...)
        -> authorization

Cookie-backed sessions may additionally require CSRF validation for
state-changing browser requests via RequireCsrf (Bearer/ApiKey skip).

Production persistence is injected through dependency providers rather
than constructing stores at import time.

Account status gating (AccountLifecycleManager.can_authenticate) is
deferred — that API is async while CurrentUser remains sync to match
SessionStore.get.

Sessions: inject via ``configure_auth_stores(sessions=...)``.
``get_session_store()`` / ``_resolve_session`` always use that configured
instance — never construct ``SessionStore()`` inside CurrentUser.
``SecureSessionStore`` is a deprecated alias for ``SessionStore``.
"""

from __future__ import annotations

from typing import Annotated, Any, Callable

from fastapi import Cookie, Depends, Header, Request

from {{cookiecutter.project_name}}.core.errors import Problem
from {{cookiecutter.project_name}}.core.security import validate_token
from {{cookiecutter.project_name}}.identity.api_keys import (
    ApiKeyRecord,
    ApiKeyStore,
)
from {{cookiecutter.project_name}}.identity.csrf import CSRF_HEADER, CsrfProtection
from {{cookiecutter.project_name}}.identity.permissions import has_permission
from {{cookiecutter.project_name}}.identity.principal import Anonymous, Principal
from {{cookiecutter.project_name}}.identity.session import SessionStore
from {{cookiecutter.project_name}}.identity.session_lifecycle import SecureSessionStore
from {{cookiecutter.project_name}}.settings import settings


_STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


# ---------------------------------------------------------------------------
# Store dependencies
# ---------------------------------------------------------------------------

_api_key_store: ApiKeyStore | None = None
_session_store: SessionStore | None = None
_csrf_protection: CsrfProtection | None = None


def configure_auth_stores(
    *,
    api_keys: ApiKeyStore | None = None,
    sessions: SessionStore | None = None,
    csrf: CsrfProtection | None = None,
) -> None:
    """
    Configure authentication stores during application startup.

    Production applications should provide persistent/centralized
    implementations here. Do not construct stores at import time.

    Example:

        configure_auth_stores(
            api_keys=redis_api_key_store,
            sessions=redis_session_store,
            csrf=CsrfProtection(settings.users_secret),
        )
    """

    global _api_key_store
    global _session_store
    global _csrf_protection

    if api_keys is not None:
        _api_key_store = api_keys

    if sessions is not None:
        _session_store = sessions

    if csrf is not None:
        _csrf_protection = csrf


def get_api_key_store() -> ApiKeyStore:
    """
    Return the configured API-key store.
    """

    if _api_key_store is None:
        raise Problem(
            title="Server Misconfigured",
            status_code=500,
            detail="API key store has not been configured",
        )

    return _api_key_store


def get_session_store() -> SessionStore:
    """
    Return the configured session store.
    """

    if _session_store is None:
        raise Problem(
            title="Server Misconfigured",
            status_code=500,
            detail="session store has not been configured",
        )

    return _session_store


# ---------------------------------------------------------------------------
# JWT authentication
# ---------------------------------------------------------------------------

def _resolve_jwt(token: str) -> Principal:
    """
    Resolve a signed application token into a Principal.

    This function assumes validate_token performs the cryptographic
    validation of the token.
    """

    secret = getattr(settings, "users_secret", "")

    if not secret:
        raise Problem(
            title="Server Misconfigured",
            status_code=500,
            detail=(
                "USERS_SECRET is not set; refusing to sign/verify "
                "with a fallback secret"
            ),
        )

    subject = validate_token(
        token,
        secret,
    )

    if not subject:
        raise Problem(
            title="Invalid Token",
            status_code=401,
            detail="token expired or invalid",
        )

    return Principal(
        user_id=subject,
        provider="token",
    )


# ---------------------------------------------------------------------------
# API-key authentication
# ---------------------------------------------------------------------------

def _principal_from_api_key(
    record: ApiKeyRecord,
) -> Principal:
    """
    Convert an API-key record into a Principal.

    key_id is used as the stable machine identity. The human-readable
    key name must never be treated as the identity.
    """

    roles = {
        "service",
    }

    return Principal(
        user_id=f"svc:{record.key_id}",
        roles=frozenset(roles),
        provider="api_key",
        is_service=True,
    )


def _resolve_api_key(
    raw_key: str,
    *,
    client_ip: str | None = None,
) -> Principal:
    """
    Validate an API key and create its Principal.
    """

    if not raw_key:
        raise Problem(
            title="Invalid API Key",
            status_code=401,
            detail="API key is required",
        )

    record = get_api_key_store().verify(
        raw_key,
        client_ip=client_ip,
    )

    if record is None:
        raise Problem(
            title="Invalid API Key",
            status_code=401,
            detail="unrecognized, expired, revoked, or restricted key",
        )

    return _principal_from_api_key(record)


# ---------------------------------------------------------------------------
# Session authentication
# ---------------------------------------------------------------------------

def _resolve_session(
    session_id: str,
) -> Principal:
    """
    Resolve a browser session into a Principal.
    """

    if not session_id:
        raise Problem(
            title="Invalid Session",
            status_code=401,
            detail="session is missing",
        )

    session = get_session_store().get(session_id)

    if session is None:
        raise Problem(
            title="Session Expired",
            status_code=401,
            detail="session invalid or expired",
        )

    principal_id = session.get("principal_id")

    if not principal_id:
        raise Problem(
            title="Invalid Session",
            status_code=401,
            detail="session has no principal",
        )

    # SessionStore.create keeps extras under "data"; accept top-level too.
    roles = session.get("roles")
    if roles is None:
        data = session.get("data") or {}
        roles = data.get("roles", ())

    return Principal(
        user_id=str(principal_id),
        roles=frozenset(str(role) for role in roles),
        provider="session",
    )


# ---------------------------------------------------------------------------
# Authorization header parsing
# ---------------------------------------------------------------------------

def _parse_authorization(
    authorization: str,
) -> tuple[str, str] | None:
    """
    Parse:

        Bearer <token>
        ApiKey <key>

    Returns None for malformed input.
    """

    value = authorization.strip()

    if not value:
        return None

    parts = value.split()

    if len(parts) != 2:
        return None

    scheme, credential = parts

    if not credential:
        return None

    return scheme.lower(), credential


# ---------------------------------------------------------------------------
# Main authentication dependency
# ---------------------------------------------------------------------------

def CurrentUser(
    request: Request,
    authorization: Annotated[
        str | None,
        Header(alias="Authorization"),
    ] = None,
    session_cookie: Annotated[
        str | None,
        Cookie(alias="session"),
    ] = None,
    x_session_id: Annotated[
        str | None,
        Header(alias="X-Session-Id"),
    ] = None,
) -> Principal:
    """
    Resolve the authenticated Principal.

    Authentication priority:

        1. Authorization: Bearer
        2. Authorization: ApiKey
        3. session cookie
        4. X-Session-Id compatibility header

    Session cookies are preferred over custom session headers for browser
    authentication.

    The client IP is passed to API-key verification when supported.
    """

    if authorization:
        parsed = _parse_authorization(
            authorization,
        )

        if parsed is None:
            raise Problem(
                title="Invalid Authorization Header",
                status_code=401,
                detail="malformed Authorization header",
            )

        scheme, credential = parsed

        if scheme == "bearer":
            principal = _resolve_jwt(credential)

        elif scheme == "apikey":
            client_ip = request.client.host if request.client else None

            principal = _resolve_api_key(
                credential,
                client_ip=client_ip,
            )

        else:
            raise Problem(
                title="Unsupported Authentication Scheme",
                status_code=401,
                detail="unsupported Authorization scheme",
            )

        request.state.principal = principal

        return principal

    # Browser session authentication.
    effective_session_id = (
        session_cookie
        or (
            x_session_id.strip()
            if x_session_id and x_session_id.strip()
            else None
        )
    )

    if effective_session_id:
        principal = _resolve_session(
            effective_session_id,
        )

        request.state.principal = principal
        request.state.session_id = effective_session_id

        return principal

    raise Problem(
        title="Not Authenticated",
        status_code=401,
        detail="authentication credentials are required",
    )


# ---------------------------------------------------------------------------
# Optional authentication
# ---------------------------------------------------------------------------

def OptionalUser(
    request: Request,
    authorization: Annotated[
        str | None,
        Header(alias="Authorization"),
    ] = None,
    session_cookie: Annotated[
        str | None,
        Cookie(alias="session"),
    ] = None,
) -> Principal:
    """
    Resolve a Principal when credentials are supplied.

    Missing credentials return Anonymous instead of 401.

    Invalid supplied credentials still fail with 401.
    """

    if not authorization and not session_cookie:
        request.state.principal = Anonymous
        return Anonymous

    return CurrentUser(
        request=request,
        authorization=authorization,
        session_cookie=session_cookie,
    )


# ---------------------------------------------------------------------------
# Permission authorization
# ---------------------------------------------------------------------------

def RequirePermission(
    required: str,
) -> Callable[..., Any]:
    """
    Require a specific permission.

    Usage:

        @router.get(
            "/records",
            dependencies=[Depends(RequirePermission("records.read"))],
        )
    """

    if not required or not required.strip():
        raise ValueError(
            "permission cannot be empty",
        )

    def checker(
        principal: Annotated[
            Principal,
            Depends(CurrentUser),
        ],
    ) -> Principal:
        if principal.is_anonymous:
            raise Problem(
                title="Forbidden",
                status_code=403,
                detail="authenticated access is required",
            )

        if not has_permission(
            principal,
            required,
        ):
            raise Problem(
                title="Insufficient Permissions",
                status_code=403,
                detail=f"requires '{required}'",
            )

        return principal

    return checker


# ---------------------------------------------------------------------------
# Role authorization
# ---------------------------------------------------------------------------

def RequireRole(
    role: str,
) -> Callable[..., Any]:
    """
    Require a specific role.

    Usage:

        current_user = Depends(RequireRole("admin"))
    """

    if not role or not role.strip():
        raise ValueError(
            "role cannot be empty",
        )

    def checker(
        principal: Annotated[
            Principal,
            Depends(CurrentUser),
        ],
    ) -> Principal:
        if principal.is_anonymous:
            raise Problem(
                title="Forbidden",
                status_code=403,
                detail="authenticated access is required",
            )

        if not principal.has_role(role):
            raise Problem(
                title="Insufficient Role",
                status_code=403,
                detail=f"requires role '{role}'",
            )

        return principal

    return checker


# ---------------------------------------------------------------------------
# CSRF (cookie / session auth only)
# ---------------------------------------------------------------------------

def RequireCsrf(
    *,
    action: str = "",
) -> Callable[..., Any]:
    """
    Validate ``X-CSRF-Token`` for cookie-session state-changing requests.

    Skips Bearer and ApiKey principals. Safe no-op for GET/HEAD/OPTIONS.
    Requires ``request.state.session_id`` (set by CurrentUser on session auth)
    and a configured ``CsrfProtection`` (via configure_auth_stores).
    """

    def checker(
        request: Request,
        x_csrf_token: Annotated[
            str | None,
            Header(alias=CSRF_HEADER),
        ] = None,
    ) -> None:
        principal = getattr(request.state, "principal", None)

        if principal is None or getattr(principal, "provider", None) != "session":
            return

        if request.method.upper() not in _STATE_CHANGING_METHODS:
            return

        session_id = getattr(request.state, "session_id", None)
        if not session_id:
            raise Problem(
                title="CSRF Validation Failed",
                status_code=403,
                detail="session context required for CSRF validation",
            )

        if _csrf_protection is None:
            raise Problem(
                title="Server Misconfigured",
                status_code=500,
                detail="CSRF protection has not been configured",
            )

        token = (x_csrf_token or "").strip()
        if not _csrf_protection.validate_token(
            session_id,
            token,
            action=action,
        ):
            raise Problem(
                title="CSRF Validation Failed",
                status_code=403,
                detail="missing or invalid CSRF token",
            )

    return checker


__all__ = [
    "Anonymous",
    "CurrentUser",
    "OptionalUser",
    "RequireCsrf",
    "RequirePermission",
    "RequireRole",
    "SecureSessionStore",
    "SessionStore",
    "configure_auth_stores",
    "get_api_key_store",
    "get_session_store",
]