"""Deprecated — prefer ``core.state``."""

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
