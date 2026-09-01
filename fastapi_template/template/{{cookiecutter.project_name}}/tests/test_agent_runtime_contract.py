"""Tests for bounded, restartable agent workflow execution."""

from __future__ import annotations

import pytest

from {{cookiecutter.project_name}}.agents.runtime import (
    BoundedRuntime,
    CancellationToken,
    InMemoryCheckpointStore,
    RuntimeCancelled,
    RuntimeStep,
)
from {{cookiecutter.project_name}}.platform.contracts import Scope, WorkflowState


def _scope() -> Scope:
    return Scope(principal_id="p1", organization_id="o1", run_id="r1")


async def test_runtime_runs_all_phases_and_checkpoints() -> None:
    seen: list[str] = []

    async def handler(state: WorkflowState, step: RuntimeStep) -> WorkflowState:
        seen.append(step.value)
        state.data["last_step"] = step.value
        return state

    checkpoints = InMemoryCheckpointStore()
    runtime = BoundedRuntime(
        scope=_scope(),
        handler=handler,
        checkpoints=checkpoints,
    )
    result = await runtime.run()

    assert result.status.value == "completed"
    assert seen == ["observe", "reason", "act", "verify"]
    restored = await checkpoints.load(str(result.workflow_id))
    assert restored is not None
    assert restored.data["last_step"] == "verify"


async def test_runtime_can_cancel_before_side_effect_phase() -> None:
    token = CancellationToken()
    token.cancel()

    async def handler(state: WorkflowState, step: RuntimeStep) -> WorkflowState:
        return state

    runtime = BoundedRuntime(
        scope=_scope(),
        handler=handler,
        cancellation=token,
    )

    with pytest.raises(RuntimeCancelled):
        await runtime.run()
