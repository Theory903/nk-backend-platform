# GOTCHAS

- Profiles (`fastapi_template/profiles.py`) validate profile *names* only — they do not yet enforce feature dependency constraints (e.g. `enable_agents` ⇒ `enable_llm`). Next: add profile dependency validation.
- OTel compose fragment uses Docker service DNS `http://otel-stack:4317` (not a hostname alias like `otel-collector`); only Grafana `3000` is published by default; joins external `{{project}}-app` network.
- Compose is split: `docker-compose.yml` (base/prod defaults) + `docker-compose.dev.yml` + `docker-compose.prod.yml`. Infra host ports only in `.dev.yml`. Service DNS is `db`/`redis`/`rmq`/`kafka`/`nats` — not `{{project}}-db` hostnames.
- Compose credentials use `${DB_USER}` / `${DB_PASSWORD}` (with local `:-` bootstrap). Prod must override; Traefik stack + Docker secrets still not bundled.
- Many identity/session primitives are still in-memory — a container restart clears them. Next: wire durable Postgres/Redis stores for SaaS/prod profiles.
