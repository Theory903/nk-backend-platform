"""Production dependency-injection container.

Supports:
- singleton, scoped and transient lifetimes
- lazy construction
- sync/async factories
- dependency injection through type annotations
- class factories (constructor injection)
- overrides for tests
- child scopes
- deterministic cleanup
- thread-safe singleton construction
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from dataclasses import dataclass, field
from enum import StrEnum
from threading import RLock
from types import TracebackType
from typing import Any, Generic, TypeVar, get_type_hints

T = TypeVar("T")


class ServiceLifetime(StrEnum):
    SINGLETON = "singleton"
    SCOPED = "scoped"
    TRANSIENT = "transient"


class DependencyError(RuntimeError):
    """Base dependency-injection error."""


class ServiceNotRegisteredError(DependencyError):
    """Requested service has not been registered."""


class CircularDependencyError(DependencyError):
    """Dependency graph contains a cycle."""


class AsyncResolutionError(DependencyError):
    """A synchronous resolver encountered an async dependency."""


class ScopeRequiredError(DependencyError):
    """A scoped service was resolved outside an active scope."""


class ContainerClosedError(DependencyError):
    """Operations attempted on a closed container."""


@dataclass(frozen=True, slots=True)
class ServiceDescriptor(Generic[T]):
    """Registration metadata for a service."""

    factory: Callable[..., T]
    lifetime: ServiceLifetime = ServiceLifetime.SINGLETON
    name: str | None = None


@dataclass
class _CleanupError(Exception):
    """Aggregates cleanup failures."""

    errors: list[BaseException] = field(default_factory=list)

    def __str__(self) -> str:
        return f"{len(self.errors)} cleanup error(s): {self.errors!r}"


class Container:
    """
    Dependency-injection container.

    The root container owns SINGLETON services.
    A child scope owns SCOPED services.
    TRANSIENT services are constructed for every resolution.

    Example:

        container = Container()

        container.register(Database, Database)

        container.register(
            UserService,
            UserService,
            lifetime=ServiceLifetime.SCOPED,
        )

        async with container.scope() as scope:
            service = await scope.aget(UserService)
    """

    def __init__(
        self,
        *,
        parent: Container | None = None,
    ) -> None:
        self._parent = parent
        self._descriptors: dict[Any, ServiceDescriptor[Any]] = {}
        self._instances: dict[Any, Any] = {}
        self._overrides: dict[Any, Any] = {}
        self._inflight: dict[Any, asyncio.Future[Any]] = {}
        self._closed = False
        self._lock = RLock()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        service: Any,
        factory: Callable[..., Any],
        *,
        lifetime: ServiceLifetime = ServiceLifetime.SINGLETON,
        name: str | None = None,
    ) -> None:
        """Register or replace a service factory."""
        self._ensure_open()
        descriptor = ServiceDescriptor(
            factory=factory,
            lifetime=lifetime,
            name=name,
        )
        key = self._key(service, name)

        with self._lock:
            self._descriptors[key] = descriptor
            self._instances.pop(key, None)
            self._overrides.pop(key, None)

    def unregister(
        self,
        service: Any,
        *,
        name: str | None = None,
    ) -> None:
        """Remove a registration and its cached instance."""
        key = self._key(service, name)

        with self._lock:
            instance = self._instances.pop(key, None)
            self._overrides.pop(key, None)
            self._descriptors.pop(key, None)

        if instance is not None:
            self._close_sync(instance)

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def get(
        self,
        service: type[T] | Any,
        *,
        name: str | None = None,
    ) -> T:
        """
        Resolve a service synchronously.

        Raises AsyncResolutionError if construction requires awaiting.
        """
        self._ensure_open()
        return self._resolve(service, name=name, stack=[])

    async def aget(
        self,
        service: type[T] | Any,
        *,
        name: str | None = None,
    ) -> T:
        """Resolve a service asynchronously."""
        self._ensure_open()
        return await self._aresolve(service, name=name, stack=[])

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    def override(
        self,
        service: Any,
        instance: Any,
        *,
        name: str | None = None,
        lifetime: ServiceLifetime = ServiceLifetime.SINGLETON,
    ) -> None:
        """
        Replace a service instance for all subsequent resolutions.

        Primarily useful for tests and application bootstrapping.
        Honored for singleton, scoped, and transient lifetimes.
        """
        self._ensure_open()
        key = self._key(service, name)

        with self._lock:
            if key not in self._descriptors:
                self._descriptors[key] = ServiceDescriptor(
                    factory=lambda: instance,
                    lifetime=lifetime,
                    name=name,
                )
            old = self._instances.get(key)
            self._overrides[key] = instance
            self._instances[key] = instance

        if old is not None and old is not instance:
            self._close_sync(old)

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def has(
        self,
        service: Any,
        *,
        name: str | None = None,
    ) -> bool:
        """Return whether a service is registered."""
        key = self._key(service, name)
        if key in self._descriptors:
            return True
        return self._parent is not None and self._parent.has(service, name=name)

    def describe(self) -> dict[str, str]:
        """Return registered services and lifetimes."""
        result: dict[str, str] = {}

        if self._parent is not None:
            result.update(self._parent.describe())

        for key, descriptor in self._descriptors.items():
            result[self._display_key(key)] = descriptor.lifetime.value

        return result

    # ------------------------------------------------------------------
    # Scopes
    # ------------------------------------------------------------------

    def scope(self) -> ContainerScope:
        """Create a child dependency scope."""
        self._ensure_open()
        return ContainerScope(Container(parent=self))

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def aclose(self) -> None:
        """Close all locally owned service instances."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            instances = list(self._instances.values())
            self._instances.clear()
            self._overrides.clear()

        errors: list[BaseException] = []
        for instance in reversed(instances):
            try:
                await self._close_async(instance)
            except BaseException as exc:  # noqa: BLE001 — aggregate cleanup
                errors.append(exc)

        if errors:
            raise _CleanupError(errors)

    def close(self) -> None:
        """Synchronous shutdown."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            instances = list(self._instances.values())
            self._instances.clear()
            self._overrides.clear()

        errors: list[BaseException] = []
        for instance in reversed(instances):
            try:
                self._close_sync(instance)
            except BaseException as exc:  # noqa: BLE001 — aggregate cleanup
                errors.append(exc)

        if errors:
            raise _CleanupError(errors)

    # ------------------------------------------------------------------
    # Internal resolution
    # ------------------------------------------------------------------

    def _resolve(
        self,
        service: Any,
        *,
        name: str | None,
        stack: list[Any],
    ) -> Any:
        key = self._key(service, name)

        override = self._find_override(key)
        if override is not None:
            return override

        descriptor = self._find_descriptor(key)
        if descriptor is None:
            raise ServiceNotRegisteredError(
                f"service {self._display_key(key)!r} is not registered"
            )

        if descriptor.lifetime is ServiceLifetime.SCOPED:
            return self._resolve_scoped(key, descriptor, stack)

        if descriptor.lifetime is ServiceLifetime.SINGLETON:
            return self._resolve_singleton(key, descriptor, stack)

        return self._construct_sync(key, descriptor.factory, stack)

    async def _aresolve(
        self,
        service: Any,
        *,
        name: str | None,
        stack: list[Any],
    ) -> Any:
        key = self._key(service, name)

        override = self._find_override(key)
        if override is not None:
            return override

        descriptor = self._find_descriptor(key)
        if descriptor is None:
            raise ServiceNotRegisteredError(
                f"service {self._display_key(key)!r} is not registered"
            )

        if descriptor.lifetime is ServiceLifetime.SCOPED:
            return await self._aresolve_scoped(key, descriptor, stack)

        if descriptor.lifetime is ServiceLifetime.SINGLETON:
            return await self._aresolve_singleton(key, descriptor, stack)

        return await self._construct_async(key, descriptor.factory, stack)

    def _find_descriptor(self, key: Any) -> ServiceDescriptor[Any] | None:
        descriptor = self._descriptors.get(key)
        if descriptor is not None:
            return descriptor
        if self._parent is not None:
            return self._parent._find_descriptor(key)
        return None

    def _find_override(self, key: Any) -> Any | None:
        if key in self._overrides:
            return self._overrides[key]
        if self._parent is not None:
            return self._parent._find_override(key)
        return None

    def _resolve_singleton(
        self,
        key: Any,
        descriptor: ServiceDescriptor[Any],
        stack: list[Any],
    ) -> Any:
        owner = self._singleton_owner()

        with owner._lock:
            if key in owner._overrides:
                return owner._overrides[key]
            existing = owner._instances.get(key)
            if existing is not None:
                return existing
            if key in owner._inflight:
                raise DependencyError(
                    f"singleton {self._display_key(key)!r} is being "
                    "constructed asynchronously; use 'aget()'"
                )

            instance = owner._construct_sync(key, descriptor.factory, stack)
            owner._instances[key] = instance
            return instance

    async def _aresolve_singleton(
        self,
        key: Any,
        descriptor: ServiceDescriptor[Any],
        stack: list[Any],
    ) -> Any:
        owner = self._singleton_owner()
        return await owner._aresolve_cached(key, descriptor.factory, stack)

    def _resolve_scoped(
        self,
        key: Any,
        descriptor: ServiceDescriptor[Any],
        stack: list[Any],
    ) -> Any:
        if self._parent is None:
            raise ScopeRequiredError(
                f"scoped service {self._display_key(key)!r} "
                "requires an active scope; use container.scope()"
            )

        with self._lock:
            if key in self._overrides:
                return self._overrides[key]
            existing = self._instances.get(key)
            if existing is not None:
                return existing
            if key in self._inflight:
                raise DependencyError(
                    f"scoped service {self._display_key(key)!r} "
                    "is being constructed asynchronously; use 'aget()'"
                )

            instance = self._construct_sync(key, descriptor.factory, stack)
            self._instances[key] = instance
            return instance

    async def _aresolve_scoped(
        self,
        key: Any,
        descriptor: ServiceDescriptor[Any],
        stack: list[Any],
    ) -> Any:
        if self._parent is None:
            raise ScopeRequiredError(
                f"scoped service {self._display_key(key)!r} "
                "requires an active scope; use container.scope()"
            )

        return await self._aresolve_cached(key, descriptor.factory, stack)

    async def _aresolve_cached(
        self,
        key: Any,
        factory: Callable[..., Any],
        stack: list[Any],
    ) -> Any:
        """
        Resolve a cached (singleton/scoped) service asynchronously.

        Per-key Futures avoid container-wide lock deadlocks when nested
        dependencies resolve concurrently.
        """
        with self._lock:
            if key in self._overrides:
                return self._overrides[key]
            existing = self._instances.get(key)
            if existing is not None:
                return existing

            inflight = self._inflight.get(key)
            if inflight is not None:
                if key in stack:
                    cycle = " -> ".join(
                        self._display_key(item) for item in [*stack, key]
                    )
                    raise CircularDependencyError(f"circular dependency: {cycle}")
                wait_for = inflight
                create = False
            else:
                wait_for = asyncio.get_running_loop().create_future()
                self._inflight[key] = wait_for
                create = True

        if not create:
            return await wait_for

        try:
            instance = await self._construct_async(key, factory, stack)
            with self._lock:
                if key in self._overrides:
                    discarded = instance
                    instance = self._overrides[key]
                else:
                    discarded = None
                self._instances[key] = instance
                self._inflight.pop(key, None)
            if not wait_for.done():
                wait_for.set_result(instance)
            if discarded is not None and discarded is not instance:
                await self._close_async(discarded)
            return instance
        except BaseException as exc:
            with self._lock:
                self._inflight.pop(key, None)
                self._instances.pop(key, None)
            if not wait_for.done():
                wait_for.set_exception(exc)
            raise

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _construct_sync(
        self,
        key: Any,
        factory: Callable[..., Any],
        stack: list[Any],
    ) -> Any:
        if key in stack:
            cycle = " -> ".join(self._display_key(item) for item in [*stack, key])
            raise CircularDependencyError(f"circular dependency: {cycle}")

        stack = [*stack, key]
        kwargs = self._dependencies_sync(factory, stack)
        result = factory(**kwargs)

        if inspect.isawaitable(result):
            close = getattr(result, "close", None)
            if close is not None:
                close()
            raise AsyncResolutionError(
                f"service {self._display_key(key)!r} "
                "requires async resolution; use 'aget()'"
            )

        return result

    async def _construct_async(
        self,
        key: Any,
        factory: Callable[..., Any],
        stack: list[Any],
    ) -> Any:
        if key in stack:
            cycle = " -> ".join(self._display_key(item) for item in [*stack, key])
            raise CircularDependencyError(f"circular dependency: {cycle}")

        stack = [*stack, key]
        kwargs = await self._dependencies_async(factory, stack)
        result = factory(**kwargs)

        if inspect.isawaitable(result):
            result = await result

        return result

    def _dependencies_sync(
        self,
        factory: Callable[..., Any],
        stack: list[Any],
    ) -> dict[str, Any]:
        hints = self._factory_hints(factory)
        result: dict[str, Any] = {}

        for parameter in inspect.signature(factory).parameters.values():
            if parameter.kind in (
                parameter.VAR_POSITIONAL,
                parameter.VAR_KEYWORD,
            ):
                continue
            if parameter.name == "self":
                continue

            dependency = hints.get(parameter.name)
            if dependency is None:
                if parameter.default is not inspect.Parameter.empty:
                    continue
                raise DependencyError(
                    f"factory {factory!r} has untyped required dependency "
                    f"{parameter.name!r}"
                )

            try:
                result[parameter.name] = self._resolve(
                    dependency,
                    name=None,
                    stack=stack,
                )
            except ServiceNotRegisteredError:
                if parameter.default is not inspect.Parameter.empty:
                    continue
                raise

        return result

    async def _dependencies_async(
        self,
        factory: Callable[..., Any],
        stack: list[Any],
    ) -> dict[str, Any]:
        hints = self._factory_hints(factory)
        result: dict[str, Any] = {}

        for parameter in inspect.signature(factory).parameters.values():
            if parameter.kind in (
                parameter.VAR_POSITIONAL,
                parameter.VAR_KEYWORD,
            ):
                continue
            if parameter.name == "self":
                continue

            dependency = hints.get(parameter.name)
            if dependency is None:
                if parameter.default is not inspect.Parameter.empty:
                    continue
                raise DependencyError(
                    f"factory {factory!r} has untyped required dependency "
                    f"{parameter.name!r}"
                )

            try:
                result[parameter.name] = await self._aresolve(
                    dependency,
                    name=None,
                    stack=stack,
                )
            except ServiceNotRegisteredError:
                if parameter.default is not inspect.Parameter.empty:
                    continue
                raise

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _factory_hints(self, factory: Callable[..., Any]) -> dict[str, Any]:
        target = self._dependency_target(factory)
        try:
            return get_type_hints(target)
        except (NameError, TypeError):
            return dict(getattr(target, "__annotations__", {}) or {})

    def _ensure_open(self) -> None:
        if self._closed:
            raise ContainerClosedError("container is closed")

    def _singleton_owner(self) -> Container:
        current = self
        while current._parent is not None:
            current = current._parent
        return current

    @staticmethod
    def _dependency_target(factory: Callable[..., Any]) -> Callable[..., Any]:
        """Return the callable whose annotations describe constructor deps."""
        if inspect.isclass(factory):
            return factory.__init__
        return factory

    @staticmethod
    def _key(service: Any, name: str | None) -> tuple[Any, str | None]:
        return service, name

    @staticmethod
    def _display_key(key: Any) -> str:
        service, name = key
        if isinstance(service, type):
            value = service.__qualname__
        else:
            value = repr(service)
        if name:
            value = f"{value}:{name}"
        return value

    @staticmethod
    def _close_sync(instance: Any) -> None:
        close = getattr(instance, "close", None)
        if close is not None:
            result = close()
            if inspect.isawaitable(result):
                raise AsyncResolutionError(
                    "service requires async cleanup; use 'aclose()'"
                )
            return

        if getattr(instance, "aclose", None) is not None:
            raise AsyncResolutionError(
                "service requires async cleanup; use 'aclose()'"
            )

    @staticmethod
    async def _close_async(instance: Any) -> None:
        close = getattr(instance, "aclose", None)
        if close is not None:
            await close()
            return

        close = getattr(instance, "close", None)
        if close is None:
            return

        result = close()
        if inspect.isawaitable(result):
            await result


class ContainerScope(
    AbstractAsyncContextManager["ContainerScope"],
    AbstractContextManager["ContainerScope"],
):
    """Context manager for request/job scoped dependencies."""

    def __init__(self, container: Container) -> None:
        self.container = container

    def get(
        self,
        service: type[T] | Any,
        *,
        name: str | None = None,
    ) -> T:
        return self.container.get(service, name=name)

    async def aget(
        self,
        service: type[T] | Any,
        *,
        name: str | None = None,
    ) -> T:
        return await self.container.aget(service, name=name)

    def __enter__(self) -> ContainerScope:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.container.close()

    async def __aenter__(self) -> ContainerScope:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.container.aclose()


_container: Container | None = None
_container_lock = RLock()


def get_container() -> Container:
    """Return the process-wide application container."""
    global _container

    if _container is None:
        with _container_lock:
            if _container is None:
                _container = Container()

    return _container


def reset_container() -> None:
    """Dispose and clear the process-wide container (intended for tests)."""
    global _container

    with _container_lock:
        if _container is not None:
            _container.close()
            _container = None


__all__ = [
    "AsyncResolutionError",
    "CircularDependencyError",
    "Container",
    "ContainerClosedError",
    "ContainerScope",
    "DependencyError",
    "ScopeRequiredError",
    "ServiceDescriptor",
    "ServiceLifetime",
    "ServiceNotRegisteredError",
    "get_container",
    "reset_container",
]
