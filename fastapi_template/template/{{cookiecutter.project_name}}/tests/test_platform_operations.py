"""Tests for release registry, reproducibility, and failure handling."""

from __future__ import annotations

import asyncio

import pytest

from {{cookiecutter.project_name}}.operations.reliability import (
    FailureClass,
    RetryPolicy,
    classify_failure,
    retry_async,
)
from {{cookiecutter.project_name}}.platform.control_plane import (
    ControlPlaneRegistry,
    RegistryEntry,
)
from {{cookiecutter.project_name}}.platform.reproducibility import (
    ReproducibilityManifest,
)


def test_control_plane_activation_is_versioned() -> None:
    registry = ControlPlaneRegistry()
    registry.register(RegistryEntry("model", "v1", "model", active=True))
    registry.register(RegistryEntry("model", "v2", "model"))

    assert registry.active("model", "model").version == "v1"
    registry.activate("model", "model", "v2")
    assert registry.active("model", "model").version == "v2"


def test_reproducibility_fingerprint_changes_with_model_version() -> None:
    first = ReproducibilityManifest.from_inputs(
        config={"config_version": "1"},
        lockfile="lock",
        model_versions={"answer": "v1"},
    )
    second = ReproducibilityManifest.from_inputs(
        config={"config_version": "1"},
        lockfile="lock",
        model_versions={"answer": "v2"},
    )

    assert first.fingerprint() != second.fingerprint()


async def test_retry_is_bounded_and_classifies_failures() -> None:
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("temporarily unavailable")
        return "ok"

    result = await retry_async(
        operation,
        policy=RetryPolicy(attempts=3, base_delay_s=0, max_delay_s=0),
    )

    assert result == "ok"
    assert attempts == 3
    assert classify_failure(TimeoutError()) is FailureClass.TRANSIENT
    with pytest.raises(ValueError):
        await retry_async(
            lambda: asyncio.sleep(0, result=None),
            policy=RetryPolicy(attempts=0),
        )
