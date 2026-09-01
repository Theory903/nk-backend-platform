"""Small provider-neutral dependency container for generated adapters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

T = TypeVar("T")
Factory = Callable[[], Any]


class DependencyError(RuntimeError):
    """Raised when a required platform dependency is not registered."""


@dataclass
class DependencyContainer:
    """Explicit registry used at composition boundaries."""

    _values: dict[type[Any], Any] = field(default_factory=dict)
    _factories: dict[type[Any], Factory] = field(default_factory=dict)

    def provide(self, contract: type[T], value: T) -> T:
        """Register a concrete implementation for a contract."""
        self._values[contract] = value
        self._factories.pop(contract, None)
        return value

    def factory(self, contract: type[T], builder: Factory) -> None:
        """Register a lazy implementation factory."""
        self._factories[contract] = builder

    def resolve(self, contract: type[T]) -> T:
        """Resolve one dependency, instantiating lazy providers once."""
        if contract in self._values:
            return self._values[contract]
        builder = self._factories.get(contract)
        if builder is None:
            raise DependencyError(f"no provider registered for {contract!r}")
        value = builder()
        self._values[contract] = value
        return value

    def has(self, contract: type[Any]) -> bool:
        """Return whether a concrete or lazy provider is registered."""
        return contract in self._values or contract in self._factories

    def clear(self) -> None:
        """Remove all registered providers."""
        self._values.clear()
        self._factories.clear()


__all__ = ["DependencyContainer", "DependencyError"]
