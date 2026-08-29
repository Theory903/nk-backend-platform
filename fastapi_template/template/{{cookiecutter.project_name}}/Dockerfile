# syntax=docker/dockerfile:1.7

# ============================================================================
# Stage 1: uv
# ============================================================================

FROM ghcr.io/astral-sh/uv:0.11.7-python3.12-trixie AS uv


# ============================================================================
# Stage 2: React documentation assets
# ============================================================================

FROM node:22-alpine AS frontend

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ .
RUN npm run build


# ============================================================================
# Stage 3: production
# ============================================================================

FROM python:3.12-slim-trixie AS prod

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/usr/local \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_MANAGED_PYTHON=1

WORKDIR /app/src


# ---------------------------------------------------------------------------
# Runtime/build dependencies
# ---------------------------------------------------------------------------

{%- if cookiecutter.db_info.name == "mysql" %}

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        default-libmysqlclient-dev \
        gcc \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

{%- elif cookiecutter.db_info.name == "postgresql" %}

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
    && rm -rf /var/lib/apt/lists/*

{%- endif %}


# ---------------------------------------------------------------------------
# Dependency layer
# ---------------------------------------------------------------------------

RUN --mount=from=uv,source=/usr/local/bin/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --no-install-project --no-dev


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

COPY . .
COPY --from=frontend /app/{{cookiecutter.project_name}}/static/studio/dist ./{{cookiecutter.project_name}}/static/studio/dist


# Install project itself.
RUN --mount=from=uv,source=/usr/local/bin/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev


# ---------------------------------------------------------------------------
# Runtime user
# ---------------------------------------------------------------------------

RUN useradd \
        --create-home \
        --uid 10001 \
        --shell /usr/sbin/nologin \
        appuser \
    && mkdir -p /db_data \
    && chown -R appuser:appuser /app /db_data

USER appuser


# ---------------------------------------------------------------------------
# Application configuration
# ---------------------------------------------------------------------------

{%- if cookiecutter.orm == 'piccolo' %}

ENV PICCOLO_CONF="{{cookiecutter.project_name}}.piccolo_conf"

{%- endif %}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

HEALTHCHECK \
    --interval=30s \
    --timeout=3s \
    --start-period=10s \
    --retries=3 \
    CMD python -c \
        "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('{{cookiecutter.project_name | upper}}_PORT', '8000') + '/api/health')" \
        || exit 1


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------

CMD ["/usr/local/bin/python", "-m", "{{cookiecutter.project_name}}"]


# ============================================================================
# Stage 4: development
# ============================================================================

FROM prod AS dev

USER root

RUN --mount=from=uv,source=/usr/local/bin/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --all-groups

USER appuser