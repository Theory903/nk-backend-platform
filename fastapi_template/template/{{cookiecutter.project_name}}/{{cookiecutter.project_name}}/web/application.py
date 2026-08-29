import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
{%- if cookiecutter.add_users == "True" and cookiecutter.orm in ['sqlalchemy', 'beanie'] %}
from {{cookiecutter.project_name}}.api.scim import register_scim
{%- endif %}
from {{cookiecutter.project_name}}.core.errors import register_problem_handlers
from {{cookiecutter.project_name}}.settings import settings
from {{cookiecutter.project_name}}.web.api.router import api_router
from {{cookiecutter.project_name}}.web.middleware.request_id import RequestIdMiddleware
from {{cookiecutter.project_name}}.web.middleware.security_headers import (
    SecurityHeadersMiddleware,
)
{%- if cookiecutter.enable_idempotency == "True" %}
from {{cookiecutter.project_name}}.web.middleware.idempotency import IdempotencyMiddleware
{%- endif %}

{%- if cookiecutter.api_type == 'graphql' %}
from {{cookiecutter.project_name}}.web.gql.router import gql_router

{%- endif %}

from {{cookiecutter.project_name}}.web.lifespan import lifespan_setup

{%- if cookiecutter.orm == 'tortoise' %}
from tortoise.contrib.fastapi import register_tortoise
from {{cookiecutter.project_name}}.db.config import TORTOISE_CONFIG

{%- endif %}

{%- if cookiecutter.sentry_enabled == "True" %}
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

{%- if cookiecutter.orm == "sqlalchemy" %}
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

{%- endif %}
{%- endif %}

{%- if cookiecutter.enable_loguru == "True" %}
from {{cookiecutter.project_name}}.log import configure_logging

{%- endif %}

APP_ROOT = Path(__file__).parent.parent


def get_app() -> FastAPI:
    """
    Get FastAPI application.

    This is the main constructor of an application.

    :return: application.
    """
    {%- if cookiecutter.enable_loguru == "True" %}
    configure_logging()
    {%- endif %}
    {%- if cookiecutter.sentry_enabled == "True" %}
    if settings.sentry_dsn:
        # Enables sentry integration.
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=settings.sentry_sample_rate,
            environment=settings.environment,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                LoggingIntegration(
                    level=logging.getLevelName(
                        settings.log_level.value,
                    ),
                    event_level=logging.ERROR,
                ),
                {%- if cookiecutter.orm == "sqlalchemy" %}
                SqlalchemyIntegration(),
                {%- endif %}
            ],
        )
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
    app.state.self_hosted_swagger = {{ cookiecutter.self_hosted_swagger == "True" }}

    # Main router for the API.
    app.include_router(router=api_router, prefix="/api")
    register_problem_handlers(app)
    {%- if cookiecutter.add_users == "True" and cookiecutter.orm in ['sqlalchemy', 'beanie'] %}
    register_scim(app)
    {%- endif %}
    {%- if cookiecutter.add_users == "True" %}
    from {{cookiecutter.project_name}}.identity.deps import CurrentUser
    from {{cookiecutter.project_name}}.platform.files.router import build_files_router

    app.include_router(
        build_files_router(current_user_dep=CurrentUser),
    )
    {%- endif %}
    {%- if cookiecutter.api_type == 'graphql' %}
    # Graphql router
    app.include_router(router=gql_router, prefix="/graphql")
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
        {%- if cookiecutter.enable_migrations != "True" %}
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
    {%- if cookiecutter.enable_idempotency == "True" %}
    app.add_middleware(IdempotencyMiddleware)
    {%- endif %}
    # app.add_middleware(AuthMiddleware)  # when available: after security, before idempotency
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
    app.add_middleware(RequestIdMiddleware)

    return app
