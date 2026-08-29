"""
Legacy authentication routes (fastapi-users compatibility adapter).

These routes are retained for compatibility while authentication
is migrated to ``identity``. New endpoints should use the identity
service directly.

fastapi-users must not remain a second JWT/session authority alongside
identity key-rotation and session infrastructure.

Next (identity-owned HTTP surface — not implemented in this module)::

    /auth/register
    /auth/login
    /auth/logout
    /auth/refresh
    /auth/password/*
    /auth/mfa/*
    /auth/oauth/*
    /auth/sessions/*
    /auth/api-keys/*
"""

from __future__ import annotations

from fastapi import APIRouter

from {{cookiecutter.project_name}}.db.models.users import (
    UserCreate,
    UserRead,
    UserUpdate,
    api_users,
{%- if cookiecutter.jwt_auth == "True" %}
    auth_jwt,
{%- endif %}
{%- if cookiecutter.cookie_auth == "True" %}
    auth_cookie,
{%- endif %}
)


router = APIRouter()


# ---------------------------------------------------------------------------
# User lifecycle
# ---------------------------------------------------------------------------

router.include_router(
    api_users.get_register_router(
        UserRead,
        UserCreate,
    ),
    prefix="/auth",
    tags=["auth"],
)

router.include_router(
    api_users.get_reset_password_router(),
    prefix="/auth",
    tags=["auth"],
)

router.include_router(
    api_users.get_verify_router(
        UserRead,
    ),
    prefix="/auth",
    tags=["auth"],
)


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

router.include_router(
    api_users.get_users_router(
        UserRead,
        UserUpdate,
    ),
    prefix="/users",
    tags=["users"],
)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

{%- if cookiecutter.jwt_auth == "True" %}

router.include_router(
    api_users.get_auth_router(
        auth_jwt,
    ),
    prefix="/auth/jwt",
    tags=["auth"],
)

{%- endif %}

{%- if cookiecutter.cookie_auth == "True" %}

router.include_router(
    api_users.get_auth_router(
        auth_cookie,
    ),
    prefix="/auth/cookie",
    tags=["auth"],
)

{%- endif %}
