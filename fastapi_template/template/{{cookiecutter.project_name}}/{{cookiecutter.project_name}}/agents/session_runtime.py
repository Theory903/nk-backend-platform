"""Session runtime: append-only events, inspect, fork, replay, resume (P13)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from {{cookiecutter.project_name}}.agents.session_events import (
    RunMeta,
    SessionEvent,
    SessionEventKind,
)
from {{cookiecutter.project_name}}.agents.session_store import SessionEventStore
from {{cookiecutter.project_name}}.platform.contracts import Scope


class SessionRecorder:
    """Bound recorder for a single in-flight run."""

    __slots__ = ("_runtime", "_scope", "_run_id", "_thread_id", "_sequence")

    def __init__(
        self,
        runtime: SessionRuntime,
        scope: Scope,
        run_id: UUID,
        thread_id: str,
    ) -> None:
        self._runtime = runtime
        self._scope = scope
        self._run_id = run_id
        self._thread_id = thread_id
        self._sequence = 0

    async def _emit(
        self,
        kind: SessionEventKind,
        payload: dict[str, Any],
    ) -> None:
        event = SessionEvent(
            run_id=self._run_id,
            thread_id=self._thread_id,
            sequence=self._sequence,
            kind=kind,
            payload=payload,
        )
        self._sequence += 1
        await self._runtime.emit(self._scope, event)

    async def context_built(self, *, task: str, runtime_mode: str) -> None:
        await self._emit(
            SessionEventKind.CONTEXT_BUILT,
            {"task": task, "runtime_mode": runtime_mode},
        )

    async def model_called(
        self,
        *,
        step: int,
        tool_calls: int = 0,
    ) -> None:
        await self._emit(
            SessionEventKind.MODEL_CALLED,
            {"step": step, "tool_calls": tool_calls},
        )

    async def tool_called(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        output: str,
        ok: bool,
    ) -> None:
        await self._emit(
            SessionEventKind.TOOL_CALLED,
            {
                "name": name,
                "arguments": arguments,
                "output": output,
                "ok": ok,
            },
        )

    async def approval_requested(self, *, tool_name: str) -> None:
        await self._emit(
            SessionEventKind.APPROVAL_REQUESTED,
            {"tool": tool_name},
        )


class SessionRuntime:
    """High-level session operations over the append-only event store."""

    __slots__ = ("_store",)

    def __init__(self, store: SessionEventStore) -> None:
        self._store = store

    async def emit(self, scope: Scope, event: SessionEvent) -> None:
        await self._store.append(scope, event)

    def bind(
        self,
        scope: Scope,
        run_id: UUID,
        thread_id: str,
    ) -> SessionRecorder:
        return SessionRecorder(self, scope, run_id, thread_id)

    async def start_run(
        self,
        scope: Scope,
        *,
        thread_id: str,
        task: str,
        runtime_mode: str = "auto",
        parent_run_id: UUID | None = None,
        forked_from_sequence: int | None = None,
    ) -> tuple[UUID, SessionRecorder]:
        run_id = uuid4()
        meta = RunMeta(
            run_id=run_id,
            thread_id=thread_id,
            principal_id=scope.principal_id,
            organization_id=scope.organization_id,
            task=task,
            parent_run_id=parent_run_id,
            forked_from_sequence=forked_from_sequence,
        )
        await self._store.save_run_meta(scope, meta)
        recorder = self.bind(scope, run_id, thread_id)
        await recorder._emit(
            SessionEventKind.RUN_STARTED,
            {
                "task": task,
                "runtime_mode": runtime_mode,
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
            },
        )
        return run_id, recorder

    async def complete_run(
        self,
        scope: Scope,
        run_id: UUID,
        *,
        content: str,
        steps: int,
        workflow_id: UUID | None = None,
        runtime_mode: str | None = None,
    ) -> None:
        meta = await self._store.load_run_meta(scope, run_id)
        if meta is not None:
            await self._store.save_run_meta(
                scope,
                meta.model_copy(
                    update={
                        "status": "completed",
                        "workflow_id": workflow_id,
                        "updated_at": datetime.now(timezone.utc),
                    },
                ),
            )
        recorder = self.bind(scope, run_id, meta.thread_id if meta else "")
        events = await self._store.list_events(scope, run_id)
        recorder._sequence = len(events)
        await recorder._emit(
            SessionEventKind.RUN_COMPLETED,
            {
                "content": content,
                "steps": steps,
                "workflow_id": str(workflow_id) if workflow_id else None,
                "runtime_mode": runtime_mode,
            },
        )

    async def fail_run(
        self,
        scope: Scope,
        run_id: UUID,
        *,
        error: str,
        thread_id: str,
    ) -> None:
        meta = await self._store.load_run_meta(scope, run_id)
        if meta is not None:
            await self._store.save_run_meta(
                scope,
                meta.model_copy(
                    update={
                        "status": "failed",
                        "updated_at": datetime.now(timezone.utc),
                    },
                ),
            )
        recorder = self.bind(scope, run_id, thread_id)
        events = await self._store.list_events(scope, run_id)
        recorder._sequence = len(events)
        await recorder._emit(SessionEventKind.RUN_FAILED, {"error": error})

    async def inspect(
        self,
        scope: Scope,
        run_id: UUID,
    ) -> dict[str, Any]:
        meta = await self._store.load_run_meta(scope, run_id)
        events = await self._store.list_events(scope, run_id)
        return {
            "run_id": str(run_id),
            "meta": meta.model_dump(mode="json") if meta else None,
            "events": [event.model_dump(mode="json") for event in events],
            "event_count": len(events),
        }

    async def replay(
        self,
        scope: Scope,
        run_id: UUID,
    ) -> list[SessionEvent]:
        """Return the append-only event stream for read-only replay."""
        return await self._store.list_events(scope, run_id)

    async def fork(
        self,
        scope: Scope,
        run_id: UUID,
        *,
        through_sequence: int | None = None,
    ) -> UUID:
        """Fork a run by copying events up to an optional sequence boundary."""
        source_events = await self._store.list_events(scope, run_id)
        if not source_events:
            raise ValueError(f"run {run_id} has no events to fork")
        if through_sequence is not None:
            source_events = [
                event
                for event in source_events
                if event.sequence <= through_sequence
            ]
        source_meta = await self._store.load_run_meta(scope, run_id)
        thread_id = source_meta.thread_id if source_meta else source_events[0].thread_id
        task = source_meta.task if source_meta else str(
            source_events[0].payload.get("task", ""),
        )
        new_run_id = uuid4()
        meta = RunMeta(
            run_id=new_run_id,
            thread_id=thread_id,
            principal_id=scope.principal_id,
            organization_id=scope.organization_id,
            task=task,
            parent_run_id=run_id,
            forked_from_sequence=through_sequence,
        )
        await self._store.save_run_meta(scope, meta)
        for index, event in enumerate(source_events):
            copied = event.model_copy(
                update={
                    "run_id": new_run_id,
                    "sequence": index,
                    "event_id": uuid4(),
                    "timestamp": datetime.now(timezone.utc),
                },
            )
            await self._store.append(scope, copied)
        return new_run_id

    async def resume_context(
        self,
        scope: Scope,
        run_id: UUID,
    ) -> dict[str, Any]:
        """Build resume hints from the event stream and run metadata."""
        meta = await self._store.load_run_meta(scope, run_id)
        events = await self._store.list_events(scope, run_id)
        if meta is None and not events:
            raise ValueError(f"run {run_id} not found")
        task = meta.task if meta else ""
        thread_id = meta.thread_id if meta else ""
        workflow_id = meta.workflow_id if meta else None
        runtime_mode = "auto"
        for event in events:
            if event.kind is SessionEventKind.RUN_STARTED:
                task = str(event.payload.get("task", task))
                runtime_mode = str(event.payload.get("runtime_mode", runtime_mode))
            if event.kind is SessionEventKind.RUN_COMPLETED:
                wf = event.payload.get("workflow_id")
                if wf:
                    workflow_id = UUID(str(wf))
        return {
            "run_id": str(run_id),
            "thread_id": thread_id,
            "task": task,
            "runtime_mode": runtime_mode,
            "resume_workflow_id": str(workflow_id) if workflow_id else None,
            "status": meta.status if meta else "unknown",
        }


__all__ = ["SessionRecorder", "SessionRuntime"]
