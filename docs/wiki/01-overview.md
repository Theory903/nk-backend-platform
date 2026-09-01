<!-- Getting Started · updated 2026-08-27 · status: active -->

# Getting Started — 5 minutes

[← INDEX](INDEX.md)

NK Backend OS aims for a Next.js-style loop: **create → sync → doctor → check → dev → build**.

## 1. Create

From this generator repo (or a published install):

```bash
uv tool install /path/to/FastAPI-template
nk init my_app --use-case saas
```

`nk init NAME` is the Next.js-style generator command. The installed `nk`
executable can be run from any directory. For local repository development,
use `uv run nk init ...` after `uv sync`. The legacy `create` and
`fastapi_template` entry points remain supported.
Generation writes `platform.yaml` as the typed architecture contract and
creates `uv.lock` so CI can enforce reproducible dependencies.

Use cases: `minimal-api` · `saas` · `enterprise-saas` · `crud-platform` ·
`integration-api` · `data-platform` · `search-platform` ·
`knowledge-platform` · `ai-saas` · `ai-knowledge` · `agentic` ·
`automation-platform` · `event-platform` · `fintech` · `internal-tool` ·
`developer-api` · `webhook-platform` · `high-scale-api` · `custom`

Use cases select the closest profile. The current architecture profiles are
`minimal`, `saas`, `ai-saas`, `agentic`, and `fintech`; use `nk generate` to
add business-specific modules.

## 2. Install & verify

```bash
cd my_app
uv sync
uv run nk doctor
uv run nk check
```

## 3. Develop

```bash
uv run nk dev
# the CLI prints the selected /api/docs URL
```

- `minimal` (no DB/redis) uses uvicorn only
- `saas+` starts Docker Compose (`docker-compose.yml` + `docker-compose.dev.yml`)
- Force app-only: `uv run nk dev --app-only`
- Add local telemetry with `uv run nk dev --otlp` when OpenTelemetry is enabled.
- Existing Compose stacks prompt to reuse or start a new isolated stack;
  use `uv run nk dev --reuse` or `uv run nk dev --new` to choose directly.

## 4. Production image

```bash
uv run nk build
```

## 5. Scaffold a module

```bash
uv run nk generate crm.leads --fields name:str email:str
```

Generated modules under `business/modules/<domain>/<module>/` are discovered
automatically and mounted at `/api/v1/<domain>/<module>`. Agent profiles also
provide `/api/v1/runs`, `/api/v1/runs/stream`, and `/mcp`.

## Next reading

- Architecture → [02-architecture.md](02-architecture.md)
- Conventions → [03-conventions.md](03-conventions.md)
- Deploy → [04-deployment.md](04-deployment.md)
- Full service map → [EVA service catalog](references/service-catalog.md)
- Documentation site → run `cd website && npm ci && npm run start` from the
  repository root
