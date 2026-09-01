import asyncio
import inspect
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI
{%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}
from redis.asyncio import Redis
{%- endif %}
from {{cookiecutter.project_name}}.core.graceful import ShutdownState
{%- if cookiecutter.otlp_enabled in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.core.logging import RedactionFilter
{%- endif %}
from {{cookiecutter.project_name}}.web.api.monitoring.views import (
    register_readiness_check,
)
from {{cookiecutter.project_name}}.settings import settings

def _verify_auth_schema(engine: Any, statement: Any) -> None:
    """Run the synchronous auth schema probe off the event loop."""
    with engine.connect() as connection:
        connection.execute(statement)

{%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.services.redis.lifespan import (init_redis,
                                                                   shutdown_redis)

{%- endif %}

{%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.services.rabbit.lifespan import (init_rmq,
                                                                    shutdown_rmq)

{%- endif %}

{%- if cookiecutter.enable_kafka in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.services.kafka.lifespan import (init_kafka,
                                                                   shutdown_kafka)

{%- endif %}

{%- if cookiecutter.enable_nats in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.services.nats.lifespan import (init_nats,
                                                                   shutdown_nats)

{%- endif %}

{%- if cookiecutter.enable_taskiq in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.tkq import broker
from taskiq.instrumentation import TaskiqInstrumentor

{%- endif %}
{%- if cookiecutter.enable_rag_traditional in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.ai.embeddings import get_embedding_provider
from {{cookiecutter.project_name}}.ai.gateway import get_router
from {{cookiecutter.project_name}}.ai.knowledge.answer import RAGAnswerService
from {{cookiecutter.project_name}}.ai.knowledge.retrieval import HybridRetriever
from {{cookiecutter.project_name}}.ai.knowledge.runtime import (
    ChatModelAdapter,
    HybridRetrievalAdapter,
    RedisAnswerCache,
)
from {{cookiecutter.project_name}}.ai.knowledge.vector_store import (
    InMemoryVectorStore,
)
{%- endif %}


{%- if cookiecutter.orm == "ormar" %}
from {{cookiecutter.project_name}}.db.base import database

{%- if cookiecutter.db_info.name != "none" and cookiecutter.enable_migrations not in [True, "True", "true", 1, "1"] %}
from sqlalchemy.engine import create_engine
from {{cookiecutter.project_name}}.db.base import meta
from {{cookiecutter.project_name}}.db.models import load_all_models

{%- endif %}
{%- endif %}

{%- if cookiecutter.otlp_enabled in [True, "True", "true", 1, "1"] %}
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import (DEPLOYMENT_ENVIRONMENT, SERVICE_NAME,
                                         TELEMETRY_SDK_LANGUAGE, Resource)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import (
    ParentBased,
    TraceIdRatioBased,
)
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

{%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}
from opentelemetry.instrumentation.redis import RedisInstrumentor

{%- endif %}
{%- if cookiecutter.db_info.name == "postgresql" and cookiecutter.orm in ["ormar", "tortoise"] %}
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor

{%- endif %}
{%- if cookiecutter.orm == "sqlalchemy" %}
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

{%- endif %}
{%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] %}
from opentelemetry.instrumentation.aio_pika import AioPikaInstrumentor

{%- endif %}
{%- if cookiecutter.enable_loguru not in [True, "True", "true", 1, "1"] %}
from opentelemetry.instrumentation.logging import LoggingInstrumentor

{%- endif %}

{%- endif %}

{%- if cookiecutter.orm == "psycopg" %}
import psycopg_pool


async def _setup_db(app: FastAPI) -> None:
    """
    Creates connection pool for timescaledb.

    :param app: current FastAPI app.
    """
    app.state.db_pool = psycopg_pool.AsyncConnectionPool(conninfo=str(settings.db_url), open=False)
    await app.state.db_pool.open(wait=True)
{%- endif %}

{%- if cookiecutter.orm == "sqlalchemy" %}
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
{%- if cookiecutter.enable_migrations not in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.db.meta import meta
from {{cookiecutter.project_name}}.db.models import load_all_models

{%- endif %}


def _setup_db(app: FastAPI) -> None:  # pragma: no cover
    """
    Creates connection to the database.

    This function creates SQLAlchemy engine instance,
    session_factory for creating sessions
    and stores them in the application's state property.

    :param app: fastAPI application.
    """
    engine = create_async_engine(str(settings.db_url), echo=settings.db_echo)
    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )
    app.state.db_engine = engine
    app.state.db_session_factory = session_factory
{%- endif %}

{%- if cookiecutter.orm == "beanie" %}
import beanie
from pymongo import AsyncMongoClient
from {{cookiecutter.project_name}}.db.models import load_all_models
async def _setup_db(app: FastAPI) -> None:
    client = AsyncMongoClient(str(settings.db_url))  # type: ignore
    app.state.db_client = client
    await beanie.init_beanie(
        database=client[settings.db_base],
        document_models=load_all_models(),  # type: ignore
    )
{%- endif %}

{%- if cookiecutter.enable_migrations not in [True, "True", "true", 1, "1"] %}
{%- if cookiecutter.orm in ["ormar", "sqlalchemy"] %}
async def _create_tables() -> None:  # pragma: no cover
    """Populates tables in the database."""
    load_all_models()
    {%- if cookiecutter.orm == "ormar" %}
    engine = create_engine(str(settings.db_url))
    with engine.connect() as connection:
        meta.create_all(connection)
    engine.dispose()
    {%- elif cookiecutter.orm == "sqlalchemy" %}
    engine = create_async_engine(str(settings.db_url))
    async with engine.begin() as connection:
        await connection.run_sync(meta.create_all)
    await engine.dispose()
    {%- endif %}
{%- endif %}
{%- endif %}

{%- if cookiecutter.otlp_enabled in [True, "True", "true", 1, "1"] %}
_OTEL_RUNTIME: dict[str, Any] = {}


def setup_opentelemetry(app: FastAPI) -> None:  # pragma: no cover
    """
    Enables opentelemetry instrumentation.

    :param app: current application.
    """
    if not settings.opentelemetry_endpoint:
        return
    if getattr(app.state, "otel_configured", False):
        return

    if not _OTEL_RUNTIME:
        otlp_resource = Resource(
            attributes={
                SERVICE_NAME: "{{cookiecutter.project_name}}",
                "service.version": settings.service_version,
                "service.role": settings.service_role,
                TELEMETRY_SDK_LANGUAGE: "python",
                DEPLOYMENT_ENVIRONMENT: settings.environment,
            },
        )
        tracer_provider = TracerProvider(
            resource=otlp_resource,
            sampler=ParentBased(
                TraceIdRatioBased(settings.opentelemetry_trace_sample_rate),
            ),
        )
        tracer_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=settings.opentelemetry_endpoint),
            ),
        )
        trace.set_tracer_provider(tracer_provider=tracer_provider)

        meter_provider = MeterProvider(
            resource=otlp_resource,
            metric_readers=[
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(endpoint=settings.opentelemetry_endpoint),
                ),
            ],
        )
        metrics.set_meter_provider(meter_provider)

        logger_provider = LoggerProvider(resource=otlp_resource)
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(
                OTLPLogExporter(endpoint=settings.opentelemetry_endpoint),
            ),
        )
        otel_logging_handler = LoggingHandler(
            level=logging.NOTSET,
            logger_provider=logger_provider,
        )
        otel_logging_handler.addFilter(RedactionFilter())
        logging.getLogger().addHandler(otel_logging_handler)
        _OTEL_RUNTIME.update(
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            logger_provider=logger_provider,
            logging_handler=otel_logging_handler,
        )

    tracer_provider = _OTEL_RUNTIME["tracer_provider"]
    meter_provider = _OTEL_RUNTIME["meter_provider"]
    logger_provider = _OTEL_RUNTIME["logger_provider"]
    otel_logging_handler = _OTEL_RUNTIME["logging_handler"]
    app.state.otel_tracer_provider = tracer_provider
    app.state.otel_meter_provider = meter_provider
    app.state.otel_logger_provider = logger_provider
    app.state.otel_logging_handler = otel_logging_handler

    excluded_endpoints = [
        app.url_path_for('health_check'),
        app.url_path_for('readiness_check'),
        app.url_path_for('openapi'),
        app.url_path_for('api_studio'),
        app.url_path_for('swagger_ui_html'),
        app.url_path_for('swagger_ui_redirect'),
        app.url_path_for('redoc_html'),
        {%- if cookiecutter.prometheus_enabled in [True, "True", "true", 1, "1"] %}
        "/api/metrics",
        {%- endif %}
    ]

    FastAPIInstrumentor().instrument_app(
        app,
        tracer_provider=tracer_provider,
        excluded_urls=",".join(excluded_endpoints),
    )
    {%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}
    RedisInstrumentor().instrument(
        tracer_provider=tracer_provider,
    )
    {%- endif %}
    {%- if cookiecutter.db_info.name == "postgresql" and cookiecutter.orm in ["ormar", "tortoise"] %}
    AsyncPGInstrumentor().instrument(
        tracer_provider=tracer_provider,
    )
    {%- endif %}
    {%- if cookiecutter.orm == "sqlalchemy" %}
    SQLAlchemyInstrumentor().instrument(
        tracer_provider=tracer_provider,
        engine=app.state.db_engine.sync_engine,
    )
    {%- endif %}
    {%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] %}
    AioPikaInstrumentor().instrument(
        tracer_provider=tracer_provider,
    )
    {%- endif %}
    {%- if cookiecutter.enable_taskiq in [True, "True", "true", 1, "1"] %}
    TaskiqInstrumentor().instrument_broker(
        broker,
        tracer_provider=tracer_provider,
    )
    {%- endif %}
    app.state.otel_configured = True


