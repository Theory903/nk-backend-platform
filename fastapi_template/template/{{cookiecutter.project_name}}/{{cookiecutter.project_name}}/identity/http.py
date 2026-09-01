"""Identity-owned authentication HTTP surface.

The database/authentication adapter remains replaceable, while the public
contract stays stable at ``/auth/*``. The legacy users router is retained as a
file-level compatibility adapter but is no longer mounted by the framework.
"""

from __future__ import annotations

from fastapi import APIRouter

from {{cookiecutter.project_name}}.db.models.users import (
    UserCreate,
    UserRead,
    UserUpdate,
    api_users,
{%- if cookiecutter.jwt_auth in [True, "True", "true", 1, "1"] %}
    auth_jwt,
{%- endif %}
{%- if cookiecutter.cookie_auth in [True, "True", "true", 1, "1"] %}
    auth_cookie,
{%- endif %}
)
from {{cookiecutter.project_name}}.identity.platform_http import (
    router as platform_router,
)
from {{cookiecutter.project_name}}.settings import settings

router = APIRouter()
router.include_router(platform_router)

router.include_router(
    api_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)
router.include_router(api_users.get_reset_password_router(), prefix="/auth", tags=["auth"])
router.include_router(
    api_users.get_verify_router(UserRead),
    prefix="/auth",
    tags=["auth"],
)
if settings.security_require_auth:
    router.include_router(
        api_users.get_users_router(UserRead, UserUpdate),
        prefix="/users",
        tags=["users"],
    )
{%- if cookiecutter.jwt_auth in [True, "True", "true", 1, "1"] %}
router.include_router(
    api_users.get_auth_router(auth_jwt),
    prefix="/auth/jwt",
    tags=["auth"],
)
{%- endif %}
{%- if cookiecutter.cookie_auth in [True, "True", "true", 1, "1"] %}
router.include_router(
    api_users.get_auth_router(auth_cookie),
    prefix="/auth/cookie",
    tags=["auth"],
)
{%- endif %}

__all__ = ["router"]
