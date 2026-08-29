[![version](https://img.shields.io/pypi/v/fastapi_template?style=for-the-badge)](https://pypi.org/project/fastapi-template/)
[![downloads](https://img.shields.io/pypi/dm/fastapi_template?style=for-the-badge&color=blue)](https://pypistats.org/packages/fastapi-template)
<div align="center">
<img src="https://raw.githubusercontent.com/s3rius/FastAPI-template/master/images/logo.png" width=700>
<div><i>NK Backend OS — Next.js-style FastAPI framework (profiles · <code>nk</code> CLI · contracts).</i></div>
</div>

## Quick start (create → check → run)

Requires [Git](https://git-scm.com/downloads), [Python 3.12+](https://www.python.org/), and [UV](https://docs.astral.sh/uv/).

```bash
# From this repo
uv sync
uv run python -m fastapi_template create \
  --quiet --force \
  --profile saas \
  -n my_app

cd my_app
uv sync
uv run nk doctor
uv run nk check
uv run nk dev          # → http://localhost:8000/api/docs
uv run nk build        # production image
```

Profiles: `minimal` · `saas` · `ai-saas` · `agentic` · `fintech`

| Command | Purpose |
|---|---|
| `nk doctor` | Environment / import health |
| `nk validate` | Structure + manifest checks |
| `nk check` | ruff + mypy + pytest |
| `nk dev` | uvicorn (minimal) or compose (saas+) |
| `nk build` | `docker build --target prod` |
| `nk generate …` | Scaffold a business module |

Wiki: [docs/wiki/INDEX.md](docs/wiki/INDEX.md) · Getting Started: [docs/wiki/01-overview.md](docs/wiki/01-overview.md)

### Install variants

```bash
# PyPI (upstream package; use this repo for latest NK DX)
python3 -m pip install fastapi_template
python3 -m fastapi_template create --profile minimal -n toy --quiet --force

# Docker generator
docker run --rm -it -v "$(pwd):/projects" ghcr.io/s3rius/fastapi_template
```

Interactive TUI still works if you omit `--quiet`.

## Features

Configurable FastAPI factory: REST/GraphQL, SQLAlchemy/Beanie/…, Redis, Kafka, NATS, RabbitMQ, Taskiq, identity/tenancy, OTel, Prometheus, Sentry, LLM/agents (opt-in), fintech pack.

Generator CLI options (also `fastapi_template create …`):

```shell
$ python -m fastapi_template --help

Usage: fastapi_template [OPTIONS]

Options:
  -n, --name TEXT                 Name of your awesome project
  -V, --version                   Prints current version
  --force                         Overwrite directory if it exists
  --quiet                         Do not ask for features during generation
  --profile [minimal|saas|ai-saas|agentic|fintech]
                                  Apply a preset bundle of features
  --api-type [rest|graphql]       Select API type for your application
  --db [none|sqlite|mysql|postgresql|mongodb]
  --orm [none|ormar|sqlalchemy|tortoise|psycopg|piccolo|beanie]
  --ci [none|gitlab_ci|github]
  --redis / --llm / --agents / --audit / --idempotency / …
```

Invalid flag combos fail fast via `validate_context` before cookiecutter runs.
