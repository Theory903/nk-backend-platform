---
id: generator
title: Generate an EVA service
description: Generate, inspect, and verify a service from the EVA FastAPI template.
---

[← INDEX](../INDEX.md)

The repository is a generator, not a single deployable API. Each invocation
creates an independent FastAPI service from the Cookiecutter template and
records the selected architecture in `platform.yaml`.

## Prerequisites

- Python 3.12 or newer
- `uv`
- Git
- Docker for profiles that start PostgreSQL, Redis, Taskiq, or telemetry

Install the generator from a checkout:

```bash
uv sync
```

For a published package, use `uv tool install fastapi-template`. The repository
also exposes the compatibility entry points `fastapi_template` and
`fastapi-template`.

## Choose a product use case

Product-first generation uses `--use-case` to select the closest existing
architecture profile:

| Use case | Current profile |
| --- | --- |
| `minimal-api` | `minimal` |
| `saas`, `enterprise-saas`, `crud-platform`, `integration-api` | `saas` |
| `data-platform`, `search-platform`, `automation-platform`, `event-platform` | `saas` |
| `knowledge-platform`, `ai-saas`, `ai-knowledge` | `ai-saas` |
| `agentic` | `agentic` |
| `fintech` | `fintech` |
| `internal-tool`, `developer-api`, `webhook-platform`, `high-scale-api` | `saas` |
| `custom` | interactive composition |

Examples:

```bash
nk init reliant --use-case enterprise-saas
nk init sampati --use-case data-platform
nk init knowledge --use-case ai-knowledge
nk init support_agent --use-case agentic
```

Use cases are intent labels and architecture starting points. They do not
automatically generate domain-specific CRM, data, search, or high-scale
modules. Add product behavior with `nk generate` and inspect the generated
`platform.yaml` before deployment.

## Choose a profile

| Profile | Intended service shape | Main capabilities |
| --- | --- | --- |
| `minimal` | Small REST service | REST router and local-first defaults |
| `saas` | Production web API | PostgreSQL/SQLAlchemy, Redis, Taskiq, users, migrations, OTel, Prometheus |
| `ai-saas` | Retrieval-backed product | `saas` plus LLM, vectors, and traditional RAG |
| `agentic` | Tool-using AI service | `ai-saas` plus bounded agents and GraphRAG |
| `fintech` | Transactional workload | `saas` plus audit, idempotency, and fintech primitives |

Profiles are deterministic presets. Explicit command-line options override
profile values; options not supplied by a profile are disabled by default.
When both selectors are supplied, an explicit `--profile` wins while the
requested use case is retained as metadata. Compatibility checks run before
Cookiecutter renders files.

## Generate

```bash
uv run nk init my_app --profile saas
cd my_app
uv sync
```

The legacy equivalent is:

```bash
uv run python -m fastapi_template create --profile saas -n my_app
```

The generated project contains:

- `platform.yaml`, the resolved architecture contract;
- the application package;
- `tests/`;
- Docker Compose and, where applicable, Helm deployment files;
- a generated `nk` CLI;
- a React API Studio source tree when the selected features require it.

## Inspect the contract

```bash
uv run nk validate
```

`validate` checks the generated structure and manifest. Treat
`platform.yaml` as metadata describing generated intent. It does not replace
cloud IAM, a WAF, a secret manager, a TLS edge, or a Kubernetes admission
policy.

## Verify before development

```bash
uv run nk doctor
uv run nk check
```

`doctor` checks environment and generated wiring. `check` runs the generated
quality checks, typing, and tests. Fix validation or doctor failures before
starting infrastructure so that the failure is local and actionable.

## Source of truth

The profile definitions and deterministic defaults live in
`fastapi_template/profiles.py`. Feature dependency validation lives in
`fastapi_template/validation.py`; the generated manifest is
`fastapi_template/template/{{cookiecutter.project_name}}/platform.yaml`.
When adding a profile capability, update those contracts and the profile
matrix tests together.

## Related references

- [CLI reference](cli.md)
- [Service catalog](service-catalog.md)
- [Deployment](../04-deployment.md)
