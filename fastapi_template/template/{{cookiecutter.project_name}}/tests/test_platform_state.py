"""Tests for tenant-scoped state, checkpoints, and idempotency."""

from __future__ import annotations

from uuid import uuid4

import pytest

from {{cookiecutter.project_name}}.platform.contracts import Scope, WorkflowState
from {{cookiecutter.project_name}}.platform.state import (
    InMemoryStateStore,
    StateConflict,
    StateKey,
)


def _scope(org: str = "org-1") -> Scope:
    return Scope(principal_id="user-1", organization_id=org, project_id="p1")


async def test_state_isolation_and_optimistic_versions() -> None:
    store = InMemoryStateStore()
    key = StateKey(scope=_scope(), collection="working", item_id="item")

    first = await store.write(key, {"value": 1})
    second = await store.write(
        key,
        {"value": 2},
        expected_revision=first.revision,
    )

    assert second.revision == 2
    assert (await store.read(StateKey(
        scope=_scope("other-org"),
        collection="working",
        item_id="item",
    ))) is None
    with pytest.raises(StateConflict):
        await store.write(key, {"value": 3}, expected_revision=1)


async def test_checkpoint_resume_and_idempotency_claim() -> None:
    store = InMemoryStateStore()
    scope = _scope()
    state = WorkflowState(scope=scope)
    await store.save_checkpoint(state)

    restored = await store.load_checkpoint(scope, state.workflow_id)
    assert restored is not None
    assert restored.workflow_id == state.workflow_id
    assert await store.claim_idempotency(scope, "charge-1") is True
    assert await store.claim_idempotency(scope, "charge-1") is False
    assert await store.claim_idempotency(_scope("other-org"), "charge-1") is True

    assert await store.delete_scope(scope) >= 1
    assert await store.load_checkpoint(scope, uuid4()) is None
