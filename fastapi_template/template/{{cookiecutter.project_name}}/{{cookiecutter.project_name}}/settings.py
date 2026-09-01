import os
import enum
from pathlib import Path
from tempfile import gettempdir
from typing import List, Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from yarl import URL

TEMP_DIR = Path(gettempdir())

class LogLevel(enum.StrEnum):
    """Possible log levels."""

    NOTSET = "NOTSET"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    FATAL = "FATAL"


class Settings(BaseSettings):
    """
    Application settings.

    These parameters can be configured
    with environment variables.
    """

    host: str = "127.0.0.1"
    port: int = 8000
    # quantity of workers for uvicorn
    workers_count: int = 1
    # Enable uvicorn reloading
    reload: bool = False
    readiness_timeout_s: float = 2.0
    shutdown_drain_timeout_s: float = 30.0
    shutdown_cleanup_timeout_s: float = 15.0

    # Current environment. Production deployments should set this explicitly
    # through the Compose/Kubernetes environment rather than relying on the
    # local-development default.
    environment: str = "development"

    # Request-plane security. Keep the host and origin lists explicit; an
    # empty CORS list denies browser cross-origin access.
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver", "test"]
    cors_allowed_origins: list[str] = []
    cors_allow_credentials: bool = False
    secure_cookies: bool = True
    max_request_body_bytes: int = 10 * 1024 * 1024
    auth_token_ttl_seconds: int = 900
    session_cookie_max_age_seconds: int = 86_400
    auth_store_backend: str = "memory"
    auth_redis_prefix: str = "nk:session"
    metrics_auth_token: str | None = None
    security_identity_enabled: bool = {{ cookiecutter.add_users in [True, "True", "true", 1, "1"] }}
    security_require_auth: bool = {{ cookiecutter.add_users in [True, "True", "true", 1, "1"] }}

    log_level: LogLevel = LogLevel.INFO
    log_format: str = "json"
    service_version: str = "0.1.0"
    service_role: str = "api"
    llm_provider: str = "ollama"
    llm_model: str = "llama3.2"
    llm_timeout_s: float = 30.0
    llm_max_retries: int = 1
    llm_cost_budget_usd: float | None = None

    # Reverse-proxy trust + browser security headers.
    # trusted_proxy_count > 0 allows X-Forwarded-Proto for HSTS detection.
    # Keep 0 unless the app sits behind a trusted proxy/LB.
    trusted_proxy_count: int = 0
    hsts_max_age: int = 31536000
    hsts_include_subdomains: bool = True
    hsts_preload: bool = False
    # None → SecurityHeadersMiddleware DEFAULT_CSP
    security_csp: Optional[str] = None

    {%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
    {%- if cookiecutter.orm == "sqlalchemy" %}
    users_secret: str = os.getenv(
        "{{cookiecutter.project_name | upper}}_USERS_SECRET",
        "",
    )
    {%- endif %}
    {%- endif %}
    {% if cookiecutter.db_info.name != "none" -%}

    # Variables for the database
    {%- if cookiecutter.db_info.name == "sqlite" %}
    db_file: Path = TEMP_DIR / "db.sqlite3"
    {%- else %}
    db_host: str = "localhost"
    db_port: int = {{cookiecutter.db_info.port}}
    db_user: str = "{{cookiecutter.project_name}}"
    db_pass: str = "{{cookiecutter.project_name}}"  # noqa: S105
    db_base: str = "{{cookiecutter.project_name}}"
    {%- endif %}
    db_echo: bool = False

    {%- endif %}


    {%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}

    # Variables for Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_user: Optional[str] = None
    redis_pass: Optional[str] = None
    redis_base: Optional[int] = None
    redis_max_connections: int = 50

    {%- endif %}


    {%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] %}

    # Variables for RabbitMQ
    rabbit_host: str = "localhost"
    rabbit_port: int = 5672
    rabbit_user: str = "guest"
    rabbit_pass: str = "guest"  # noqa: S105
    rabbit_vhost: str = "/"

    rabbit_pool_size: int = 2
    rabbit_channel_pool_size: int = 10

    {%- endif %}


    {%- if cookiecutter.prometheus_enabled in [True, "True", "true", 1, "1"] %}

    # This variable is used to define
    # multiproc_dir. It's required for [uvi|guni]corn projects.
    prometheus_dir: Path = TEMP_DIR / "prom"

    {%- endif %}


    {%- if cookiecutter.sentry_enabled in [True, "True", "true", 1, "1"] %}

    # Sentry's configuration.
    sentry_dsn: Optional[str] = None
    sentry_error_sample_rate: float = 1.0
    sentry_traces_sample_rate: float = 0.05

    {%- endif %}


    {%- if cookiecutter.otlp_enabled in [True, "True", "true", 1, "1"] %}

    # Grpc endpoint for opentelemetry.
    # E.G. http://localhost:4317
    opentelemetry_endpoint: Optional[str] = None
    opentelemetry_trace_sample_rate: float = 0.05

    {%- endif %}

    {%- if cookiecutter.enable_kafka in [True, "True", "true", 1, "1"] %}

    kafka_bootstrap_servers: List[str] = ["localhost:9092"]
    # Producer knobs (services.kafka.lifespan). Prefer these over hard-coded
    # defaults. kafka_compression_type defaults to "lz4"; init_kafka falls
    # back to "gzip" when lz4 is unavailable. Set to None to disable.
    kafka_acks: str = "all"
    kafka_enable_idempotence: bool = True
    kafka_linger_ms: int = 5
    kafka_compression_type: Optional[str] = "lz4"
    kafka_request_timeout_ms: int = 30_000

    {%- endif %}


    {%- if cookiecutter.enable_nats in [True, "True", "true", 1, "1"] %}
    nats_servers: list[str] = ["nats://localhost:4222"]
    {%- endif %}


    {%- if cookiecutter.db_info.name != "none" %}


    @property
    def db_url(self) -> {%- if cookiecutter.db_info.name == "sqlite"
        %}str{%- else %}URL{%- endif %}:
        """
        Assemble database URL from settings.

        :return: database URL.
        """
        {%- if cookiecutter.db_info.name == "sqlite" %}
        return (
            {%- if cookiecutter.orm == "sqlalchemy" %}
            "{{cookiecutter.db_info.async_driver}}:"
            {%- elif cookiecutter.orm == "tortoise" %}
            "{{cookiecutter.db_info.driver_short}}:"
            {%- else %}
            "{{cookiecutter.db_info.driver}}:"
            {%- endif %}
            f"///{self.db_file}"
        )
        {%- else %}
        return URL.build(
            {%- if cookiecutter.orm == "sqlalchemy" %}
            scheme="{{cookiecutter.db_info.async_driver}}",
            {%- elif cookiecutter.orm == "tortoise" %}
            scheme="{{cookiecutter.db_info.driver_short}}",
            {%- else %}
            scheme="{{cookiecutter.db_info.driver}}",
            {%- endif %}
            host=self.db_host,
            port=self.db_port,
            user=self.db_user,
            password=self.db_pass,
            path=f"/{self.db_base}",
        )
        {%- endif %}
    {%- endif %}

    {%- if cookiecutter.enable_redis in [True, "True", "true", 1, "1"] %}
    @property
    def redis_url(self) -> URL:
        """
        Assemble REDIS URL from settings.

        :return: redis URL.
        """
        path = ""
        if self.redis_base is not None:
            path = f"/{self.redis_base}"
        return URL.build(
            scheme="redis",
            host=self.redis_host,
            port=self.redis_port,
            user=self.redis_user,
            password=self.redis_pass,
            path=path,
        )
    {%- endif %}

    {%- if cookiecutter.enable_rmq in [True, "True", "true", 1, "1"] %}
    @property
    def rabbit_url(self) -> URL:
        """
        Assemble RabbitMQ URL from settings.

        :return: rabbit URL.
        """
        return URL.build(
            scheme="amqp",
            host=self.rabbit_host,
            port=self.rabbit_port,
            user=self.rabbit_user,
            password=self.rabbit_pass,
            path=self.rabbit_vhost,
        )
    {%- endif %}

    model_config = SettingsConfigDict(
        env_file = ".env",
        env_prefix = "{{cookiecutter.project_name | upper }}_",
        env_file_encoding = "utf-8",
        # Compose-only keys (DB_USER/DB_PASSWORD/DB_NAME, etc.) live in .env
        # alongside prefixed app settings; ignore extras so Settings can load.
        extra = "ignore",
    )

    @model_validator(mode="after")
    def validate_security_configuration(self) -> "Settings":
        """Reject unsafe production request and credential configuration."""
        environment = self.environment.strip().lower()

        if self.max_request_body_bytes <= 0:
            raise ValueError("max_request_body_bytes must be greater than zero")
        if self.auth_token_ttl_seconds <= 0:
            raise ValueError("auth_token_ttl_seconds must be greater than zero")
        if self.session_cookie_max_age_seconds <= 0:
            raise ValueError(
                "session_cookie_max_age_seconds must be greater than zero",
            )
        if self.cors_allow_credentials and "*" in self.cors_allowed_origins:
            raise ValueError(
                "credentialed CORS cannot use the wildcard origin",
            )

        if environment in {"prod", "production", "staging"}:
            if self.reload:
                raise ValueError("reload must be disabled outside development")
            if not self.allowed_hosts or "*" in self.allowed_hosts:
                raise ValueError(
                    "production requires an explicit allowed_hosts list",
                )
            if not self.security_identity_enabled:
                raise ValueError(
                    "production requires an enabled identity provider",
                )
            if self.security_identity_enabled and not self.security_require_auth:
                raise ValueError(
                    "identity-enabled production requires authentication",
                )

            secret = getattr(self, "users_secret", "")
            if self.security_require_auth and len(secret.encode("utf-8")) < 32:
                raise ValueError(
                    "production authentication requires a 32-byte USERS_SECRET",
                )
            durable_backends = {
                "postgres",
                "postgresql",
                "redis",
                "redis-or-sql",
                "sql",
                "sqlalchemy",
            }
            if (
                self.security_require_auth
                and self.auth_store_backend.strip().lower()
                not in durable_backends
            ):
                raise ValueError(
                    "production authentication requires a durable auth store",
                )
            {%- if cookiecutter.prometheus_enabled in [True, "True", "true", 1, "1"] and cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
            if (
                not self.metrics_auth_token
                or len(self.metrics_auth_token.strip()) < 16
            ):
                raise ValueError(
                    "production metrics export requires METRICS_AUTH_TOKEN",
                )
            {%- endif %}

        return self



settings = Settings()
