<!-- Getting Started · updated 2026-08-27 · status: active -->

# Getting Started — 5 minutes

[← INDEX](INDEX.md)

NK Backend OS aims for a Next.js-style loop: **create → sync → doctor → check → dev → build**.

## 1. Create

From this generator repo (or a published install):

```bash
uv sync
uv run python -m fastapi_template create \
  --quiet --force \
  --profile saas \
  -n my_app
```

Profiles: `minimal` · `saas` · `ai-saas` · `agentic` · `fintech`

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
# open http://localhost:8000/api/docs
```

- `minimal` (no DB/redis) uses uvicorn only
- `saas+` starts Docker Compose (`docker-compose.yml` + `docker-compose.dev.yml`)
- Force app-only: `uv run nk dev --app-only`

## 4. Production image

```bash
uv run nk build
```

## 5. Scaffold a module

```bash
uv run nk generate crm.leads --fields name:str email:str
```

## Next reading

- Architecture → [02-architecture.md](02-architecture.md)
- Conventions → [03-conventions.md](03-conventions.md)
- Deploy → [04-deployment.md](04-deployment.md)
