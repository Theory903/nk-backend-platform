"""Tests for the production dependency-injection container."""

from __future__ import annotations

import pytest

from {{cookiecutter.project_name}}.core.di import (
    AsyncResolutionError,
    CircularDependencyError,
    Container,
    ContainerClosedError,
    DependencyError,
    ScopeRequiredError,
    ServiceLifetime,
    ServiceNotRegisteredError,
    get_container,
    reset_container,
)


class Database:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class UserRepository:
    def __init__(self, database: Database) -> None:
        self.database = database


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository


class AsyncResource:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class _CycleA:
    def __init__(self, b: "_CycleB") -> None:
        self.b = b


class _CycleB:
    def __init__(self, a: _CycleA) -> None:
        self.a = a


# ------------------------------------------------------------------
# Basics
# ------------------------------------------------------------------


def test_container_registers_and_caches_singleton() -> None:
    c = Container()
    calls: list[int] = []

    def _factory() -> object:
        calls.append(1)
        return object()

    c.register("svc", _factory)
    first = c.get("svc")
    second = c.get("svc")
    assert first is second
    assert len(calls) == 1


def test_container_missing_raises() -> None:
    c = Container()
    with pytest.raises(ServiceNotRegisteredError, match="missing"):
        c.get("missing")


def test_get_container_singleton() -> None:
    reset_container()
    try:
        a = get_container()
        b = get_container()
        assert a is b
    finally:
        reset_container()


def test_transient_creates_new_instance_each_time() -> None:
    c = Container()
    c.register("svc", object, lifetime=ServiceLifetime.TRANSIENT)
    assert c.get("svc") is not c.get("svc")


def test_has_and_describe() -> None:
    c = Container()
    c.register(Database, Database, lifetime=ServiceLifetime.SINGLETON)
    assert c.has(Database)
    assert not c.has(UserService)
    assert c.describe()["Database"] == "singleton"


# ------------------------------------------------------------------
# Constructor injection
# ------------------------------------------------------------------


def test_class_factory_constructor_injection() -> None:
    c = Container()
    c.register(Database, Database)
    c.register(UserRepository, UserRepository)
    c.register(UserService, UserService)

    service = c.get(UserService)
    assert isinstance(service, UserService)
    assert isinstance(service.repository, UserRepository)
    assert isinstance(service.repository.database, Database)
    assert c.get(Database) is service.repository.database


def test_typed_factory_function_injection() -> None:
    c = Container()
    c.register(Database, Database)

    def make_repo(database: Database) -> UserRepository:
        return UserRepository(database)

    c.register(UserRepository, make_repo)
    repo = c.get(UserRepository)
    assert repo.database is c.get(Database)


def test_untyped_required_dependency_raises() -> None:
    c = Container()

    def bad_factory(database) -> Database:  # type: ignore[no-untyped-def]
        return database

    c.register("bad", bad_factory)
    with pytest.raises(DependencyError, match="untyped"):
        c.get("bad")


# ------------------------------------------------------------------
# Lifetimes & scopes
# ------------------------------------------------------------------


def test_scoped_requires_active_scope() -> None:
    c = Container()
    c.register(Database, Database, lifetime=ServiceLifetime.SCOPED)
    with pytest.raises(ScopeRequiredError, match="scope"):
        c.get(Database)


def test_scoped_cached_within_scope_and_isolated_across() -> None:
    c = Container()
    c.register(Database, Database)
    c.register(UserRepository, UserRepository, lifetime=ServiceLifetime.SCOPED)

    with c.scope() as scope_a:
        repo_a1 = scope_a.get(UserRepository)
        repo_a2 = scope_a.get(UserRepository)
        assert repo_a1 is repo_a2
        assert repo_a1.database is c.get(Database)

    with c.scope() as scope_b:
        repo_b = scope_b.get(UserRepository)
        assert repo_b is not repo_a1
        assert repo_b.database is c.get(Database)


@pytest.mark.anyio
async def test_async_scope_resolves_graph() -> None:
    c = Container()
    c.register(Database, Database)
    c.register(UserRepository, UserRepository, lifetime=ServiceLifetime.SCOPED)
    c.register(UserService, UserService, lifetime=ServiceLifetime.SCOPED)

    async with c.scope() as scope:
        service = await scope.aget(UserService)
        again = await scope.aget(UserService)
        assert service is again
        assert service.repository.database is await c.aget(Database)


# ------------------------------------------------------------------
# Async factories & cleanup
# ------------------------------------------------------------------


@pytest.mark.anyio
async def test_async_factory_requires_aget() -> None:
    c = Container()

    async def make_db() -> Database:
        return Database()

    c.register(Database, make_db)

    with pytest.raises(AsyncResolutionError, match="aget"):
        c.get(Database)

    db = await c.aget(Database)
    assert isinstance(db, Database)


@pytest.mark.anyio
async def test_aclose_calls_aclose_on_instances() -> None:
    c = Container()
    c.register(AsyncResource, AsyncResource)
    resource = await c.aget(AsyncResource)
    await c.aclose()
    assert resource.closed is True


def test_close_calls_close_on_instances() -> None:
    c = Container()
    c.register(Database, Database)
    db = c.get(Database)
    c.close()
    assert db.closed is True


def test_scope_exit_closes_scoped_instances() -> None:
    c = Container()
    c.register(Database, Database, lifetime=ServiceLifetime.SCOPED)

    with c.scope() as scope:
        db = scope.get(Database)
        assert db.closed is False

    assert db.closed is True


# ------------------------------------------------------------------
# Overrides, cycles, named services
# ------------------------------------------------------------------


def test_override_replaces_instance() -> None:
    c = Container()
    c.register(Database, Database)
    fake = Database()
    c.override(Database, fake)
    assert c.get(Database) is fake


def test_override_without_prior_registration() -> None:
    c = Container()
    fake = Database()
    c.override(Database, fake)
    assert c.get(Database) is fake


def test_circular_dependency_detected() -> None:
    c = Container()
    c.register(_CycleA, _CycleA)
    c.register(_CycleB, _CycleB)

    with pytest.raises(CircularDependencyError, match="circular"):
        c.get(_CycleA)


def test_named_services() -> None:
    c = Container()
    c.register("db", lambda: "primary", name="primary")
    c.register("db", lambda: "replica", name="replica")
    assert c.get("db", name="primary") == "primary"
    assert c.get("db", name="replica") == "replica"


def test_child_scope_inherits_parent_registrations() -> None:
    c = Container()
    c.register(Database, Database)
    assert c.scope().container.has(Database)


def test_override_works_for_transient() -> None:
    c = Container()
    c.register("svc", object, lifetime=ServiceLifetime.TRANSIENT)
    fake = object()
    c.override("svc", fake, lifetime=ServiceLifetime.TRANSIENT)
    assert c.get("svc") is fake
    assert c.get("svc") is fake


def test_get_after_close_raises() -> None:
    c = Container()
    c.register(Database, Database)
    c.close()
    with pytest.raises(ContainerClosedError):
        c.get(Database)


def test_register_on_closed_raises() -> None:
    c = Container()
    c.close()
    with pytest.raises(ContainerClosedError):
        c.register(Database, Database)
