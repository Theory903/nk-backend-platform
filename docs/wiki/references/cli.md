---
id: cli
title: Generated CLI reference
description: Commands available in every generated EVA service.
---

[← INDEX](../INDEX.md)

After generation, run commands from the generated project root with
`uv run nk`. The implementation is
`{{cookiecutter.project_name}}/cli/__init__.py`; commands are feature-aware and
may be unavailable when their profile capability is disabled.

## Core lifecycle

| Command | Purpose |
| --- | --- |
| `nk doctor` | Check the local environment, imports, and generated wiring |
| `nk validate` | Validate project structure and `platform.yaml` |
| `nk check` | Run formatting, linting, typing, and tests |
| `nk dev` | Start the local API or development Compose stack |
| `nk build` | Build the production Docker target |
| `nk start` | Start the application process |

Typical first run:

```bash
uv sync
uv run nk doctor
uv run nk validate
uv run nk check
uv run nk dev
```

`nk dev` selects the app-only server for `minimal` projects and the Compose
stack for infrastructure-enabled projects. Use `--app-only` to avoid starting
Compose. Use `--reuse` to reuse an existing local stack or `--new` to start an
isolated one. `--otlp` adds the local OpenTelemetry overlay when enabled.

## Data and modules

| Command | Purpose |
| --- | --- |
| `nk migrate` | Apply database migrations when migrations are enabled |
| `nk seed` | Seed configured development data |
| `nk generate` | Scaffold a business module |

Example:

```bash
uv run nk generate crm.leads --fields name:str email:str
```

Generated business modules are discovered by
`{{cookiecutter.project_name}}/core/module_discovery.py` and are included in
the protected API router for supported database/ORM combinations.

## AI and operations

| Command | Purpose |
| --- | --- |
| `nk eval` | Run the configured evaluation harness |
| `nk jobs replay` | Replay visible dead-letter jobs |
| `nk deploy` | Run the generated deployment helper |
| `nk scale-status` | Inspect configured scale metadata |
| `nk worker` | Run the worker process when task processing is enabled |

Evaluation requires the relevant AI dependencies and fixtures. A successful
local run does not prove model quality or production safety; use the golden
dataset, governance thresholds, and red-team gates when those are enabled in
the generated project.

## Build and failure modes

The generated CI workflow runs the same broad sequence as a reliable local
check:

```bash
uv sync --locked
uv run nk doctor
uv run nk validate
uv run ruff format --check .
uv run ruff check .
uv run mypy <project> tests
uv run pytest -q
docker build --target prod --tag app:ci .
```

`jobs replay` uses the configured dead-letter queue. The default in-memory
queue is process-local and is lost on restart; production must configure a
shared Redis- or SQL-backed implementation.

## Implementation and tests

- CLI implementation:
  `fastapi_template/template/{{cookiecutter.project_name}}/{{cookiecutter.project_name}}/cli/__init__.py`
- Generator entry point:
  `fastapi_template/__main__.py`
- Generator CLI tests: `fastapi_template/tests/test_cli.py`
- Generated CLI tests:
  `fastapi_template/template/{{cookiecutter.project_name}}/tests/test_cli.py`

