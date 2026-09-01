"""Durable access-token database used by FastAPI Users cookie auth."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime, String, Table, delete, select
from sqlalchemy.engine import Engine
from sqlalchemy import insert

from {{cookiecutter.project_name}}.identity.sql_stores import metadata


@dataclass(frozen=True, slots=True)
class AccessTokenRecord:
    token: str
    user_id: Any
    created_at: datetime


def _record_from_create_payload(access_token: Any) -> AccessTokenRecord:
    """Normalize FastAPI Users create dict or ORM objects into AccessTokenRecord."""
    if isinstance(access_token, AccessTokenRecord):
        return access_token
    if isinstance(access_token, dict):
        created_at = access_token.get("created_at")
        if created_at is None:
            created_at = datetime.now(UTC)
        elif not isinstance(created_at, datetime):
            created_at = datetime.fromtimestamp(float(created_at), tz=UTC)
        return AccessTokenRecord(
            token=str(access_token["token"]),
            user_id=access_token["user_id"],
            created_at=created_at,
        )
    return AccessTokenRecord(
        token=str(access_token.token),
        user_id=access_token.user_id,
        created_at=access_token.created_at,
    )


auth_access_tokens = Table(
    "auth_access_token",
    metadata,
    Column("token_digest", String(64), primary_key=True),
    Column("user_id", String(255), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


class SqlAlchemyAccessTokenStore:
    """Synchronous SQL adapter implementing FastAPI Users' token database."""

    def __init__(self, engine: Engine, *, secret: str) -> None:
        if not secret:
            raise ValueError("access-token digest secret is required")
        self._engine = engine
        self._secret = secret.encode("utf-8")

    async def create(self, access_token: Any) -> AccessTokenRecord:
        return await asyncio.to_thread(self.create_sync, access_token)

    def create_sync(self, access_token: Any) -> AccessTokenRecord:
        record = _record_from_create_payload(access_token)
        with self._engine.begin() as connection:
            connection.execute(
                insert(auth_access_tokens).values(
                    token_digest=self._digest(record.token),
                    user_id=str(record.user_id),
                    created_at=record.created_at,
                ),
            )
        return record

    async def get(self, token: str) -> AccessTokenRecord | None:
        return await asyncio.to_thread(self.get_sync, token)

    def get_sync(self, token: str) -> AccessTokenRecord | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(auth_access_tokens).where(
                    auth_access_tokens.c.token_digest == self._digest(token),
                ),
            ).mappings().first()
        if not row:
            return None
        return self._decode(dict(row), token=token)

    async def delete(self, token: str) -> None:
        await asyncio.to_thread(self.delete_sync, token)

    def delete_sync(self, token: str) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                delete(auth_access_tokens).where(
                    auth_access_tokens.c.token_digest == self._digest(token),
                ),
            )

    def _digest(self, token: str) -> str:
        return hmac.new(
            self._secret,
            token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _decode(
        data: dict[str, Any],
        *,
        token: str,
    ) -> AccessTokenRecord:
        user_id: Any = data["user_id"]
        try:
            user_id = uuid.UUID(str(user_id))
        except (ValueError, TypeError, AttributeError):
            pass
        created_at = data["created_at"]
        if not isinstance(created_at, datetime):
            created_at = datetime.fromtimestamp(float(created_at), tz=UTC)
        return AccessTokenRecord(
            token=token,
            user_id=user_id,
            created_at=created_at,
        )


class RedisAccessTokenStore:
    """Redis adapter implementing FastAPI Users' token database."""

    def __init__(
        self,
        redis: Any,
        *,
        prefix: str = "nk:access-token",
        lifetime_seconds: int = 3600,
        secret: str,
    ) -> None:
        if not secret:
            raise ValueError("access-token digest secret is required")
        self._redis = redis
        self._prefix = prefix.rstrip(":")
        self._lifetime_seconds = lifetime_seconds
        self._secret = secret.encode("utf-8")

    def _key(self, token: str) -> str:
        digest = hmac.new(
            self._secret,
            token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{self._prefix}:{digest}"

    async def create(self, access_token: Any) -> AccessTokenRecord:
        return await asyncio.to_thread(self.create_sync, access_token)

    def create_sync(self, access_token: Any) -> AccessTokenRecord:
        record = _record_from_create_payload(access_token)
        self._redis.set(
            self._key(record.token),
            json.dumps(
                {
                    "user_id": str(record.user_id),
                    "created_at": record.created_at.timestamp(),
                },
            ),
            ex=max(
                1,
                int(
                    self._lifetime_seconds
                    - (time.time() - record.created_at.timestamp())
                ),
            ),
        )
        return record

    async def get(self, token: str) -> AccessTokenRecord | None:
        return await asyncio.to_thread(self.get_sync, token)

    def get_sync(self, token: str) -> AccessTokenRecord | None:
        raw = self._redis.get(self._key(token))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return SqlAlchemyAccessTokenStore._decode(
            json.loads(raw),
            token=token,
        )

    async def delete(self, token: str) -> None:
        await asyncio.to_thread(self._redis.delete, self._key(token))


class InMemoryAccessTokenStore:
    """Development-only access-token database."""

    def __init__(self) -> None:
        self._tokens: dict[str, AccessTokenRecord] = {}

    async def create(self, create_dict: dict[str, Any]) -> AccessTokenRecord:
        record = _record_from_create_payload(create_dict)
        self._tokens[record.token] = record
        return record

    async def get_by_token(
        self,
        token: str,
        max_age: datetime | None = None,
    ) -> AccessTokenRecord | None:
        record = self._tokens.get(token)
        if record is None:
            return None
        if max_age is not None and record.created_at < max_age:
            return None
        return record

    async def update(
        self,
        access_token: AccessTokenRecord,
        update_dict: dict[str, Any],
    ) -> AccessTokenRecord:
        updated = AccessTokenRecord(
            token=access_token.token,
            user_id=update_dict.get("user_id", access_token.user_id),
            created_at=update_dict.get("created_at", access_token.created_at),
        )
        self._tokens[updated.token] = updated
        return updated

    async def delete(self, access_token: AccessTokenRecord) -> None:
        self._tokens.pop(access_token.token, None)

    async def get(self, token: str) -> AccessTokenRecord | None:
        return self.get_sync(token)

    def get_sync(self, token: str) -> AccessTokenRecord | None:
        return self._tokens.get(token)


__all__ = [
    "AccessTokenRecord",
    "InMemoryAccessTokenStore",
    "RedisAccessTokenStore",
    "SqlAlchemyAccessTokenStore",
    "auth_access_tokens",
]
