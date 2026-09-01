"""Tenant-scoped state contracts and restart-safe development adapters."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

from {{cookiecutter.project_name}}.platform.contracts import (
    CacheKey,
    MemoryKind,
    MemoryRecord,
    Scope,
    WorkflowState,
)


@dataclass(frozen=True, slots=True)
class StateKey:
    """Storage key that cannot be constructed without tenant identity."""

    scope: Scope
    collection: str
    item_id: str

    def value(self) -> str:
        return f"{self.scope.namespace(self.collection)}:{self.item_id}"


@dataclass(frozen=True, slots=True)
class VersionedValue:
    """Optimistically versioned value stored under a tenant namespace."""

    key: StateKey
    value: Any
    revision: int = 1
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class StateConflict(RuntimeError):
    """Raised when a stale revision attempts to overwrite state."""


class StateStore(Protocol):
    async def read(self, key: StateKey) -> VersionedValue | None: ...

    async def write(
        self,
        key: StateKey,
        value: Any,
        *,
        expected_revision: int | None = None,
    ) -> VersionedValue: ...

    async def delete(self, key: StateKey) -> bool: ...

    async def delete_scope(self, scope: Scope) -> int: ...

    async def claim_idempotency(self, scope: Scope, key: str) -> bool: ...


class InMemoryStateStore:
    """Deterministic adapter for tests and local development."""

    def __init__(self) -> None:
        self._values: dict[str, VersionedValue] = {}
        self._claims: set[str] = set()

    async def read(self, key: StateKey) -> VersionedValue | None:
        value = self._values.get(key.value())
        return value

    async def write(
        self,
        key: StateKey,
        value: Any,
        *,
        expected_revision: int | None = None,
    ) -> VersionedValue:
        existing = self._values.get(key.value())
        if (
            expected_revision is not None
            and (existing is None or existing.revision != expected_revision)
        ):
            raise StateConflict(f"stale state revision for {key.value()}")
        revision = existing.revision + 1 if existing else 1
        stored = VersionedValue(key=key, value=value, revision=revision)
        self._values[key.value()] = stored
        return stored

    async def delete(self, key: StateKey) -> bool:
        return self._values.pop(key.value(), None) is not None

    async def delete_scope(self, scope: Scope) -> int:
        prefix = scope.namespace("")
        matching = [
            key
            for key, value in self._values.items()
            if value.key.scope == scope or key.startswith(prefix)
        ]
        for key in matching:
            self._values.pop(key, None)
        claim_prefix = scope.namespace("idempotency")
        self._claims = {
            claim for claim in self._claims if not claim.startswith(claim_prefix)
        }
        return len(matching)

    async def claim_idempotency(self, scope: Scope, key: str) -> bool:
        """Atomically claim a side-effect key within one tenant."""
        claim = f"{scope.namespace('idempotency')}:{key}"
        if claim in self._claims:
            return False
        self._claims.add(claim)
        return True

    async def save_checkpoint(self, state: WorkflowState) -> None:
        key = StateKey(
            scope=state.scope,
            collection="checkpoints",
            item_id=str(state.workflow_id),
        )
        existing = await self.read(key)
        await self.write(
            key,
            state.model_dump(mode="json"),
            expected_revision=existing.revision if existing else None,
        )

    async def load_checkpoint(
        self,
        scope: Scope,
        workflow_id: UUID,
    ) -> WorkflowState | None:
        key = StateKey(scope=scope, collection="checkpoints", item_id=str(workflow_id))
        stored = await self.read(key)
        return WorkflowState.model_validate(stored.value) if stored else None

    async def put_memory(self, record: MemoryRecord) -> MemoryRecord:
        key = StateKey(
            scope=record.scope,
            collection=f"memory:{record.kind.value}",
            item_id=str(record.memory_id),
        )
        await self.write(key, record.model_dump(mode="json"), expected_revision=(
            record.version - 1 if record.version > 1 else None
        ))
        return record

    async def list_memory(
        self,
        scope: Scope,
        kind: MemoryKind,
        *,
        limit: int = 50,
    ) -> list[MemoryRecord]:
        prefix = scope.namespace(f"memory:{kind.value}")
        records = [
            MemoryRecord.model_validate(value.value)
            for key, value in self._values.items()
            if key.startswith(prefix)
        ]
        return records[-limit:]

    async def cache_get(self, key: CacheKey) -> str | None:
        scope_key = StateKey(
            scope=Scope(
                principal_id="_cache",
                organization_id=key.namespace,
            ),
            collection="cache",
            item_id=key.value(),
        )
        stored = await self.read(scope_key)
        return stored.value if stored is not None else None

    async def cache_put(self, key: CacheKey, value: str) -> None:
        scope_key = StateKey(
            scope=Scope(
                principal_id="_cache",
                organization_id=key.namespace,
            ),
            collection="cache",
            item_id=key.value(),
        )
        await self.write(scope_key, value)


class RedisStateStore:
    """Durable tenant-scoped state using an async Redis client."""

    def __init__(self, redis_client: Any, *, prefix: str = "nk:state") -> None:
        self._redis = redis_client
        self._prefix = prefix.rstrip(":")

    def _key(self, key: StateKey) -> str:
        return f"{self._prefix}:{key.value()}"

    async def read(self, key: StateKey) -> VersionedValue | None:
        raw = await self._redis.get(self._key(key))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        return VersionedValue(
            key=key,
            value=data["value"],
            revision=int(data["revision"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )

    async def write(
        self,
        key: StateKey,
        value: Any,
        *,
        expected_revision: int | None = None,
    ) -> VersionedValue:
        redis_key = self._key(key)
        pipeline_factory = getattr(self._redis, "pipeline", None)
        if not callable(pipeline_factory):
            raise RuntimeError("Redis state writes require transactional pipeline support")

        for _ in range(5):
            pipe = pipeline_factory()
            try:
                await pipe.watch(redis_key)
                raw = await pipe.get(redis_key)
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                existing = (
                    json.loads(raw)
                    if raw is not None
                    else None
                )
                existing_revision = (
                    int(existing["revision"]) if existing is not None else None
                )
                if expected_revision is not None and (
                    existing_revision != expected_revision
                ):
                    raise StateConflict(f"stale state revision for {key.value()}")
                stored = VersionedValue(
                    key=key,
                    value=value,
                    revision=(existing_revision or 0) + 1,
                )
                pipe.multi()
                pipe.set(
                    redis_key,
                    json.dumps({
                        "value": stored.value,
                        "revision": stored.revision,
                        "updated_at": stored.updated_at.isoformat(),
                    }),
                )
                result = await pipe.execute()
                if result is not None:
                    return stored
            except Exception as exc:
                if type(exc).__name__ != "WatchError":
                    raise
            finally:
                reset = getattr(pipe, "reset", None)
                if callable(reset):
                    await reset()
        raise StateConflict(f"concurrent state writes for {key.value()}")

    async def delete(self, key: StateKey) -> bool:
        return bool(await self._redis.delete(self._key(key)))

    async def delete_scope(self, scope: Scope) -> int:
        count = 0
        pattern = f"{self._prefix}:{scope.namespace('').rstrip(':')}:*"
        async for raw_key in self._redis.scan_iter(match=pattern):
            count += int(await self._redis.delete(raw_key))
        return count

    async def claim_idempotency(self, scope: Scope, key: str) -> bool:
        """Atomically claim an idempotency key using Redis SET NX."""
        claim_key = f"{self._prefix}:{scope.namespace('idempotency')}:{key}"
        return bool(await self._redis.set(claim_key, "1", nx=True))

    async def save_checkpoint(self, state: WorkflowState) -> None:
        key = StateKey(state.scope, "checkpoints", str(state.workflow_id))
        existing = await self.read(key)
        await self.write(
            key,
            state.model_dump(mode="json"),
            expected_revision=existing.revision if existing else None,
        )

    async def load_checkpoint(self, scope: Scope, workflow_id: UUID) -> WorkflowState | None:
        stored = await self.read(StateKey(scope, "checkpoints", str(workflow_id)))
        return WorkflowState.model_validate(stored.value) if stored else None

    async def cache_get(self, key: CacheKey) -> str | None:
        value = await self._redis.get(f"{self._prefix}:cache:{key.value()}")
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value

    async def cache_put(self, key: CacheKey, value: str, *, ttl_s: int = 300) -> None:
        await self._redis.set(
            f"{self._prefix}:cache:{key.value()}",
            value,
            ex=ttl_s,
        )


__all__ = [
    "InMemoryStateStore",
    "RedisStateStore",
    "StateConflict",
    "StateKey",
    "StateStore",
    "VersionedValue",
]