def stop_opentelemetry(app: FastAPI) -> None:  # pragma: no cover
    """
    Disables opentelemetry instrumentation.

    :param app: current application.
    """
    if not settings.opentelemetry_endpoint:
        return

    FastAPIInstrumentor().uninstrument_app(app)
    {%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}
    RedisInstrumentor().uninstrument()
    {%- endif %}
    {%- if cookiecutter.db_info.name == "postgresql" and cookiecutter.orm in ["ormar", "tortoise"] %}
    AsyncPGInstrumentor().uninstrument()
    {%- endif %}
    {%- if cookiecutter.orm == "sqlalchemy" %}
    SQLAlchemyInstrumentor().uninstrument()
    {%- endif %}
    {%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] %}
    AioPikaInstrumentor().uninstrument()
    {%- endif %}
    {%- if cookiecutter.enable_taskiq in [True, "True", "true", 1, "1"] %}
    TaskiqInstrumentor().uninstrument_broker(broker)
    {%- endif %}
    for provider_name in ("logger_provider", "meter_provider", "tracer_provider"):
        provider = _OTEL_RUNTIME.get(provider_name)
        if provider is None:
            continue
        try:
            provider.force_flush()
        except Exception:
            logging.getLogger(__name__).exception(
                "OpenTelemetry provider flush failed",
                extra={"provider": provider_name},
            )
    app.state.otel_configured = False

