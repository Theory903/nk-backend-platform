"""Durable append-only session event storage (P13)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from {{cookiecutter.project_name}}.agents.session_events import RunMeta, SessionEvent
from {{cookiecutter.project_name}}.platform.contracts import Scope
from {{cookiecutter.project_name}}.platform.state import StateKey, StateStore


class SessionEventStore:
    """Tenant-scoped event log backed by the platform StateStore."""

    __slots__ = ("_store",)

    def __init__(self, store: StateStore) -> None:
        self._store = store

    async def append(self, scope: Scope, event: SessionEvent) -> SessionEvent:
        key = StateKey(scope, "session_events", str(event.run_id))
        existing = await self._store.read(key)
        events = list(existing.value) if existing is not None else []
        events.append(event.model_dump(mode="json"))
        await self._store.write(
            key,
            events,
            expected_revision=existing.revision if existing else None,
        )
        return event

    async def list_events(self, scope: Scope, run_id: UUID) -> list[SessionEvent]:
        key = StateKey(scope, "session_events", str(run_id))
        stored = await self._store.read(key)
        if stored is None:
            return []
        raw = stored.value
        if not isinstance(raw, list):
            return []
        return [SessionEvent.model_validate(item) for item in raw]

    async def save_run_meta(self, scope: Scope, meta: RunMeta) -> RunMeta:
        key = StateKey(scope, "session_runs", str(meta.run_id))
        updated = meta.model_copy(
            update={"updated_at": datetime.now(timezone.utc)},
        )
        existing = await self._store.read(key)
        await self._store.write(
            key,
            updated.model_dump(mode="json"),
            expected_revision=existing.revision if existing else None,
        )
        await self._index_thread_run(scope, meta.thread_id, meta.run_id)
        return updated

    async def load_run_meta(self, scope: Scope, run_id: UUID) -> RunMeta | None:
        key = StateKey(scope, "session_runs", str(run_id))
        stored = await self._store.read(key)
        if stored is None:
            return None
        return RunMeta.model_validate(stored.value)

    async def list_thread_runs(
        self,
        scope: Scope,
        thread_id: str,
    ) -> list[RunMeta]:
        index_key = StateKey(scope, "session_threads", thread_id)
        stored = await self._store.read(index_key)
        if stored is None or not isinstance(stored.value, list):
            return []
        runs: list[RunMeta] = []
        for run_id in stored.value:
            meta = await self.load_run_meta(scope, UUID(str(run_id)))
            if meta is not None:
                runs.append(meta)
        return runs

    async def _index_thread_run(
        self,
        scope: Scope,
        thread_id: str,
        run_id: UUID,
    ) -> None:
        index_key = StateKey(scope, "session_threads", thread_id)
        existing = await self._store.read(index_key)
        run_ids = list(existing.value) if existing is not None else []
        run_id_str = str(run_id)
        if run_id_str not in run_ids:
            run_ids.append(run_id_str)
        await self._store.write(
            index_key,
            run_ids,
            expected_revision=existing.revision if existing else None,
        )


__all__ = ["SessionEventStore"]
