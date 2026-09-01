import asyncio
import uuid
from typing import Any, AsyncGenerator
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

{%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}
from redis.asyncio import ConnectionPool
from {{cookiecutter.project_name}}.services.redis.dependency import get_redis_pool

{%- endif %}
{%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] %}
from aio_pika import Channel
from aio_pika.abc import AbstractExchange, AbstractQueue
from aio_pika.pool import Pool
from {{cookiecutter.project_name}}.services.rabbit.dependencies import \
    get_rmq_channel_pool
from {{cookiecutter.project_name}}.services.rabbit.lifespan import (init_rmq,
                                                                    shutdown_rmq)

{%- endif %}
{%- if cookiecutter.enable_kafka in [True, "True", "true", 1, "1"] %}
from aiokafka import AIOKafkaProducer
from {{cookiecutter.project_name}}.services.kafka.dependencies import get_kafka_producer
from {{cookiecutter.project_name}}.services.kafka.lifespan import (init_kafka,
                                                                   shutdown_kafka)

{%- endif %}

{%- if cookiecutter.enable_nats in [True, "True", "true", 1, "1"] %}
from nats.aio.client import Client as NATS
from {{cookiecutter.project_name}}.services.nats.dependencies import get_nats
from {{cookiecutter.project_name}}.services.nats.lifespan import (init_nats,
                                                                   shutdown_nats)
{%- endif %}