{%- endif %}


def _register_runtime_readiness(app: FastAPI) -> None:
    """Register checks for resources initialized by this application."""
    resource_names: list[tuple[str, str]] = []
    {%- if cookiecutter.db_info.name != "none" %}
    {%- if cookiecutter.orm == "sqlalchemy" %}
    resource_names.append(("database", "db_engine"))
    {%- elif cookiecutter.orm == "psycopg" %}
    resource_names.append(("database", "db_pool"))
    {%- elif cookiecutter.orm == "ormar" %}
    resource_names.append(("database", "database"))
    {%- elif cookiecutter.orm == "beanie" %}
    resource_names.append(("database", "db_client"))
    {%- endif %}
    {%- endif %}
    {%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}
    resource_names.append(("redis", "redis_pool"))
    {%- endif %}
    {%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] %}
    resource_names.append(("rabbitmq", "rmq_connection"))
    {%- endif %}
    {%- if cookiecutter.enable_kafka in [True, "True", "true", 1, "1"] %}
    resource_names.append(("kafka", "kafka_producer"))
    {%- endif %}
    {%- if cookiecutter.enable_nats in [True, "True", "true", 1, "1"] %}
    resource_names.append(("nats", "nats"))
    {%- endif %}

    for name, state_key in resource_names:
        async def check(
            state_key: str = state_key,
            resource_name: str = name,
        ) -> None:
            {%- if cookiecutter.orm == "ormar" %}
            if state_key == "database":
                if not database.is_connected:
                    raise RuntimeError("database is not connected")
                return
            {%- endif %}
            resource = getattr(app.state, state_key, None)
            if resource is None:
                raise RuntimeError(f"{resource_name} is not initialized")
            {%- if cookiecutter.orm == "sqlalchemy" %}
            if state_key == "db_engine":
                async with resource.connect() as connection:
                    await connection.execute(text("SELECT 1"))
            {%- endif %}
            {%- if cookiecutter.orm == "psycopg" %}
            if state_key == "db_pool":
                async with resource.connection() as connection:
                    await connection.execute("SELECT 1")
            {%- endif %}
            {%- if cookiecutter.orm == "beanie" %}
            if state_key == "db_client":
                await resource.admin.command("ping")
            {%- endif %}
            {%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}
            if state_key == "redis_pool":
                client = Redis(connection_pool=resource)
                try:
                    await client.ping()
                finally:
                    await client.aclose(close_connection_pool=False)
            {%- endif %}
            if getattr(resource, "is_closed", False):
                raise RuntimeError(f"{resource_name} is closed")
            ready = getattr(resource, "ready", None)
            if callable(ready):
                result = ready()
                if inspect.isawaitable(result):
                    result = await result
                if result is False:
                    raise RuntimeError(f"{resource_name} is not ready")

        register_readiness_check(name, check, app=app)


