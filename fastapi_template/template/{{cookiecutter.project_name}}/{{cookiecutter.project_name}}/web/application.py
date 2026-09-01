from pathlib import Path
import re
from typing import Any

{%- if cookiecutter.sentry_enabled in [True, "True", "true", 1, "1"] %}
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
{%- if cookiecutter.orm == 'tortoise' %}
from tortoise.contrib.fastapi import register_tortoise
from {{cookiecutter.project_name}}.db.config import TORTOISE_CONFIG
{%- endif %}
{%- if cookiecutter.orm == "sqlalchemy" %}
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
{%- endif %}
{%- endif %}
from fastapi import FastAPI
{%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
from fastapi import Depends
from {{cookiecutter.project_name}}.identity.deps import CurrentUser
{%- endif %}
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
{%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] and cookiecutter.orm in ['sqlalchemy', 'beanie'] %}
from {{cookiecutter.project_name}}.api.scim import register_scim
{%- endif %}
from {{cookiecutter.project_name}}.core.errors import register_problem_handlers
from {{cookiecutter.project_name}}.core.logging import configure_logging
from {{cookiecutter.project_name}}.settings import settings
from {{cookiecutter.project_name}}.web.api.router import api_router
from {{cookiecutter.project_name}}.web.middleware.request_id import RequestIdMiddleware
from {{cookiecutter.project_name}}.web.middleware.request_limits import (
    RequestBodyLimitMiddleware,
)
{%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.web.middleware.auth import AuthMiddleware
{%- endif %}
from {{cookiecutter.project_name}}.web.middleware.security_headers import (
    SecurityHeadersMiddleware,
)
{%- if cookiecutter.prometheus_enabled in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.web.middleware.metrics import (
    PrometheusMetricsMiddleware,
)
{%- endif %}
{%- if cookiecutter.enable_idempotency in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.web.middleware.idempotency import IdempotencyMiddleware
{%- endif %}

{%- if cookiecutter.api_type == 'graphql' %}
from {{cookiecutter.project_name}}.web.gql.router import gql_router

{%- endif %}
{%- if cookiecutter.enable_agents in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.web.api.agent_protocol import mcp_router
{%- endif %}

from {{cookiecutter.project_name}}.web.lifespan import lifespan_setup
{%- if cookiecutter.enable_loguru in [True, "True", "true", 1, "1"] %}
from {{cookiecutter.project_name}}.log import configure_logging as configure_loguru
{%- endif %}

APP_ROOT = Path(__file__).parent.parent
_sentry_initialized = False
_SENTRY_SECRET_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "cookies",
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "private_key",
        "access_key",
    }
)
_SENTRY_SECRET_TEXT = re.compile(
    r"(?i)(\b(?:password|passwd|secret|token|api[_-]?key|authorization)"
    r"\s*[:=]\s*)(?:(Bearer|Basic)\s+)?([^\s,;]+)",
)
_SENTRY_AUTH_SCHEME = re.compile(r"(?i)\b(Bearer|Basic)\s+[^\s,;]+")


def _scrub_sentry_text(value: str) -> str:
    redacted = _SENTRY_SECRET_TEXT.sub(
        lambda match: (
            f"{match.group(1)}"
            f"{match.group(2) + ' ' if match.group(2) else ''}"
            "[REDACTED]"
        ),
        value,
    )
    return _SENTRY_AUTH_SCHEME.sub(
        lambda match: f"{match.group(1)} [REDACTED]",
        redacted,
    )


def _scrub_sentry_value(value: Any, *, key: str | None = None) -> Any:
    if key is not None and key.lower().replace("-", "_") in _SENTRY_SECRET_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(child_key): _scrub_sentry_value(
                child_value,
                key=str(child_key),
            )
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [_scrub_sentry_value(item) for item in value]
    if isinstance(value, str):
        return _scrub_sentry_text(value)
    return value


def _scrub_sentry_event(
    event: Any,
    _hint: Any,
) -> Any:
    """Remove credentials and request payloads before sending to Sentry."""
    scrubbed = _scrub_sentry_value(event)
    if isinstance(scrubbed, dict):
        request = scrubbed.get("request")
        if isinstance(request, dict):
            request.pop("data", None)
            request.pop("query_string", None)
            request.pop("cookies", None)
    return scrubbed


def get_app() -> FastAPI:
    """
    Get FastAPI application.

    This is the main constructor of an application.

    :return: application.
    """
    configure_logging(
        level=settings.log_level.value,
        log_format=settings.log_format,
        environment=settings.environment,
        service="{{cookiecutter.project_name}}",
        version=settings.service_version,
        force=True,
    )
    {%- if cookiecutter.enable_loguru in [True, "True", "true", 1, "1"] %}
    configure_loguru()
    {%- endif %}
    {%- if cookiecutter.sentry_enabled in [True, "True", "true", 1, "1"] %}
    global _sentry_initialized
    if settings.sentry_dsn and not _sentry_initialized:
        # Enables sentry integration.
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            sample_rate=settings.sentry_error_sample_rate,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            environment=settings.environment,
            release=settings.service_version,
            send_default_pii=False,
            before_send=_scrub_sentry_event,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                {%- if cookiecutter.orm == "sqlalchemy" %}
                SqlalchemyIntegration(),
                {%- endif %}
            ],
        )
        _sentry_initialized = True
    {%- endif %}
    app = FastAPI(
        title="{{cookiecutter.project_name}}",
        description=(
            "NK Backend API — use the React documentation reader at `/api/docs`, "
            "the interactive Swagger view at `/api/swagger`, or the reference "
            "ReDoc view at `/api/redoc`."
        ),
        version="0.1.0",
        lifespan=lifespan_setup,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.self_hosted_swagger = {{ cookiecutter.self_hosted_swagger }}

    # Main router for the API.
    app.include_router(router=api_router, prefix="/api")
    {%- if cookiecutter.enable_agents in [True, "True", "true", 1, "1"] %}
    app.include_router(mcp_router, prefix="/mcp")
    {%- endif %}
    register_problem_handlers(app)
    {%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] and cookiecutter.orm in ['sqlalchemy', 'beanie'] %}
    register_scim(app)
    {%- endif %}
    {%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
    from {{cookiecutter.project_name}}.identity.deps import CurrentUser
    from {{cookiecutter.project_name}}.platform.files.router import build_files_router

    app.include_router(
        build_files_router(current_user_dep=CurrentUser),
    )
    {%- endif %}
    {%- if cookiecutter.api_type == 'graphql' %}
    # Graphql router
    {%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
    app.include_router(
        router=gql_router,
        prefix="/graphql",
        dependencies=[Depends(CurrentUser)],
    )
    {%- else %}
    app.include_router(router=gql_router, prefix="/graphql")
    {%- endif %}
    {%- endif %}

    # Branding + API Studio assets (always); optional self-hosted swagger bundles.
    app.mount(
        "/static",
        StaticFiles(directory=APP_ROOT / "static"),
        name="static",
    )

    {%- if cookiecutter.orm == 'tortoise' %}
    # Configures tortoise orm.
    register_tortoise(
        app,
        config=TORTOISE_CONFIG,
        add_exception_handlers=True,
    {%- if cookiecutter.enable_migrations not in [True, "True", "true", 1, "1"] %}
        generate_schemas=True,
        {%- endif %}
    )
    {%- endif %}

    # ------------------------------------------------------------------
    # Middleware stack (add_middleware is LIFO: last added = outermost).
    #
    # Request flow (outer → inner):
    #   RequestId → SecurityHeaders → [Auth/Tenant if present] →
    #   Idempotency → application
    # ------------------------------------------------------------------
    {%- if cookiecutter.enable_idempotency in [True, "True", "true", 1, "1"] %}
    app.add_middleware(IdempotencyMiddleware)
    {%- endif %}
    {%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
    if settings.security_require_auth:
        app.add_middleware(
            AuthMiddleware,
            allowed_origins=settings.cors_allowed_origins,
        )
    {%- endif %}
    _security_kwargs: dict = {
        "hsts_max_age": settings.hsts_max_age,
        "hsts_include_subdomains": settings.hsts_include_subdomains,
        "hsts_preload": settings.hsts_preload,
        "trusted_proxy_count": settings.trusted_proxy_count,
    }
    # None means "use middleware DEFAULT_CSP"; empty string disables CSP.
    if settings.security_csp is not None:
        _security_kwargs["csp"] = settings.security_csp
    app.add_middleware(SecurityHeadersMiddleware, **_security_kwargs)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_hosts,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-CSRF-Token",
            "X-Request-ID",
            "X-Org-Id",
            "X-Session-Id",
            "Idempotency-Key",
        ],
        expose_headers=["X-Request-ID", "X-Trace-ID"],
    )
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=settings.max_request_body_bytes,
    )
    app.add_middleware(RequestIdMiddleware)
    {%- if cookiecutter.prometheus_enabled in [True, "True", "true", 1, "1"] %}
    app.add_middleware(PrometheusMetricsMiddleware)
    {%- endif %}

    return app
