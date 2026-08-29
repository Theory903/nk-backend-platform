# {{cookiecutter.project_name}}

This project was generated using fastapi_template.

## UV

This project uses uv. It's a modern dependency management
tool.

To run the project use this set of commands:

```bash
cd frontend
npm ci
npm run build
cd ..
uv sync
uv run -m {{cookiecutter.project_name}}
```

This will start the server on the configured host.

The React documentation app is available at `/api/docs`, with interactive
Swagger at `/api/swagger` and the reference view at `/api/redoc`.

You can read more about uv here: https://docs.astral.sh/ruff/

## Docker

Compose is split into base + overlays:

| File | Role |
| --- | --- |
| `docker-compose.yml` | Base topology (`target: prod`, internal `app` network, no DB/broker host ports) |
| `docker-compose.dev.yml` | Dev: `target: dev`, reload, source mount, API + infra host ports |
| `docker-compose.prod.yml` | Prod: reload off, no source mounts, no infra host ports |

**Development** (API on `:8000`, optional DB/Redis/broker ports for local tools):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

**Production-shaped** (no host ports for DB/Redis/brokers; put an edge proxy in front):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Service DNS inside the stack is the Compose service name (`db`, `redis`, `rmq`, `kafka`, `nats`, `api`) — not `{{cookiecutter.project_name}}-db` hostnames.

Credentials come from env (see `.env`): `DB_USER`, `DB_PASSWORD`, `DB_NAME`, and `RABBITMQ_USER` / `RABBITMQ_PASSWORD` when RabbitMQ is enabled. Override these for anything beyond local bootstrap.

Rebuild whenever `uv.lock` or `pyproject.toml` changes:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml build
```

## Project structure

```bash
$ tree "{{cookiecutter.project_name}}"
{{cookiecutter.project_name}}
├── conftest.py  # Fixtures for all tests. 
{%- if cookiecutter.db_info.name != "none" %}
├── db  # module contains db configurations
│   ├── dao  # Data Access Objects. Contains different classes to interact with database.
│   └── models  # Package contains different models for ORMs.
{%- endif %}
├── __main__.py  # Startup script. Starts uvicorn.
├── services  # Package for different external services such as rabbit or redis etc.
├── settings.py  # Main configuration settings for project.
├── static  # Static content.
├── tests  # Tests for project.
└── web  # Package contains web server. Handlers, startup config.
    ├── api  # Package with all handlers.
    │   └── router.py  # Main router.
    ├── application.py  # FastAPI application configuration.
    └── lifespan.py  # Contains actions to perform on startup and shutdown.
```

## Configuration

This application can be configured with environment variables.

You can create `.env` file in the root directory and place all
environment variables here. 

All environment variables should start with "{{cookiecutter.project_name | upper}}_" prefix.

For example if you see in your "{{cookiecutter.project_name}}/settings.py" a variable named like
`random_parameter`, you should provide the "{{cookiecutter.project_name | upper}}_RANDOM_PARAMETER" 
variable to configure the value. This behaviour can be changed by overriding `env_prefix` property
in `{{cookiecutter.project_name}}.settings.Settings.Config`.

An example of .env file:
```bash
{{cookiecutter.project_name | upper}}_RELOAD="True"
{{cookiecutter.project_name | upper}}_PORT="8000"
{{cookiecutter.project_name | upper}}_ENVIRONMENT="dev"
```

You can read more about BaseSettings class here: https://pydantic-docs.helpmanual.io/usage/settings/

{%- if cookiecutter.otlp_enabled == "True" %}
## OpenTelemetry 

If you want to start your project with OpenTelemetry collector 
you can add `-f ./deploy/docker-compose.otlp.yml` to your docker command.

Like this:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f deploy/docker-compose.otlp.yml --project-directory . up
```

This command will start grafana with full opentelemetry stack at http://localhost:3000/. 
After sending a requests you can see traces at explore tab in drilldown.

This docker configuration is not supposed to be used in production. 
It's only for demo purpose.

You can read more about OpenTelemetry here: https://opentelemetry.io/
{%- endif %}

## Pre-commit

To install pre-commit simply run inside the shell:
```bash
pre-commit install
```

Local pre-commit runs **format + lint + mypy + bandit** (ruff format may rewrite files).
CI validates only: `ruff format --check`, `ruff check` (no `--fix`), mypy, bandit, then pytest.
A generated-project matrix across cookiecutter profiles is the next CI hardening step.

By default it runs:
* ruff format (auto-formats);
* ruff check (lint only — no autofix);
* mypy (validates types);
* bandit (security scan of `{{cookiecutter.project_name}}`, excludes tests);


You can read more about pre-commit here: https://pre-commit.com/

{%- if cookiecutter.enable_migrations == 'True' %}

## Migrations

If you want to migrate your database, you should run following commands:
```bash
{%- if cookiecutter.orm in ['sqlalchemy', 'ormar'] %}
# To run all migrations until the migration with revision_id.
alembic upgrade "<revision_id>"

# To perform all pending migrations.
alembic upgrade "head"
{%- elif cookiecutter.orm == 'tortoise' %}
# Upgrade database to the last migration.
aerich upgrade

{%- elif cookiecutter.orm == 'piccolo' %}
# You have to set a PICCOLO_CONF variable
export PICCOLO_CONF="{{cookiecutter.project_name}}.piccolo_conf"
# Now you can easily run migrations using 
piccolo migrations forwards all
{%- endif %}
```

### Reverting migrations

If you want to revert migrations, you should run:
```bash
{%- if cookiecutter.orm in ['sqlalchemy', 'ormar'] %}
# revert all migrations up to: revision_id.
alembic downgrade <revision_id>

# Revert everything.
 alembic downgrade base
{%- elif cookiecutter.orm == 'tortoise' %}
aerich downgrade
{%- endif %}
```

### Migration generation

To generate migrations you should run:
```bash
{%- if cookiecutter.orm in ['sqlalchemy', 'ormar'] %}
# For automatic change detection.
alembic revision --autogenerate

# For empty file generation.
alembic revision
{%- elif cookiecutter.orm == 'tortoise' %}
aerich migrate
{%- endif %}
```
{%- endif %}


## Running tests

If you want to run it in docker, simply run:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --build --rm api pytest -vv .
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
```

For running tests on your local machine.

{%- if ((cookiecutter.db_info.name != "none" and cookiecutter.db_info.name != "sqlite") or
            (cookiecutter.enable_redis == "True") or
            (cookiecutter.enable_rmq == "True") or
            (cookiecutter.enable_kafka == "True") or
            (cookiecutter.enable_nats == "True")
) %}
1. you need to start all aux services.

We can do so with the base + dev Compose overlays (dev publishes host ports for tools):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --wait{%- if cookiecutter.db_info.name != 'none' and cookiecutter.db_info.name != 'sqlite' %} db{%- endif %}{%- if cookiecutter.enable_redis == "True" %} redis{%- endif %}{%- if cookiecutter.enable_rmq == "True" %} rmq{%- endif %}{%- if cookiecutter.enable_kafka == "True" %} kafka{%- endif %}{%- if cookiecutter.enable_nats == "True" %} nats{%- endif %}
```

2. Run tests.
```bash
pytest -vv .
```
{%- else %}
Simply run 

```bash
pytest -vv .
```
{%- endif %}