@asynccontextmanager
async def lifespan_setup(app: FastAPI) -> AsyncGenerator[None, None]:  # pragma: no cover
    """
    Actions to run on application startup.

    This function uses fastAPI app to store data
    in the state, such as db_engine.

    :param app: the fastAPI application.
    :return: function that actually performs actions.
    """

    app.middleware_stack = None
    app.state.startup_complete = False
    app.state.readiness_checks = dict(
        getattr(app.state, "readiness_checks", {}),
    )
    app.state.readiness_timeout_s = settings.readiness_timeout_s
    app.state.shutdown_state = ShutdownState(
        drain_timeout_s=settings.shutdown_drain_timeout_s,
        cleanup_timeout_s=settings.shutdown_cleanup_timeout_s,
    )
    {%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
    # Auth stores must be configured at startup (never at import time).
    # In-memory defaults are fine for local/dev; production should pass
    # Redis/SQL-backed implementations (and optionally CsrfProtection).
    from {{cookiecutter.project_name}}.identity.api_keys import (
        ApiKeyStore,
        RedisApiKeyStore,
    )
    from {{cookiecutter.project_name}}.identity.csrf import CsrfProtection
    from {{cookiecutter.project_name}}.identity.deps import configure_auth_stores
    from {{cookiecutter.project_name}}.identity.access_tokens import (
        InMemoryAccessTokenStore,
        RedisAccessTokenStore,
    )
    from {{cookiecutter.project_name}}.identity.session import (
        RedisSessionStore,
        SessionStore,
    )
    from {{cookiecutter.project_name}}.identity.service_accounts import (
        ServiceAccountRegistry,
    )
    from {{cookiecutter.project_name}}.identity.tenant_context import (
        InMemoryMembershipRegistry,
    )
    from {{cookiecutter.project_name}}.platform.tenancy import (
        configure_tenant_authorization,
    )

    _auth_backend = settings.auth_store_backend.strip().lower()
    _auth_kwargs: dict = {}
    _auth_redis = None
    if (
        _auth_backend in {"sql", "sqlalchemy", "postgres", "postgresql"}
        or (
            _auth_backend == "redis-or-sql"
            and not {{ cookiecutter.enable_redis | lower }}
        )
    ) and not {{ cookiecutter.enable_migrations | lower }}:
        raise RuntimeError(
            "SQL authentication stores require enabled migrations",
        )
    if _auth_backend in {"redis", "redis-or-sql"}:
        {%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}
        from redis import Redis as SyncRedis

        _auth_redis = SyncRedis.from_url(str(settings.redis_url))
        await asyncio.to_thread(_auth_redis.ping)
        _auth_kwargs["api_keys"] = RedisApiKeyStore(
            _auth_redis,
            prefix=f"{settings.auth_redis_prefix}:keys",
        )
        _auth_kwargs["sessions"] = RedisSessionStore(
            _auth_redis,
            prefix=settings.auth_redis_prefix,
            secret=settings.users_secret,
        )
        _auth_kwargs["access_tokens"] = RedisAccessTokenStore(
            _auth_redis,
            prefix=f"{settings.auth_redis_prefix}:access",
            lifetime_seconds=settings.session_cookie_max_age_seconds,
            secret=settings.users_secret,
        )
        {%- elif cookiecutter.orm == "sqlalchemy" %}
        if _auth_backend == "redis":
            raise RuntimeError(
                "AUTH_STORE_BACKEND=redis requires the Redis feature",
            )
        from {{cookiecutter.project_name}}.identity.access_tokens import (
            SqlAlchemyAccessTokenStore,
        )
        from {{cookiecutter.project_name}}.identity.sql_stores import (
            SqlAlchemyApiKeyStore,
            SqlAlchemySessionStore,
            create_auth_engine,
        )

        _auth_engine = create_auth_engine(str(settings.db_url))
        app.state.auth_store_engine = _auth_engine
        _auth_kwargs["api_keys"] = SqlAlchemyApiKeyStore(_auth_engine)
        _auth_kwargs["sessions"] = SqlAlchemySessionStore(
            _auth_engine,
            secret=settings.users_secret,
        )
        _auth_kwargs["access_tokens"] = SqlAlchemyAccessTokenStore(
            _auth_engine,
            secret=settings.users_secret,
        )
        {%- else %}
        raise RuntimeError(
            "AUTH_STORE_BACKEND requires Redis or SQLAlchemy persistence",
        )
        {%- endif %}
    elif _auth_backend in {"sql", "sqlalchemy", "postgres", "postgresql"}:
        {%- if cookiecutter.orm == "sqlalchemy" %}
        from {{cookiecutter.project_name}}.identity.sql_stores import (
            SqlAlchemyApiKeyStore,
            SqlAlchemySessionStore,
            create_auth_engine,
        )
        from {{cookiecutter.project_name}}.identity.access_tokens import (
            SqlAlchemyAccessTokenStore,
        )

        _auth_engine = create_auth_engine(str(settings.db_url))
        app.state.auth_store_engine = _auth_engine
        _auth_kwargs["api_keys"] = SqlAlchemyApiKeyStore(_auth_engine)
        _auth_kwargs["sessions"] = SqlAlchemySessionStore(
            _auth_engine,
            secret=settings.users_secret,
        )
        _auth_kwargs["access_tokens"] = SqlAlchemyAccessTokenStore(
            _auth_engine,
            secret=settings.users_secret,
        )
        {%- else %}
        raise RuntimeError(
            "AUTH_STORE_BACKEND=sql requires the SQLAlchemy ORM profile",
        )
        {%- endif %}
    elif _auth_backend == "memory" and settings.environment.lower() in {
        "development",
        "dev",
        "test",
    }:
        _auth_kwargs["api_keys"] = ApiKeyStore()
        _auth_kwargs["sessions"] = SessionStore()
        _auth_kwargs["access_tokens"] = InMemoryAccessTokenStore()
    else:
        raise RuntimeError(
            "production authentication cannot use the in-memory auth store",
        )
    _auth_kwargs["service_accounts"] = ServiceAccountRegistry()
    _membership_resolver = InMemoryMembershipRegistry()
    if settings.environment.lower() in {"prod", "production", "staging"}:
        {%- if cookiecutter.orm == "sqlalchemy" %}
        from sqlalchemy import select
        from {{cookiecutter.project_name}}.db.models.users import User
        from {{cookiecutter.project_name}}.identity.sql_stores import (
            SqlAlchemyMembershipResolver,
            create_auth_engine,
        )

        _status_engine = getattr(app.state, "auth_store_engine", None)
        if _status_engine is None:
            _status_engine = create_auth_engine(str(settings.db_url))
            app.state.auth_status_engine = _status_engine

        def _account_is_active(user_id: str) -> bool:
            try:
                with _status_engine.connect() as connection:
                    value = connection.execute(
                        select(User.is_active).where(User.id == user_id),
                    ).scalar_one_or_none()
                return value is True
            except Exception:
                logging.getLogger(__name__).exception(
                    "Account status lookup failed",
                )
                return False

        _auth_kwargs["account_active_checker"] = _account_is_active
        _membership_resolver = SqlAlchemyMembershipResolver(_status_engine)
        {%- else %}
        raise RuntimeError(
            "production identity requires the SQLAlchemy user adapter",
        )
        {%- endif %}
    _users_secret = getattr(settings, "users_secret", "") or ""
    if len(_users_secret.encode("utf-8")) >= 32:
        _auth_kwargs["csrf"] = CsrfProtection(_users_secret)
    configure_auth_stores(**_auth_kwargs)
    app.state.access_token_store = _auth_kwargs["access_tokens"]
    if _auth_backend in {"sql", "sqlalchemy", "postgres", "postgresql"}:
        from sqlalchemy import text

        await asyncio.to_thread(
            _verify_auth_schema,
            app.state.auth_store_engine,
            text("SELECT 1 FROM auth_session WHERE 1 = 0"),
        )
    configure_tenant_authorization(
        memberships=_membership_resolver,
    )
    {%- endif %}
    {%- if cookiecutter.enable_idempotency in [True, "True", "true", 1, "1"] %}
    {%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}
    from redis import Redis as SyncRedis
    from {{cookiecutter.project_name}}.core.idempotency import (
        RedisIdempotencyStore,
        set_idempotency_store,
    )
    _idempotency_redis = SyncRedis.from_url(str(settings.redis_url))
    await asyncio.to_thread(_idempotency_redis.ping)
    app.state.idempotency_redis = _idempotency_redis
    set_idempotency_store(RedisIdempotencyStore(_idempotency_redis))
    {%- else %}
    if settings.environment.lower() in {"prod", "production", "staging"}:
        raise RuntimeError(
            "production idempotency requires the Redis feature",
        )
    {%- endif %}
    {%- endif %}
    {%- if cookiecutter.enable_taskiq in [True, "True", "true", 1, "1"] %}
    if not broker.is_worker_process:
        await broker.startup()
    {%- endif %}
    {%- if cookiecutter.orm == "sqlalchemy" %}
    _setup_db(app)
    {%- elif cookiecutter.orm == "ormar" %}
    await database.connect()
    {%- elif cookiecutter.orm in ["beanie", "psycopg"] %}
    await _setup_db(app)
    {%- endif %}
    {%- if cookiecutter.db_info.name != "none" and cookiecutter.enable_migrations not in [True, "True", "true", 1, "1"] %}
    {%- if cookiecutter.orm in ["ormar", "sqlalchemy"] %}
    await _create_tables()
    {%- endif %}
    {%- endif %}
    {%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}
    init_redis(app)
    {%- if cookiecutter.enable_agents in [True, "True", "true", 1, "1"] %}
    from {{cookiecutter.project_name}}.platform.state import RedisStateStore

    # Agent checkpoints and idempotency claims share the durable Redis
    # boundary; request handlers derive tenant-scoped checkpoint adapters.
    app.state.state_store = RedisStateStore(
        Redis(connection_pool=app.state.redis_pool),
    )
    {%- endif %}
    {%- if cookiecutter.enable_audit in [True, "True", "true", 1, "1"] %}
    from {{cookiecutter.project_name}}.platform.audit import (
        RedisAuditSink,
        configure_audit_logger,
    )

    configure_audit_logger(
        RedisAuditSink(Redis(connection_pool=app.state.redis_pool)),
    )
    {%- endif %}
    {%- endif %}
    {%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] %}
    await init_rmq(app)
    {%- endif %}
    {%- if cookiecutter.enable_kafka in [True, "True", "true", 1, "1"] %}
    await init_kafka(app)
    {%- endif %}
    {%- if cookiecutter.enable_nats in [True, "True", "true", 1, "1"] %}
    await init_nats(app)
    {%- endif %}
    {%- if cookiecutter.enable_rag_traditional in [True, "True", "true", 1, "1"] %}
    # Compose the provider-neutral answer service at startup. Optional
    # providers may be absent in local environments; keep the route explicit
    # about that state rather than failing application import/startup.
    try:
        _embedding_provider = get_embedding_provider(
            getattr(settings, "embedding_provider", "local"),
        )
        _hybrid_retriever = HybridRetriever(
            embeddings=_embedding_provider,
            store=InMemoryVectorStore(),
        )
        _router = get_router()
        _route = _router.for_task("default")
        answer_cache = (
            RedisAnswerCache(Redis(connection_pool=app.state.redis_pool))
            if hasattr(app.state, "redis_pool")
            else None
        )
        app.state.rag_service = RAGAnswerService(
            retriever=HybridRetrievalAdapter(_hybrid_retriever),
            model=ChatModelAdapter(
                _router.model_for("default"),
                provider=_route.provider,
                model_name=_route.model,
                router=_router,
            ),
            cache=answer_cache,
        )
    except (ImportError, RuntimeError, ValueError) as exc:
        logging.getLogger(__name__).warning(
            "RAG service unavailable until providers are configured: %s",
            exc,
        )
        app.state.rag_service = None
    {%- endif %}
    _register_runtime_readiness(app)
    {%- if cookiecutter.otlp_enabled in [True, "True", "true", 1, "1"] %}
    setup_opentelemetry(app)
    {%- endif %}
    app.state.startup_complete = True
    app.middleware_stack = app.build_middleware_stack()

    try:
        yield
    finally:
        app.state.startup_complete = False
        app.state.shutdown_state.trigger(reason="lifespan_exit")
        await app.state.shutdown_state.shutdown()
        try:
            {%- if cookiecutter.orm not in ["sqlalchemy", "ormar", "psycopg"] and cookiecutter.enable_taskiq not in [True, "True", "true", 1, "1"] and cookiecutter.enable_redis not in [True, "True", "true", 1, "1"] and cookiecutter.enable_rmq not in [True, "True", "true", 1, "1"] and cookiecutter.enable_kafka not in [True, "True", "true", 1, "1"] and cookiecutter.enable_nats not in [True, "True", "true", 1, "1"] %}
            pass
            {%- endif %}
            {%- if cookiecutter.enable_taskiq in [True, "True", "true", 1, "1"] %}
            if not broker.is_worker_process:
                try:
                    await broker.shutdown()
                except Exception:
                    logging.getLogger(__name__).exception("Task broker shutdown failed")
            {%- endif %}
            if hasattr(app.state, "auth_store_engine"):
                try:
                    app.state.auth_store_engine.dispose()
                except Exception:
                    logging.getLogger(__name__).exception(
                        "Auth store shutdown failed",
                    )
            if hasattr(app.state, "auth_status_engine"):
                try:
                    app.state.auth_status_engine.dispose()
                except Exception:
                    logging.getLogger(__name__).exception(
                        "Auth status shutdown failed",
                    )
            {%- if cookiecutter.orm == "sqlalchemy" %}
            try:
                await app.state.db_engine.dispose()
            except Exception:
                logging.getLogger(__name__).exception("Database shutdown failed")
            {% elif cookiecutter.orm == "ormar" %}
            try:
                await database.disconnect()
            except Exception:
                logging.getLogger(__name__).exception("Database shutdown failed")
            {%- elif cookiecutter.orm == "psycopg" %}
            try:
                await app.state.db_pool.close()
            except Exception:
                logging.getLogger(__name__).exception("Database shutdown failed")
            {%- endif %}
            {%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}
            try:
                await shutdown_redis(app)
            except Exception:
                logging.getLogger(__name__).exception("Redis shutdown failed")
            {%- endif %}
            {%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] %}
            try:
                await shutdown_rmq(app)
            except Exception:
                logging.getLogger(__name__).exception("RabbitMQ shutdown failed")
            {%- endif %}
            {%- if cookiecutter.enable_kafka in [True, "True", "true", 1, "1"] %}
            try:
                await shutdown_kafka(app)
            except Exception:
                logging.getLogger(__name__).exception("Kafka shutdown failed")
            {%- endif %}
            {%- if cookiecutter.enable_nats in [True, "True", "true", 1, "1"] %}
            try:
                await shutdown_nats(app)
            except Exception:
                logging.getLogger(__name__).exception("NATS shutdown failed")
            {%- endif %}
        finally:
            {%- if cookiecutter.otlp_enabled in [True, "True", "true", 1, "1"] %}
            stop_opentelemetry(app)
            {%- else %}
            pass
            {%- endif %}
