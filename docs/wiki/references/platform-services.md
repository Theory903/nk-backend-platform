---
id: platform-services
title: Platform services and integrations
description: Data, queues, files, webhooks, and platform service boundaries.
---

[← INDEX](../INDEX.md)

The template keeps business code behind protocols and adapters. Feature
selection controls which modules are rendered; dependency availability and
runtime configuration still determine whether a service can start.

## Data access

Database-enabled projects provide repository and unit-of-work contracts under
`data/`, with adapters for SQLAlchemy, Mongo/Beanie, and optional ORM packages.
Shared reliability primitives include:

- soft-delete and optimistic-locking helpers;
- transactional outbox and event emission;
- query/runtime abstractions;
- PostgreSQL row-level security helpers.

Run migrations only when the generated project enables them. Validate schema
and RLS behavior against the actual database engine, not only the in-memory
tests.

## Cache, locks, and queues

Redis-backed state and lock stores live under `core/`, `stores/`, and
`services/redis/`. RabbitMQ, Kafka, and NATS are optional service adapters
under `services/` with matching API examples when enabled.

Task processing uses the `TaskEnqueuer` contract in `jobs/__init__.py`:

```text
enqueue → circuit breaker → bounded retry/backoff → broker
                                      └──────────→ DLQ
```

The default DLQ is in-memory and process-local. Configure
`RedisDeadLetterQueue` or another shared implementation for multi-worker
replay and restart recovery. For business events, the transactional outbox is
the primary durability path.

## Files and object storage

The files platform is composed from `platform/files/`. Treat local storage and
URL generation as development behavior until upload, download authorization,
expiry, and object-store integration are verified in the target deployment.
File metadata must be tenant-scoped and protected by the same authorization
flow as other business data.

## Webhooks

`integrations/webhooks/` signs payloads and performs bounded HTTP delivery with
timeouts and exponential backoff. A production delivery store must make
successful event recording idempotent and must protect secrets. Endpoint
allowlists, SSRF controls, replay handling, and durable delivery state belong
in the deployment-specific implementation.

## Audit, billing, notifications, and fintech

The platform includes contracts or baseline implementations for:

- audit events and security events;
- notifications;
- billing and entitlements;
- idempotency keys;
- fintech ledger and compliance primitives.

The `fintech` profile enables the ledger-oriented package, but compliance
policy is not automatically certified. Review KYC, AML, reporting, audit
retention, reconciliation, and approval behavior before production use.

## Service replacement checklist

Before declaring an integration production-ready:

1. Select a durable implementation in `platform.yaml`.
2. Configure credentials through the deployment environment or secret manager.
3. Verify health/readiness behavior and timeout/retry limits.
4. Test tenant and authorization boundaries.
5. Run failure, restart, replay, and duplicate-delivery tests.
6. Link the application-specific contract tests from its own documentation.

## Evidence

- Data contracts: generated `data/protocols.py`, `data/models.py`
- Queue/DLQ: generated `jobs/__init__.py`
- Files: generated `platform/files/`
- Webhooks: generated `integrations/webhooks/`
- Fintech: generated `industry/fintech/`
- Contract tests: generated `tests/test_stores_contract.py`,
  `test_jobs_dlq.py`, `test_webhook_signing.py`, and `test_files_module.py`

