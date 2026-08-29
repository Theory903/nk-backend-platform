"""Deprecated identity store shim — prefer ``core.state``.

Thin re-exports so existing identity imports keep working while
``core.state`` remains the canonical async state primitives layer.
"""

from {{cookiecutter.project_name}}.core.state import (
    CounterStore,
    ExpiringStore,
    InMemoryCounterStore,
    InMemoryExpiringStore,
    InMemorySetStore,
    SetStore,
)

__all__ = [
    "CounterStore",
    "ExpiringStore",
    "InMemoryCounterStore",
    "InMemoryExpiringStore",
    "InMemorySetStore",
    "SetStore",
]
