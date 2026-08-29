"""
Deprecated compatibility shim.

Prefer ``{{cookiecutter.project_name}}.core.state`` for all new code.

This module intentionally contains no implementation. It only re-exports
the state-store interfaces and implementations so existing imports continue
to work during migration.
"""

from {{cookiecutter.project_name}}.core.state import (
    CounterStore,
    ExpiringStore,
    InMemoryCounterStore,
    InMemoryExpiringStore,
    InMemorySetStore,
    RedisCounterStore,
    RedisExpiringStore,
    RedisSetStore,
    SetStore,
    StateBackendUnavailable,
    StateNamespace,
    StateStoreError,
    StateStores,
    create_state_stores,
)

__all__ = [
    "CounterStore",
    "ExpiringStore",
    "InMemoryCounterStore",
    "InMemoryExpiringStore",
    "InMemorySetStore",
    "RedisCounterStore",
    "RedisExpiringStore",
    "RedisSetStore",
    "SetStore",
    "StateBackendUnavailable",
    "StateNamespace",
    "StateStoreError",
    "StateStores",
    "create_state_stores",
]