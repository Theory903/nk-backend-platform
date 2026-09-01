---
id: production-readiness
title: Production readiness
description: Deployment, observability, and reliability checks for generated services.
---

[← INDEX](../INDEX.md)

Generated deployment files are starting points. A service is production-ready
only after the selected infrastructure, identity provider, data stores, edge
security, and operational controls are verified together.

## Deployment targets

| Target | Generated artifacts | Use |
| --- | --- | --- |
| Local | `docker-compose.yml`, `docker-compose.dev.yml` | Development and integration |
| Production Compose | `docker-compose.prod.yml`, `deploy/docker-compose.otlp.yml` | Single-host deployment |
| Kubernetes | `deploy/helm/nk-backend/`, `deploy/helm/values/` | Cluster deployment |
| App-only | Uvicorn/Gunicorn entry points | Minimal or externally managed services |

Use:

```bash
uv run nk doctor
uv run nk validate
uv run nk build
```

For Kubernetes, render and inspect the Helm output with the selected values
file before applying it. Verify migrations, worker workloads, ingress,
autoscaling, network policy, and Prometheus rules in the target cluster.

## Production security

Configure, at minimum:

- an authenticated TLS edge with an explicit host allowlist;
- explicit CORS origins;
- durable authentication/session storage;
- a 32-byte user secret from a secret manager;
- database and broker credentials outside broad `.env` injection;
- TLS and authentication for brokers crossing a trust boundary.

Do not expose database, Redis, broker, collector, or telemetry ports directly
to the public network. `platform.yaml` records generated metadata; it does
not enforce cloud IAM, WAF policy, secrets, image signing, or cluster policy.

## Observability

When enabled, the self-hosted telemetry overlay contains an OpenTelemetry
Collector, Prometheus, Loki, Tempo, and Grafana. Application logs are JSON
lines on stdout. Prometheus scrapes the internal metrics endpoint; Grafana
should be protected by the edge proxy and its administrator password should
come from a secret manager or deployment environment.

Set retention according to disk capacity and incident requirements. Replace
development image tags with approved digest-pinned images through the
deployment process.

## Readiness and failure handling

- `/api/health` is dependency-free liveness.
- `/api/ready` verifies startup state and registered dependencies.
- queue failures use bounded retries and a dead-letter path.
- business event durability uses the transactional outbox.
- agent workflows require bounded cycles, retries, cancellation, and
  checkpoint policy.
- webhook delivery requires bounded timeout/retry and idempotent recording.

The default in-memory sessions, audit, graph, and DLQ implementations are
useful for development and tests but do not survive process restart or
coordinate across workers.

## Release evidence

Before release, run the generated quality sequence:

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

Add live checks for the actual PostgreSQL/RLS, Redis, broker, object storage,
identity provider, ingress, and telemetry configuration. In-memory contract
tests alone are not sufficient evidence for a distributed deployment.

## Evidence

- Compose: generated `docker-compose*.yml`
- Helm: generated `deploy/helm/nk-backend/`
- Telemetry: generated `deploy/otel/`, `deploy/prometheus*.yml`,
  `deploy/grafana/`, `deploy/loki/`, and `deploy/tempo/`
- Generated CI: `.github/workflows/tests.yml`
- Readiness: generated `web/api/monitoring/views.py`

