<!-- Deployment · updated 2026-08-27 · status: active -->

# Deployment

[← INDEX](INDEX.md)

```bash
uv run nk dev      # local
uv run nk build    # docker --target prod
```

Compose files in a generated app:

- `docker-compose.yml` — base (prod target, service DNS)
- `docker-compose.dev.yml` — local ports / reload
- `docker-compose.prod.yml` — deploy overlay

CI for generated apps: `.github/workflows/tests.yml` (quality / compose pytest / prod image).
