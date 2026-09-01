from typing import AsyncGenerator
import uuid

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, schemas
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,

    CookieTransport,
    JWTStrategy,
)
from fastapi_users.authentication.strategy.db import DatabaseStrategy
from fastapi_users.db import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.db.base import Base
from {{cookiecutter.project_name}}.db.dependencies import get_db_session
from {{cookiecutter.project_name}}.settings import settings


class User(SQLAlchemyBaseUserTableUUID, Base):
    """Represents a user entity."""


class UserRead(schemas.BaseUser[uuid.UUID]):
    """Represents a read command for a user."""


class UserCreate(schemas.BaseUserCreate):
    """Represents a create command for a user."""


class UserUpdate(schemas.BaseUserUpdate):
    """Represents an update command for a user."""


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """Manages a user session and its tokens."""
    reset_password_token_secret = settings.users_secret
    verification_token_secret = settings.users_secret


async def get_user_db(session: AsyncSession = Depends(get_db_session)) -> AsyncGenerator[SQLAlchemyUserDatabase[User, uuid.UUID], None]:
    """
    Yield a SQLAlchemyUserDatabase instance.

    :param session: asynchronous SQLAlchemy session.
    :yields: instance of SQLAlchemyUserDatabase.
    """
    yield SQLAlchemyUserDatabase(session, User)


async def get_user_manager(user_db: SQLAlchemyUserDatabase[User, uuid.UUID] = Depends(get_user_db)) -> AsyncGenerator[UserManager, None]:
    """
    Yield a UserManager instance.

    :param user_db: SQLAlchemy user db instance
    :yields: an instance of UserManager.
    """
    yield UserManager(user_db)


def get_jwt_strategy() -> JWTStrategy[User, uuid.UUID]:
    """
    Return a JWTStrategy in order to instantiate it dynamically.

    :returns: instance of JWTStrategy with provided settings.
    """
    return JWTStrategy(
        secret=settings.users_secret,
        lifetime_seconds=settings.auth_token_ttl_seconds,
    )


async def get_access_token_db(request: Request):
    """Resolve the startup-configured durable cookie-token store."""
    store = getattr(request.app.state, "access_token_store", None)
    if store is None:
        raise RuntimeError("durable access-token store is not configured")
    return store


def get_cookie_strategy(
    access_token_db=Depends(get_access_token_db),
) -> DatabaseStrategy:
    return DatabaseStrategy(
        access_token_db,
        lifetime_seconds=settings.session_cookie_max_age_seconds,
    )


{%- if cookiecutter.jwt_auth in [True, "True", "true", 1, "1"] %}
bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")
auth_jwt = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)
{%- endif %}

{%- if cookiecutter.cookie_auth in [True, "True", "true", 1, "1"] %}
cookie_transport = CookieTransport(
    cookie_name="auth_session",
    cookie_max_age=settings.session_cookie_max_age_seconds,
    cookie_secure=settings.secure_cookies,
    cookie_httponly=True,
    cookie_samesite="lax",
)
auth_cookie = AuthenticationBackend(
    name="cookie", transport=cookie_transport, get_strategy=get_cookie_strategy
)
{%- endif %}

backends: list[AuthenticationBackend] = [
    {%- if cookiecutter.cookie_auth in [True, "True", "true", 1, "1"] %}
    auth_cookie,
    {%- endif %}
    {%- if cookiecutter.jwt_auth in [True, "True", "true", 1, "1"] %}
    auth_jwt,
    {%- endif %}
]

api_users = FastAPIUsers[User, uuid.UUID](get_user_manager, backends)

current_active_user = api_users.current_user(active=True)
