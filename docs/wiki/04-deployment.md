<!-- Deployment · updated 2026-08-31 · status: active -->

# Deployment

[← INDEX](INDEX.md)

```bash
uv run nk dev      # local
uv run nk dev --reuse  # reuse existing local Compose containers
uv run nk dev --new    # start an isolated local Compose stack
uv run nk dev --otlp   # include the local telemetry overlay
uv run nk build    # docker --target prod
```

Compose files in a generated app:

- `docker-compose.yml` — base (prod target, service DNS)
- `docker-compose.dev.yml` — local ports / reload
- `docker-compose.prod.yml` — deploy overlay

CI for generated apps: `.github/workflows/tests.yml` (quality / compose pytest / prod image).

## Helm and scale stages

Generated database-backed projects include `deploy/helm/nk-backend`, with
separate API, stream, and worker workloads, path-split ingress, HPA/PDB,
NetworkPolicy, an Argo PreSync migration Job, optional KEDA, and External
Secrets hooks. Deploy progressively:

```bash
uv run nk deploy staging --image-digest sha256:<approved-image-digest>
uv run nk deploy prod-s2 --image-digest sha256:<approved-image-digest>
uv run nk scale-status
```

`S1` is the baseline production stage; `S2` enables stream/worker separation,
`S3` increases independent autoscaling, and `S4` is the high-scale topology.
S5/S6 edge and cell deployments remain opt-in after measured SLO evidence.

The chart requires a pre-created application Secret when External Secrets is
disabled and requires an immutable application image digest for staging and
production. `PrometheusRule` is opt-in because the Prometheus
Operator CRD is not assumed. API/stream/worker pods mount a writable
`/tmp/prom` volume for Prometheus multiprocess metrics despite their
read-only root filesystem.

## Production observability

When OpenTelemetry is enabled, start the self-hosted stack with:

```bash
export GRAFANA_ADMIN_PASSWORD='use-a-secret-manager-value'
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f deploy/docker-compose.otlp.yml \
  up -d --build
```

The overlay runs an OpenTelemetry Collector, Prometheus, Loki, Tempo, and
Grafana. Grafana is the only observability service published to the host;
keep the remaining services on the internal Docker networks. Use an edge
proxy with TLS and authentication before exposing Grafana outside the VPS.

Application logs are JSON lines on stdout. Traces and logs are sent to the
collector, while Prometheus scrapes the internal-only `/api/metrics` endpoint. Set
`*_OPENTELEMETRY_ENDPOINT` to the collector address and configure
`*_SENTRY_DSN` only when external exception tracking is desired.

The generated stack persists telemetry in named Docker volumes. Set
`PROMETHEUS_RETENTION`, `LOKI_RETENTION`, and `TEMPO_RETENTION` according to
disk capacity and incident-retention requirements. Replace the version-pinned
images with approved digest-pinned images in a controlled deployment process.

## Production security contract

The production Compose overlay publishes no API or infrastructure ports and
clears the broad `.env` injection used by the base stack. Supply explicit
values through a secret manager or deployment environment:

```bash
ALLOWED_HOSTS='["api.example.com"]'
CORS_ALLOWED_ORIGINS='["https://app.example.com"]'
DB_USER='service_user'
DB_PASSWORD='secret-manager-value'
DB_ADMIN_USER='migration_admin'
DB_ADMIN_PASSWORD='separate-secret-manager-value'
DB_OWNER_ROLE='service_owner'
DB_NAME='service'
USERS_SECRET='32-byte-secret-manager-value'
AUTH_STORE_BACKEND='redis-or-sql'
```

`DB_USER` is the non-superuser application role; `DB_ADMIN_USER` is used only
to initialize PostgreSQL and must never be used by the API. Production must
use an authenticated TLS edge proxy, durable identity/session
stores, and TLS/authentication for any broker crossing a trust boundary.
Compose migrations run with the admin credential, while the API and workers
run with `DB_USER`; `DB_OWNER_ROLE` is a `NOLOGIN` ownership role. For Helm,
configure `migrationSecrets.existingSecret` separately from
`secrets.existingSecret` (or provide the ExternalSecret properties
`*_DB_ADMIN_USER` and `*_DB_ADMIN_PASS`) so migration credentials are never
mounted into application pods. Pre-create the Helm `migrate.ownerRole` as a
distinct `NOLOGIN NOSUPERUSER NOBYPASSRLS` role and grant the migration
principal permission to transfer ownership to it.
Development-only plaintext ports, `guest/guest`, empty Redis passwords, and
predictable project-name database passwords are not production controls.
Cloud IAM, WAF, secret-manager access, image signing, and network policies
remain deployment-platform responsibilities; `platform.yaml` is metadata, not
an enforcement layer.

Operational checks:

- `/api/health` is a dependency-free liveness check.
- `/api/ready` verifies startup state and registered dependencies.
- `/api/build-info` identifies the running version and Git image metadata.
- `/mcp` is the agent-profile protocol endpoint and is protected by the same
  auth middleware as other non-public routes.
- Prometheus alerts cover API error rate, latency, and scrape availability.
- Worker-enabled projects must add durable broker/DLQ storage and worker
  heartbeat checks before relying on automated task recovery.
