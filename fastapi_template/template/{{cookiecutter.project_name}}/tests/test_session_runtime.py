"""Unit tests for append-only session runtime (P13)."""

from __future__ import annotations

from uuid import UUID

import pytest

from {{cookiecutter.project_name}}.agents.session_events import SessionEventKind
from {{cookiecutter.project_name}}.agents.session_runtime import SessionRuntime
from {{cookiecutter.project_name}}.agents.session_store import SessionEventStore
from {{cookiecutter.project_name}}.platform.contracts import Scope
from {{cookiecutter.project_name}}.platform.state import InMemoryStateStore


def _scope() -> Scope:
    return Scope(principal_id="user-1", organization_id="org-1")


@pytest.mark.asyncio
async def test_session_records_run_lifecycle() -> None:
    runtime = SessionRuntime(SessionEventStore(InMemoryStateStore()))
    scope = _scope()
    run_id, recorder = await runtime.start_run(
        scope,
        thread_id="thread-a",
        task="hello",
        runtime_mode="loop",
    )
    await recorder.context_built(task="hello", runtime_mode="loop")
    await recorder.model_called(step=1, tool_calls=0)
    await runtime.complete_run(
        scope,
        run_id,
        content="done",
        steps=1,
        workflow_id=UUID("00000000-0000-0000-0000-000000000001"),
    )

    events = await runtime.replay(scope, run_id)
    kinds = [event.kind for event in events]
    assert kinds[0] is SessionEventKind.RUN_STARTED
    assert SessionEventKind.CONTEXT_BUILT in kinds
    assert SessionEventKind.MODEL_CALLED in kinds
    assert kinds[-1] is SessionEventKind.RUN_COMPLETED


@pytest.mark.asyncio
async def test_session_fork_copies_events() -> None:
    runtime = SessionRuntime(SessionEventStore(InMemoryStateStore()))
    scope = _scope()
    run_id, recorder = await runtime.start_run(
        scope,
        thread_id="thread-b",
        task="fork me",
    )
    await recorder.tool_called(
        name="echo",
        arguments={"message": "hi"},
        output="hi",
        ok=True,
    )
    fork_id = await runtime.fork(scope, run_id)
    fork_events = await runtime.replay(scope, fork_id)
    assert len(fork_events) == 2
    assert all(event.run_id == fork_id for event in fork_events)


@pytest.mark.asyncio
async def test_session_resume_context() -> None:
    runtime = SessionRuntime(SessionEventStore(InMemoryStateStore()))
    scope = _scope()
    workflow_id = UUID("00000000-0000-0000-0000-000000000099")
    run_id, _ = await runtime.start_run(
        scope,
        thread_id="thread-c",
        task="resume task",
        runtime_mode="supervisor",
    )
    await runtime.complete_run(
        scope,
        run_id,
        content="ok",
        steps=2,
        workflow_id=workflow_id,
        runtime_mode="supervisor",
    )
    ctx = await runtime.resume_context(scope, run_id)
    assert ctx["thread_id"] == "thread-c"
    assert ctx["task"] == "resume task"
    assert ctx["resume_workflow_id"] == str(workflow_id)
    assert ctx["runtime_mode"] == "supervisor"