from {{cookiecutter.project_name}}.settings import settings
from {{cookiecutter.project_name}}.web.application import get_app
{%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.identity import deps as auth_deps
from {{cookiecutter.project_name}}.identity.api_keys import ApiKeyStore
from {{cookiecutter.project_name}}.identity.csrf import CsrfProtection
from {{cookiecutter.project_name}}.identity.session import SessionStore
{%- endif %}

{%- if cookiecutter.orm == "sqlalchemy" %}
from sqlalchemy.ext.asyncio import (AsyncConnection, AsyncEngine, AsyncSession,
                                    async_sessionmaker, create_async_engine)
from {{cookiecutter.project_name}}.db.dependencies import get_db_session
from {{cookiecutter.project_name}}.db.utils import create_database, drop_database

{%- elif cookiecutter.orm == "tortoise" %}
import nest_asyncio
from tortoise import Tortoise
from tortoise.contrib.test import finalizer, initializer
from {{cookiecutter.project_name}}.db.config import MODELS_MODULES, TORTOISE_CONFIG

nest_asyncio.apply()
{%- elif cookiecutter.orm == "ormar" %}
from sqlalchemy.engine import create_engine
from {{cookiecutter.project_name}}.db.base import database
from {{cookiecutter.project_name}}.db.utils import create_database, drop_database

{%- elif cookiecutter.orm == "psycopg" %}
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from {{cookiecutter.project_name}}.db.dependencies import get_db_pool

{%- elif cookiecutter.orm == "piccolo" %}
{%- if cookiecutter.db_info.name == "postgresql" %}
from piccolo.engine.postgres import PostgresEngine

{%- endif %}
from piccolo.conf.apps import Finder
from piccolo.table import create_tables, drop_tables

{%- elif cookiecutter.orm == "beanie" %}
import beanie
from pymongo import AsyncMongoClient

{%- endif %}



def _port_open(host: str, port: int, timeout: float = 0.2) -> bool:
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """
    Backend for anyio pytest plugin.

    :return: backend name.
    """
    return 'asyncio'

{%- if cookiecutter.orm == "sqlalchemy" %}
@pytest.fixture(scope="session")
async def _engine(anyio_backend: Any) -> AsyncGenerator[AsyncEngine, None]:
    """
    Create engine and databases.

    :yield: new engine.
    """
    from {{cookiecutter.project_name}}.db.meta import meta
    from {{cookiecutter.project_name}}.db.models import load_all_models

    load_all_models()

    await create_database()

    engine = create_async_engine(str(settings.db_url))
    async with engine.begin() as conn:
        await conn.run_sync(meta.create_all)

    try:
        yield engine
    finally:
        await engine.dispose()
        await drop_database()

@pytest.fixture
async def dbsession(
    _engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Get session to database.

    Fixture that returns a SQLAlchemy session with a SAVEPOINT, and the rollback to it
    after the test completes.

    :param _engine: current engine.
    :yields: async session.
    """
    connection = await _engine.connect()
    trans = await connection.begin()

    session_maker = async_sessionmaker(
        connection,
        expire_on_commit=False,
    )
    session = session_maker()

    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await connection.close()

{%- elif cookiecutter.orm == "tortoise" %}

@pytest.fixture(autouse=True)
async def initialize_db() -> AsyncGenerator[None, None]:
    """
    Initialize models and database.

    :yields: Nothing.
    """
    initializer(
        MODELS_MODULES,
        db_url=str(settings.db_url),
        app_label="models",
    )
    await Tortoise.init(config=TORTOISE_CONFIG)

    yield

    await Tortoise.close_connections()
    finalizer()

{%- elif cookiecutter.orm == "ormar" %}

@pytest.fixture(autouse=True, scope="function")
async def initialize_db() -> AsyncGenerator[None, None]:
    """
    Create models and databases.

    :yield: new engine.
    """
    from {{cookiecutter.project_name}}.db.base import meta
    from {{cookiecutter.project_name}}.db.models import load_all_models

    load_all_models()

    create_database()

    engine = create_engine(str(settings.db_url))
    with engine.begin() as conn:
        meta.create_all(conn)

    engine.dispose()

    await database.connect()

    yield

    await database.disconnect()

    engine = create_engine(str(settings.db_url))
    with engine.begin() as conn:
        meta.drop_all(conn)
    engine.dispose()
    drop_database()

{%- elif cookiecutter.orm == "psycopg" %}

async def drop_db() -> None:
    """Drops database after tests."""
    pool = AsyncConnectionPool(conninfo=str(settings.db_url.with_path("/postgres")), open=False)
    await pool.open(wait=True)
    async with pool.connection() as conn:
        await conn.set_autocommit(True)
        await conn.execute(
            "SELECT pg_terminate_backend(pg_stat_activity.pid) "  # noqa: S608
            "FROM pg_stat_activity "
            "WHERE pg_stat_activity.datname = %(dbname)s "
            "AND pid <> pg_backend_pid();",
            params={
                "dbname": settings.db_base,
            }
        )
        await conn.execute(
            f"DROP DATABASE {settings.db_base}",
        )
    await pool.close()


async def create_db() -> None:
    """Creates database for tests."""
    pool = AsyncConnectionPool(conninfo=str(settings.db_url.with_path("/postgres")), open=False)
    await pool.open(wait=True)
    async with pool.connection() as conn_check:
        res = await conn_check.execute(
            "SELECT 1 FROM pg_database WHERE datname=%(dbname)s",
            params={
                "dbname": settings.db_base,
            }
        )
        db_exists = False
        row = await res.fetchone()
        if row is not None:
            db_exists = row[0]

    if db_exists:
        await drop_db()

    async with pool.connection() as conn_create:
        await conn_create.set_autocommit(True)
        await conn_create.execute(
            f"CREATE DATABASE {settings.db_base};",
        )
    await pool.close()


async def create_tables(connection: AsyncConnection[Any]) -> None:
    """
    Create tables for your database.

    Since psycopg doesn't have migration tool,
    you must create your tables for tests.

    :param connection: connection to database.
    """
    {%- if cookiecutter.add_dummy in [True, "True", "true", 1, "1"] %}
    await connection.execute(
        "CREATE TABLE dummy ("
        "id SERIAL primary key,"
        "name VARCHAR(200)"
        ");"
    )
    {%- endif %}
    pass


@pytest.fixture
async def dbpool() -> AsyncGenerator[AsyncConnectionPool[Any], None]:
    """
    Creates database connections pool to test database.

    This connection must be used in tests and for application.

    :yield: database connections pool.
    """
    await create_db()
    pool = AsyncConnectionPool(conninfo=str(settings.db_url), open=False)
    await pool.open(wait=True)

    async with pool.connection() as create_conn:
        await create_tables(create_conn)

    try:
        yield pool
    finally:
        await pool.close()
        await drop_db()

{%- elif cookiecutter.orm == "piccolo" %}

{%- if cookiecutter.db_info.name == "postgresql" %}
async def drop_database(engine: PostgresEngine) -> None:
    """
    Drops test database.

    :param engine: engine connected to postgres database.
    """
    await engine.run_ddl(
        "SELECT pg_terminate_backend(pg_stat_activity.pid) "  # noqa: S608
        "FROM pg_stat_activity "
        f"WHERE pg_stat_activity.datname = '{settings.db_base}' "
        "AND pid <> pg_backend_pid();",
    )
    await engine.run_ddl(
        f"DROP DATABASE {settings.db_base};",
    )
{%- endif %}

@pytest.fixture(autouse=True)
async def setup_db() -> AsyncGenerator[None, None]:
    """
    Fixture to create all tables before test and drop them after.

    :yield: nothing.
    """
    {%- if cookiecutter.db_info.name == "postgresql" %}
    engine = PostgresEngine(
        config={
            "database": "postgres",
            "user": settings.db_user,
            "password": settings.db_pass,
            "host": settings.db_host,
            "port": settings.db_port,
        },
    )
    await engine.start_connection_pool()

    db_exists = await engine.run_ddl(
        f"SELECT 1 FROM pg_database WHERE datname='{settings.db_base}'"  # noqa: S608
    )
    if db_exists:
        await drop_database(engine)
    await engine.run_ddl(f"CREATE DATABASE {settings.db_base}")
    {%- endif %}
    tables = Finder().get_table_classes()
    create_tables(*tables, if_not_exists=True)

    yield

    drop_tables(*tables)
    {%- if cookiecutter.db_info.name == "postgresql" %}
    await drop_database(engine)
    {%- endif %}

{%- elif cookiecutter.orm == "beanie" %}
@pytest.fixture(autouse=True)
async def setup_db() -> AsyncGenerator[None, None]:
    """
    Fixture to create database connection.

    :yield: nothing.
    """
    client = AsyncMongoClient(settings.db_url.human_repr())  # type: ignore
    from {{cookiecutter.project_name}}.db.models import load_all_models
    await beanie.init_beanie(
        database=client[settings.db_base],
        document_models=load_all_models(),  # type: ignore
    )
    yield


{%- endif %}

{%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] %}

@pytest.fixture
async def test_rmq_pool() -> AsyncGenerator[Any, None]:
    """Rabbit channel pool, or a stand-in when broker is unavailable."""
    if not _port_open("localhost", 5672):
        yield object()
        return
    app_mock = SimpleNamespace(state=SimpleNamespace())
    try:
        await init_rmq(app_mock)
    except Exception:
        yield object()
        return
    try:
        yield getattr(app_mock.state, "rmq_channel_pool")
    finally:
        await shutdown_rmq(app_mock)



@pytest.fixture
async def test_exchange_name() -> str:
    """
    Name of an exchange to use in tests.

    :return: name of an exchange.
    """
    return uuid.uuid4().hex


@pytest.fixture
async def test_routing_key() -> str:
    """
    Name of routing key to use while binding test queue.

    :return: key string.
    """
    return uuid.uuid4().hex


@pytest.fixture
async def test_exchange(
    test_exchange_name: str,
    test_rmq_pool: Any,
) -> AsyncGenerator[Any, None]:
    """Creates test exchange when RabbitMQ is available."""
    acquire = getattr(test_rmq_pool, "acquire", None)
    if acquire is None:
        pytest.skip("RabbitMQ not available")
    async with test_rmq_pool.acquire() as conn:
        exchange = await conn.declare_exchange(
            name=test_exchange_name,
            auto_delete=True,
        )
        yield exchange
        await exchange.delete(if_unused=False)



@pytest.fixture
async def test_queue(
    test_exchange: Any,
    test_rmq_pool: Any,
    test_routing_key: str,
) -> AsyncGenerator[Any, None]:
    """Creates queue connected to exchange when RabbitMQ is available."""
    acquire = getattr(test_rmq_pool, "acquire", None)
    if acquire is None:
        pytest.skip("RabbitMQ not available")
    async with test_rmq_pool.acquire() as conn:
        queue = await conn.declare_queue(name=uuid.uuid4().hex)
        await queue.bind(
            exchange=test_exchange,
            routing_key=test_routing_key,
        )
        yield queue
        await queue.delete(if_unused=False, if_empty=False)



@pytest.fixture
async def test_kafka_producer() -> AsyncGenerator[Any, None]:
    """Kafka producer, or a stand-in when broker is unavailable."""
    if not (_port_open("localhost", 9092) or _port_open("localhost", 9094)):
        yield object()
        return
    app_mock = SimpleNamespace(state=SimpleNamespace())
    try:
        await init_kafka(app_mock)
    except Exception:
        yield object()
        return
    try:
        yield getattr(app_mock.state, "kafka_producer")
    finally:
        await shutdown_kafka(app_mock)



@pytest.fixture
async def test_nats() -> AsyncGenerator[Any, None]:
    """NATS client, or a stand-in when broker is unavailable."""
    if not _port_open("localhost", 4222):
        yield object()
        return
    app_mock = SimpleNamespace(state=SimpleNamespace())
    try:
        await init_nats(app_mock)
    except Exception:
        yield object()
        return
    try:
        yield getattr(app_mock.state, "nats")
    finally:
        await shutdown_nats(app_mock)



@pytest.fixture
async def test_redis_pool() -> AsyncGenerator[ConnectionPool, None]:
    """
    Get instance of a fake redis.

    :yield: ConnectionPool instance.
    """
    pool = ConnectionPool.from_url(str(settings.redis_url))

    yield pool

    await pool.disconnect()

{%- endif %}

@pytest.fixture
def fastapi_app(
    {%- if cookiecutter.orm == "sqlalchemy" %}
    dbsession: AsyncSession,
    {%- elif cookiecutter.orm == "psycopg" %}
    dbpool: AsyncConnectionPool[Any],
    {%- endif %}
    {% if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] -%}
    test_redis_pool: ConnectionPool,
    {%- endif %}
    {%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] %}
    test_rmq_pool: Pool[Channel],
    {%- endif %}
    {%- if cookiecutter.enable_kafka in [True, "True", "true", 1, "1"] %}
    test_kafka_producer: AIOKafkaProducer,
    {%- endif %}
    {%- if cookiecutter.enable_nats in [True, "True", "true", 1, "1"] %}
    test_nats: NATS,
    {%- endif %}
) -> FastAPI:
    """
    Fixture for creating FastAPI app.

    :return: fastapi app with mocked dependencies.
    """
    application = get_app()
    {%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
    # Generated integration tests use a scoped admin session so protected
    # infrastructure routes are exercised as authenticated requests.
    session_store = SessionStore()
    auth_deps._api_key_store = ApiKeyStore()
    auth_deps._session_store = session_store
    auth_deps._csrf_protection = CsrfProtection(
        settings.users_secret or "test-users-secret-32chars!!",
    )
    application.state.test_session_id = session_store.create(
        "test-admin",
        data={
            "roles": ["admin"],
            "scopes": [
                "cache.read",
                "cache.write",
                "messaging.publish",
                "dummy.read",
                "dummy.write",
                "ops.metrics",
                "identity.provision",
            ],
        },
    )
    application.state.test_csrf_token = auth_deps._csrf_protection.generate_token(
        application.state.test_session_id,
    )
    {%- endif %}
    {%- if cookiecutter.orm == "sqlalchemy" %}
    application.dependency_overrides[get_db_session] = lambda: dbsession
    {%- elif cookiecutter.orm == "psycopg" %}
    application.dependency_overrides[get_db_pool] = lambda: dbpool
    {%- endif %}
    {%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}
    application.dependency_overrides[get_redis_pool] = lambda: test_redis_pool
    {%- endif %}
    {%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] %}
    application.dependency_overrides[get_rmq_channel_pool] = lambda: test_rmq_pool
    {%- endif %}
    {%- if cookiecutter.enable_kafka in [True, "True", "true", 1, "1"] %}
    application.dependency_overrides[get_kafka_producer] = lambda: test_kafka_producer
    {%- endif %}
    {%- if cookiecutter.enable_nats in [True, "True", "true", 1, "1"] %}
    application.dependency_overrides[get_nats] = lambda: test_nats
    {%- endif %}
    return application  # noqa: RET504


@pytest.fixture
async def client(
    fastapi_app: FastAPI,
    anyio_backend: Any
) -> AsyncGenerator[AsyncClient, None]:
    """
    Fixture that creates client for requesting server.

    :param fastapi_app: the application.
    :yield: client for the app.
    """
    async with AsyncClient(transport=ASGITransport(fastapi_app, raise_app_exceptions=False), base_url="http://test", timeout=2.0) as ac:
            {%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
            ac.cookies.set("session", fastapi_app.state.test_session_id)
            ac.headers["X-CSRF-Token"] = fastapi_app.state.test_csrf_token
            {%- endif %}
            yield ac
