[![version](https://img.shields.io/pypi/v/fastapi_template?style=for-the-badge)](https://pypi.org/project/fastapi-template/)
[![downloads](https://img.shields.io/pypi/dm/fastapi_template?style=for-the-badge&color=blue)](https://pypistats.org/packages/fastapi-template)
<div align="center">
<img src="images/image.png" alt="NŌKNŌWN FastAPI Template logo" width=700>
<div><i>NK Backend OS — a create-to-production FastAPI project generator.</i></div>
</div>

## Why NK Backend OS

NK Backend OS gives every generated FastAPI service a consistent foundation
while keeping business code yours. Choose a profile, generate a project,
inspect its manifest, and use the same workflow from local development through
production.

- **Profiles:** `minimal`, `saas`, `ai-saas`, `agentic`, and `fintech`
- **Generated CLI:** `nk doctor`, `validate`, `check`, `dev`, `build`, and `generate`
- **API Studio:** one branded surface for article docs, Swagger, and ReDoc
- **Composable integrations:** databases, ORMs, Redis, brokers, task queues,
  identity, tenancy, observability, AI, and fintech modules
- **Guardrails:** typed settings, feature validation, health checks,
  idempotency, audit trails, and generated CI/Docker workflows

## Quick start

Requires [Python 3.12+](https://www.python.org/), [uv](https://docs.astral.sh/uv/),
and [Git](https://git-scm.com/downloads). Docker is required for profiles that
run supporting services.

```bash
# Install the generator's development dependencies
uv sync

# Generate a service
uv run fastapi_template create --profile saas -n my_app
cd my_app

# Install generated dependencies and run the checks
uv sync
uv run nk doctor
uv run nk check
uv run nk dev          # http://localhost:8000/api/docs
```

Build a production image with `uv run nk build`. Omit `--profile` to use the
interactive generator.

## Choose a profile

| Profile | Best for | Includes |
| --- | --- | --- |
| `minimal` | Small services and experiments | REST, example router, local-first defaults |
| `saas` | Production web APIs | PostgreSQL, SQLAlchemy, Redis, Taskiq, users, migrations, OTel |
| `ai-saas` | Retrieval-backed products | SaaS plus LLM, vector storage, and traditional RAG |
| `agentic` | Tool-using AI systems | AI SaaS plus agents, guardrails, memory, and GraphRAG |
| `fintech` | Transactional workloads | SaaS plus audit, idempotency, and fintech ledger primitives |

## Generated-project workflow

| Command | Purpose |
| --- | --- |
| `nk doctor` | Check environment, imports, and generated wiring |
| `nk validate` | Validate project structure and `platform.yaml` |
| `nk check` | Run formatting, linting, typing, and tests |
| `nk dev` | Start the local API or the development Compose stack |
| `nk build` | Build the production Docker target |
| `nk generate …` | Scaffold a business module |

Generated projects expose:

- `/api/docs` — API Studio and editorial documentation
- `/api/swagger` — interactive Swagger explorer
- `/api/redoc` — reference-oriented ReDoc view

## Install and Docker variants

Install the published generator:

```bash
python -m pip install fastapi_template
python -m fastapi_template create --profile minimal -n toy
```

Generate with Docker when you do not want a local Python environment:

```bash
docker run --rm -it -v "$(pwd):/projects" ghcr.io/s3rius/fastapi_template
```

## Repository guide

| Path | What it contains |
| --- | --- |
| `fastapi_template/` | Generator package and Cookiecutter template |
| `fastapi_template/template/…/frontend/` | Generated React API Studio |
| `docs/wiki/` | Curated architecture, conventions, deployment, and data-model docs |
| `fastapi_template/tests/` | Generator and profile contract tests |

Read the [wiki index](docs/wiki/INDEX.md) for the architecture and the
[overview](docs/wiki/01-overview.md) for the first generated-project walkthrough.

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Feature combinations are validated before Cookiecutter runs, so incompatible
database, ORM, AI, and fintech options fail with an actionable message.
