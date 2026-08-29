# Production Deliverables — Master Execution Plan

<!-- title: Production Deliverables · status: ACTIVE -->
<!-- structure: Epic → Task → Subtask, each with acceptance criteria + test spec -->

## Legend
- **Epic** = major work stream
- **Task** = one PR-sized deliverable
- **Subtask** = implementation step within a task
- **AC** = Acceptance Criteria (testable conditions)
- **Dep** = blocking prerequisite
- Every AC must be verifiable by running a command — not "looks good"

---

# EPIC 1: Observability Foundation

> Without structured logs + trace_id + metrics, debugging later phases is guesswork.

---

## TASK 1.1 — Structured JSON Logging + trace_id

**Dep:** None | **Effort:** 4h

- [ ] 1.1a Create `core/logging.py` — stdlib JSON formatter, trace_id from contextvars, log_format setting
- [ ] 1.1b Extend RequestIdMiddleware to set request.state.trace_id
- [ ] 1.1c Wire configure_logging() in web/application.py
- [ ] 1.1d Add settings: `log_format: str = "json"` (json|text)

### Acceptance Criteria
- AC: When LOG_FORMAT=json, every line is valid JSON parseable by `jq .`
- AC: Every line has trace_id field
- AC: When LOG_FORMAT=text, human-readable
- AC: LOG_LEVEL=DEBUG shows debug; WARNING hides them
- Test file: `tests/test_core_logging.py`

---

## TASK 1.2 — SIGTERM Graceful Drain

**Dep:** None | **Effort:** 2h

- [ ] 1.2a Register SIGTERM/SIGINT handler that stops accepting new connections
- [ ] 1.2b Drain in-flight requests (wait up to configurable `drain_timeout_s=30`)
- [ ] 1.2c Run cleanup hooks (close DB pools, flush buffers)
- [ ] 1.2d Mark /ready as 503 immediately on signal received

### Acceptance Criteria
- AC: Send SIGTERM → server returns 503 on /ready within 100ms
- AC: In-flight requests complete before process exits
- AC: No connection reset errors during rolling deploy simulation
- Test file: `tests/test_graceful_shutdown.py`

---

## TASK 1.3 — Security Headers Middleware

**Dep:** None | **Effort:** 2h

- [ ] 1.3a Create `web/middleware/security_headers.py`
  - HSTS: `Strict-Transport-Security: max-age=31536000; includeSubDomains`
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: DENY
  - Referrer-Policy: strict-origin-when-cross-origin
  - Content-Security-Policy (configurable)
- [ ] 1.3b Wire into application.py after RequestIdMiddleware
- [ ] 1.3c Add CORS middleware with explicit origin allowlist from settings

### Acceptance Criteria
- AC: Every response includes HSTS, nosniff, frame-deny headers
- AC: CSP header present and configurable via settings
- AC: CORS only allows origins listed in CORS_ORIGINS setting
- AC: Preflight OPTIONS requests handled correctly
- Test file: `tests/test_security_headers.py`

---

## TASK 1.4 — Custom Metrics Registration

**Dep:** None | **Effort:** 3h

- [ ] 1.4a Create `operations/metrics.py` exposing typed metric helpers
  - Counter: `http_requests_total{method,path,status}`
  - Histogram: `http_request_duration_seconds{method,path}`
  - Gauge: `active_sessions`, `queue_depth`, `db_pool_size`
- [ ] 1.4b Auto-instrument FastAPI routes when prometheus_enabled
- [ ] 1.4b Expose `/api/metrics` endpoint (prometheus format)

### Acceptance Criteria
- AC: GET /api/metrics returns valid Prometheus exposition format
- AC: http_requests_total increments after each request
- AC: Duration histogram buckets are present
- Test file: `tests/test_metrics.py`

---

# EPIC 2: Data Layer Hardening

> Makes persistence production-safe: idempotency, pagination, tenancy, soft-delete.

---

## TASK 2.1 — Idempotency-Key Middleware (Stripe-style)

**Dep:** Epic 1 | **Effort:** 6h

- [ ] 2.1a Create `core/idempotency.py`
  - Store interface: `IdempotencyStore.get(key) -> stored_response | None`, `.set(key, response, ttl_s)`
  - InMemoryIdempotencyStore (dev) + RedisIdempotencyStore (prod, same protocol)
- [ ] 2.1b Create `web/middleware/idempotency.py`
  - Only applies to POST/PATCH/PUT methods
  - Reads `Idempotency-Key` header; if absent → pass through normally
  - If key exists and method+path match → return cached response with header `Idempotent-Replayed: true`
  - If key exists but method/path differ → return 409 Conflict
  - If key is new → acquire lock (SETNX), execute handler, store response, release lock
  - TTL configurable (`idempotency_ttl_s = 86400`)
- [ ] 2.1c Gate behind feature flag or always-on for unsafe methods
- [ ] 2.1d Add PG-backed durable constraint option (unique index on key column) for financial ops

### Acceptance Criteria
- AC: Same Idempotency-Key + same body → second call returns cached response with replay header
- AC: Same key + different body → 409 Conflict
- AC: Different key → normal execution
- AC: No header → normal execution
- AC: Concurrent requests with same key → exactly one executes, others wait then get cached result
- AC: Key expires after TTL → next request re-executes
- Test file: `tests/test_idempotency_middleware.py`

---

## TASK 2.2 — Cursor Pagination

**Dep:** None | **Effort:** 4h

- [ ] 2.2a Create `core/pagination.py`
  - `CursorPage[T]`: `{items: list[T], next_cursor: str | None, has_more: bool}`
  - Cursor encoding: base64 of `(sort_field, sort_direction, last_id)` opaque token
  - `encode_cursor()` / `decode_cursor()` helpers
  - SQLAlchemy cursor-based query builder mixin
- [ ] 2.2b Repository[T] gains `list_cursor(cursor, limit, order_by) -> CursorPage[T]`
- [ ] 2.2c FastAPI dependency `PaginationParams` accepting `?cursor=&limit=`

### Acceptance Criteria
- AC: First page returns items + next_cursor
- AC: Passing next_cursor returns next page without duplicates or gaps
- AC: Last page has has_more=false and next_cursor=null
- AC: Stable under concurrent inserts (no items skipped between pages)
- AC: Malformed cursor → 422 Problem detail
- Test file: `tests/test_cursor_pagination.py`

---

## TASK 2.3 — Soft-Delete Mixin

**Dep:** None | **Effort:** 2h

- [ ] 2.3a Create `data/soft_delete.py`
  - `SoftDeleteMixin`: adds `deleted_at: Mapped[datetime | None]`
  - Default scope excludes deleted records automatically
  - `restore(id)` method sets deleted_at back to None
  - `hard_delete(id)` actually removes the row
- [ ] 2.3b Integrate into SqlalchemyRepository as opt-in per model
- [ ] 2.3c Audit trail records soft-delete events

### Acceptance Criteria
- AC: Soft-deleted record excluded from list() and get() by default
- AC: `include_deleted=True` flag returns them
- AC: restore() makes record visible again
- AC: hard_delete() permanently removes
- Test file: `tests/test_soft_delete.py`

---

## TASK 2.4 — Optimistic Locking (version column)

**Dep:** None | **Effort:** 2h

- [ ] 2.4a Create `data/optimistic_lock.py`
  - `VersionedMixin`: adds `version: Mapped[int]` defaulting to 1
  - On update: WHERE version = current_version AND SET version = current_version + 1
  - Zero rows updated → raise `ConcurrencyConflictError` (maps to HTTP 409)
  - ETag support: ETag = version number; If-Match header checked before update
- [ ] 2.4b Integrate into repository update()

### Acceptance Criteria
- AC: Two concurrent updates with same version → first succeeds, second gets ConcurrencyConflictError(409)
- AC: Response includes ETag header matching current version
- AC: If-Match with wrong version → 409 Problem
- Test file: `tests/test_optimistic_locking.py`

---

## TASK 2.5 — Row-Level Security (RLS) Tenant Isolation

**Dep:** Task 2.1 | **Effort:** 6h

- [ ] 2.5a Create `data/rls.py`
  - DDL generator: `ENABLE ROW LEVEL SECURITY` + `FORCE` + policies on tenant-scoped tables
  - Session context: `SELECT set_config('app.tenant_id', :org_id, true)` inside transaction
  - Non-superuser role enforcement
- [ ] 2.5b Integrate into UoW: every transaction sets tenant_id GUC
- [ ] 2.5c Negative contract tests mandatory:
  - Cross-tenant read → 0 rows
  - Cross-tenant write → rejected
- [ ] 2.5d Schema-per-tenant and DB-per-tenant documented as enterprise profiles

### Acceptance Criteria
- AC: Tenant A cannot SELECT Tenant B's rows even with direct SQL
- AC: Tenant A cannot INSERT with Tenant B's org_id (RLS policy blocks)
- AC: RLS is FORCE'd (table owner also subject to policy)
- AC: Connection pool does not leak tenant context across requests
- Test file: `tests/test_rls_isolation.py` (requires real Postgres)

---

## TASK 2.6 — Outbox emit() Convenience API

**Dep:** Existing outbox | **Effort:** 3h

- [ ] 2.6a Create `core/events/emitter.py`
  - `await events.emit(type, source, data, session=session)` — one-liner wrapping record_event
  - Auto-generates CloudEvents envelope with unique ID
  - Supports both sync and async contexts
- [ ] 2.6b Mongo-side outbox test (currently only SA tested)
- [ ] 2.6c Backlog metric exported to Prometheus: `outbox_pending_count`

### Acceptance Criteria
- AC: `await events.emit("order.created", "/orders", {"id": "1"}, session=s)` writes one outbox row
- AC: Outbox relay publishes and marks published_at
- AC: Crash-relay-restart → at-least-once delivery (no loss)
- AC: `outbox_pending_count` gauge visible in /api/metrics
- Test file: `tests/test_outbox_emit.py`

---

## TASK 2.7 — emit() + Webhook Signer (Standard Webhooks spec)

**Dep:** Task 2.6 | **Effort:** 4h

- [ ] 2.7a Create `integrations/webhooks/signer.py`
  - HMAC-SHA256 signature per Standard Webhooks spec
  - Headers: `webhook-id`, `webhook-timestamp`, `webhook-signature`
  - Verify function for consumers
- [ ] 2.7b Delivery queue with exponential retry + DLQ after max retries
- [ ] 2.7c Endpoint registration API: URL + secret + event types filter

### Acceptance Criteria
- AC: Signature verifies using Standard Webhooks verification library
- AC: Failed delivery retries 3 times with backoff, then goes to DLQ
- AC: Endpoint receives correct headers
- Test file: `tests/test_webhook_signing.py`

---

## TASK 2.8 — Redis-Backed Distributed State Stores

**Dep:** stores/base.py protocols | **Effort:** 6h

- [ ] 2.8a Implement `RedisExpiringStore(ExpiringStore)` using redis.asyncio
- [ ] 2.8b Implement `RedisSetStore(SetStore)`
- [ ] 2.8c Implement `RedisCounterStore(CounterStore)`
- [ ] 2.8d Factory: `get_store(backend="memory"|"redis")` reads from settings
- [ ] 2.8e Contract tests: SAME tests run against both InMemory and Redis implementations

### Acceptance Criteria
- AC: Same test suite passes against InMemory and Redis backends
- AC: Redis store survives process restart (data persisted)
- AC: TTL works correctly on Redis backend
- AC: Switching backends requires zero consumer code changes
- Test file: `tests/test_stores_contract.py` (parametrized)

---

## TASK 2.9 — Distributed Locks (SET NX EX with ownership)

**Dep:** Task 2.8 | **Effort:** 3h

- [ ] 2.9a Create `core/locks.py`
  - `async with distributed_lock(key, ttl_s=30):` context manager
  - Acquire: SET key random_token NX EX ttl
  - Release: Lua script checks ownership before DEL
  - Auto-release on TTL expiry (crash safety)
- [ ] 2.9b Used by: cache rebuilds, singleton workers, migrations

### Acceptance Criteria
- AC: Two concurrent acquisitions of same lock → only one succeeds
- AC: Lock auto-releases after TTL even if holder crashes
- AC: Release only works if you own the lock (token check)
- AC: Context manager releases on exit (normal or exception)
- Test file: `tests/test_distributed_locks.py`

---

# EPIC 3: Developer Velocity Framework

> Kills boilerplate so business modules stay thin.

---

## TASK 3.1 — CrudService[T] + crud_router()

**Dep:** Epic 1, 2.2 | **Effort:** 8h

- [ ] 3.1a Create `core/crud.py`
  - `CrudService[ModelT, CreateSchemaT, UpdateSchemaT]` generic base class
    - list(cursor, limit, filters) → CursorPage
    - get(id) → ModelT or raises NotFound Problem
    - create(data, user, org) → ModelT
    - update(id, data, user, org) → ModelT
    - delete(id, user, org) → bool (soft-delete if enabled)
  - Hooks: `before_create(data, ctx)`, `after_create(obj, ctx)`, etc.
  - Auto-wires: authz check, org scoping, audit event, idempotency
- [ ] 3.1b Create `core/crud_router.py`
  - `crud_router(service, prefix, schemas, permissions)` → APIRouter
  - Generates: GET /, GET /{id}, POST /, PATCH /{id}, DELETE /{id}
  - Each route has: CurrentUser dep, RequirePermission, pagination params, problem responses
  - OpenAPI tags, operation_ids auto-generated
- [ ] 3.1c Org-scoped repository base class

### Acceptance Criteria
- AC: A CRUD module can be built with <15 lines of domain code
- AC: Generated routes have OpenAPI docs with proper schemas
- AC: Unauthorized access → 401; insufficient permission → 403
- AC: Cross-org resource access → 403
- AC: Pagination uses cursor by default
- AC: Idempotency-Key on POST prevents duplicates
- AC: Audit event emitted on create/update/delete
- Test file: `tests/test_crud_framework.py` — full integration test

---

## TASK 3.2 — Module Scaffolding Generator (`nk generate module`)

**Dep:** Task 3.1 | **Effort:** 4h

- [ ] 3.2a Add `nk generate module crm.leads` CLI command
  - Creates: `business/modules/crm/leads/{__init__,models,schemas,service,router}.py`
  - Pre-wires CrudService + crud_router with sensible defaults
  - Adds router to api_router automatically
  - Generates test file skeleton
- [ ] 3.2b `nk generate crud Customer` shorthand for single-entity module

### Acceptance Criteria
- AC: `nk generate module crm.leads` creates all files without error
- AC: Generated module passes linting immediately
- AC: Generated test passes (skeleton assertions)
- AC: Router appears in OpenAPI docs
- Test file: factory-level test in generator suite

---

## TASK 3.3 — nk doctor / validate / seed Commands

**Dep:** None | **Effort:** 4h

- [ ] 3.3a `nk doctor` — checks environment health
  - uv/git/docker installed?
  - Python version compatible?
  - Required services reachable (db, redis)?
  - platform.yaml valid?
  - Dependencies resolved?
  - Exit non-zero on failure (CI gate)
- [ ] 3.3b `nk validate` — validates generated project structure
  - No broken imports
  - conditional_files pruning left no orphans
  - platform.yaml modules match actual directories
- [ ] 3.3c `nk seed demo` — populates dev database with realistic fixtures

### Acceptance Criteria
- AC: `nk doctor` exits 0 when all services healthy, 1 when any fails
- AC: Missing DB shows actionable message ("start postgres: docker compose up db")
- AC: `nk validate` catches broken imports introduced by manual deletion
- AC: `nk seed demo` populates database with ≥10 records
- Test file: `tests/test_cli_commands.py`

---

# EPIC 4: AI Completion

> Finishes what P4-P6 started: full AI surface with evaluation and GraphRAG.

---

## TASK 4.1 — Prompt Management Registry

**Dep:** None | **Effort:** 4h

- [ ] 4.1a Create `ai/prompts/registry.py`
  - Versioned prompts: `PromptTemplate(name, version, template, variables)`
  - `render(name, version, **kwargs) -> str`
  - Templates stored as Python constants (no external service needed initially)
  - A/B testing hook: `render(name, variant="b")`
- [ ] 4.1b Type-checked variables via Pydantic models

### Acceptance Criteria
- AC: Missing variable raises clear error at render time
- AC: Version pinning works (`render("summarize", version=2)`)
- AC: Unknown prompt name raises helpful error listing available prompts
- Test file: `tests/test_prompt_registry.py`

---

## TASK 4.2 — Evaluation Harness

**Dep:** Task 4.1 | **Effort:** 6h

- [ ] 4.2a Expand `agents/evaluation/__init__.py`
  - Dataset loading from YAML files
  - LLM-as-judge evaluator (uses ChatModel to score outputs)
  - Retrieval evaluation: precision@k, recall@k against labeled ground truth
  - Agent trajectory evaluation: did agent call expected tools in expected order?
- [ ] 4.2b CLI command: `nk eval --dataset eval/samples.yaml`

### Acceptance Criteria
- AC: Evaluation produces structured report with per-case pass/fail + scores
- AC: LLM-judge returns consistent scores (temperature=0)
- AC: Regression detected when known-good case starts failing
- Test file: `tests/test_evaluation.py`

---

## TASK 4.3 — pgvector Integration (real, not stub)

**Dep:** saas profile with postgresql | **Effort:** 6h

- [ ] 4.3a Create `ai/knowledge/pgvector_store.py` implementing VectorStore protocol
  - Uses pgvector.sqlalchemy.Vector column type
  - HNSW index creation (cosine distance)
  - Cosine top-k search query
  - Hybrid search: vector results UNION FTS results → RRF fusion
- [ ] 4.3b Migration: creates extension + table + index
- [ ] 4.3c Contract test: insert embeddings, verify cosine ordering matches expected

### Acceptance Criteria
- AC: pgvector extension enabled in migration
- AC: Insert 100 vectors → cosine top-k returns correctly ordered results
- AC: Hybrid search returns fused ranking (not just dense-only)
- AC: Index used (verify via EXPLAIN ANALYZE)
- Test file: `tests/test_pgvector_store.py` (requires postgres with pgvector)

---

## TASK 4.4 — Agentic RAG Loop (CRAG-style)

**Dep:** Task 4.3, agents runtime | **Effort:** 6h

- [ ] 4.4a Create `agents/agentic_rag.py`
  - Plan: LLM decides whether retrieval is needed
  - Retrieve: calls HybridRetriever.search()
  - Grade: LLM evaluates retrieved chunks for relevance
  - Re-retrieve: if graded poor → reformulate query → retrieve again
  - Generate: final answer with citations
  - Budget-limited: max_retrieval_rounds config
- [ ] 4.4b Exposed as an agent tool: `retrieve_and_answer(query)`

### Acceptance Criteria
- AC: Simple queries answered directly without retrieval round
- AC: Complex queries trigger retrieve→grade→re-retrieve loop
- AC: Loop terminates within max_retrieval_rounds budget
- AC: Citations attached to answer chunks
- Test file: `tests/test_agentic_rag.py`

---

# EPIC 5: Platform Modules

> The product Lego library: files, notifications, billing hooks.

---

## TASK 5.1 — Files Module (S3/MinIO/local behind ObjectStore)

**Dep:** None | **Effort:** 6h

- [ ] 5.1a Implement `S3ObjectStore(ObjectStore)` using boto3
  - put/get/delete/presigned_put_url/presigned_get_url
  - Configurable bucket, region, endpoint (MinIO-compatible)
- [ ] 5.1b File upload API: POST multipart → store → return key + presigned download URL
- [ ] 5.1c File metadata tracking (size, content_type, uploaded_by, org_id)
- [ ] 5.1d LocalObjectStore already exists — wire through factory

### Acceptance Criteria
- AC: Upload 1MB file → stored, downloadable via presigned URL
- AC: Presigned URL expires after configured TTL
- AC: Delete removes object
- AC: Files scoped to org (cross-org access → 403)
- Test file: `tests/test_files_module.py` (local + MinIO integration)

---

## TASK 5.2 — Notifications Module

**Dep:** None | **Effort:** 6h

- [ ] 5.2a Protocol: `NotificationChannel.send(recipient, subject, body, **meta)`
- [ ] 5.2b Email channel: SMTP adapter (stdlib smtplib) + optional SendGrid adapter
- [ ] 5.2c In-app notification store (DB-backed, user polls or SSE)
- [ ] 5.2d Template rendering using prompt registry (TASK 4.1)
- [ ] 5.2e Notification preferences per user (email on/off, digest frequency)

### Acceptance Criteria
- AC: send_email(to, subject, body) delivers via SMTP (mocked in tests)
- AC: In-app notifications appear in GET /notifications
- AC: User can disable email notifications
- AC: Template renders with variables
- Test file: `tests/test_notifications.py`

---

## TASK 5.3 — Billing Hook Layer (Stripe-ready)

**Dep:** Task 2.1 (idempotency) | **Effort:** 8h

- [ ] 5.3a Protocol: `BillingProvider.create_customer/subscription/invoice/webhook_verify`
- [ ] 5.3b Stripe adapter using official stripe-python SDK (optional dep)
- [ ] 5.3c Subscription state machine: trialing → active → past_due → canceled
- [ ] 5.3d Entitlement checking: `billing.has_entitlement(org_id, feature)` gates features
- [ ] 5.3e Webhook handler: signature verification + event processing + outbox emission
- [ ] 5.3f Usage metering: record_usage(org_id, metric, quantity) → periodic aggregation

### Acceptance Criteria
- AC: create_subscription returns Stripe subscription ID (mocked in tests)
- AC: Webhook signature verified before processing
- AC: Expired subscription blocks gated features
- AC: Usage recorded and queryable per org per period
- Test file: `tests/test_billing_module.py`

---

# EPIC 6: Industry Pack — FinTech

> First pack because it forces correctness everywhere.

---

## TASK 6.1 — Double-Entry Ledger

**Dep:** Epic 2 | **Effort:** 12h

- [ ] 6.1a Create `industry/fintech/ledger/models.py`
  - Account: id, org_id, currency, type (asset/liability/equity/revenue/expense)
  - JournalEntry: immutable, append-only
  - LedgerLine: entry_id, account_id, amount_minor (integer), direction (debit/credit)
- [ ] 6.1b Create `industry/fintech/ledger/service.py`
  - `post_transaction(lines: list[LedgerLine])` — validates debits == credits
  - Balance computation per account
  - Account statement generation (paginated history)
  - NO update/delete on journal entries (append-only invariant enforced at DB level)
- [ ] 6.1c Money as integer minor units (cents/paise) — never float
- [ ] 6.1d Idempotent posting via external reference key
- [ ] 6.1e Maker-checker: transactions above threshold require approval workflow step

### Acceptance Criteria
- AC: post_transaction with unbalanced lines raises ValidationError
- AC: Balanced transaction persists atomically (all lines or none)
- AC: Account balance = sum of debit - sum of credit lines
- AC: Duplicate external_reference rejected (idempotency)
- AC: Cannot UPDATE or DELETE journal entries (DB constraint + service layer guard)
- AC: Amount overflow (> bigint max minor units) rejected
- Test file: `tests/test_fintech_ledger.py` — comprehensive double-entry invariant tests

---

## TASK 6.2 — Limits + Compliance Primitives

**Dep:** Task 6.1 | **Effort:** 6h

- [ ] 6.2a Per-account/per-org daily/monthly transaction limits
- [ ] 6.2b KYC/KYB status flags gating high-value operations
- [ ] 6.2c AML screening hook (pluggable checker, stub impl)
- [ ] 6.2d Regulatory reporting: daily transaction summary export
- [ ] 6.2e Immutable audit trail linking all financial operations to security events

### Acceptance Criteria
- AC: Transaction exceeding limit → blocked with clear error
- AC: Unverified KYC blocks transactions above threshold
- AC: Daily summary generates correct totals
- Test file: `tests/test_fintech_compliance.py`

---

# EPIC 7: DevOps & Operations

> Production deployment readiness.

---

## TASK 7.1 — Multi-stage Dockerfile Optimization

**Dep:** None | **Effort:** 3h

- [ ] 7.1a Builder stage: install deps with uv, compile wheels
- [ ] 7.1b Runtime stage: copy only site-packages + source, no build tools
- [ ] 7.1c Non-root user
- [ ] 7.1d HEALTHCHECK directive hitting /api/health
- [ ] 7.1e Build args for profile selection
- [ ] 7.1f Image size target: <200MB for minimal profile

### Acceptance Criteria
- AC: docker build completes successfully
- AC: Container runs as non-root user
- AC: HEALTHCHECK passes
- AC: Image size <200MB for minimal profile
- Verification: `docker images | grep <project>` size check

---

## TASK 7.2 — CI/CD Pipeline (GitHub Actions)

**Dep:** Task 7.1 | **Effort:** 6h

- [ ] 7.2a Lint job: ruff + mypy on PR
- [ ] 7.2b Unit test job: pytest with SQLite + InMemory stores (no Docker needed)
- [ ] 7.2c Integration test job: pytest with Docker Compose (Postgres + Redis + MinIO)
- [ ] 7.2d Profile matrix test: generate all 5 profiles, assert valid structure
- [ ] 7.2e Security scan: pip-audit + trivy container scan
- [ ] 7.2f Build + push image on main merge (tagged with SHA)
- [ ] 7.2g Deploy staging on main merge, deploy prod on tag push

### Acceptance Criteria
- AC: PR pipeline runs all jobs green before merge allowed
- AC: Integration tests catch import breakage from feature pruning
- AC: Security scan reports zero critical vulnerabilities
- AC: Staging deploy automatic on merge to main
- Verification: GitHub Actions run shows green pipeline

---

## TASK 7.3 — Kubernetes Manifests (Helm chart)

**Dep:** Task 7.1 | **Effort:** 8h

- [ ] 7.3a Helm chart with values.yaml per profile
- [ ] 7.3b Deployment: liveness/readiness probes, resource limits, pod anti-affinity
- [ ] 7.3c HorizontalPodAutoscaler: CPU/memory-based scaling
- [ ] 7.3d Service + Ingress with TLS termination
- [ ] 7.3e Secrets mounted from K8s secrets (never baked into image)
- [ ] 7.3f Worker deployment separate from API deployment
- [ ] 7.3g Migration Job runs before Deployment rollout

### Acceptance Criteria
- AC: helm install succeeds on kind/minikube
- AC: Pods become Ready with passing probes
- AC: HPA scales on load
- AC: Worker pods scale independently from API pods
- AC: Rolling update causes zero downtime
- Verification: kubectl get pods, kubectl describe hpa

---

# EPIC 8: Documentation & Onboarding

> A developer should be productive in <10 minutes.

---

## TASK 8.1 — Getting Started Guide

**Dep:** All above | **Effort:** 4h

- [ ] 8.1a Quickstart: pip install → generate → run → test in <5 commands
- [ ] 8.1b Architecture overview with diagram
- [ ] 8.1c Configuration reference (all settings explained)
- [ ] 8.1d Adding a new module walkthrough
- [ ] 8.1e Authentication setup guide (JWT/OAuth/API keys/MFA)
- [ ] 8.1f Deployment guide (Docker + K8s)

---

## TASK 8.2 — API Reference (auto-generated)

**Dep:** None | **Effort:** 2h

- [ ] 8.2a OpenAPI schema is the source of truth (FastAPI generates it)
- [ ] 8.2b ReDoc served at /api/redoc with branding
- [ ] 8.2c AsyncAPI document generated from event registry

### Acceptance Criteria
- AC: Every endpoint documented in OpenAPI with request/response schemas
- AC: Error responses use RFC 9457 problem+json schema
- Verification: GET /api/openapi.json returns valid schema

---

## EXECUTION ORDER & DEPENDENCY GRAPH

```
EPIC 1 ──────────────────────────────────────────────────────┐
  1.1 logging → 1.2 drain → 1.3 headers → 1.4 metrics       │
                                                             │
EPIC 2 ──────────────────────────────────────────────────────┤
  2.1 idempotency → 2.7 webhooks                             │
  2.2 pagination → 3.1 crud                                  │
  2.3 soft-delete ─┐                                         │
  2.4 optimistic  ─┤→ 2.5 RLS                                │
  2.6 outbox emit → 2.7 webhooks                             │
  2.8 redis stores → 2.9 locks                               │
                                                             │
EPIC 3 ──────────────────────────────────────────────────────┤
  3.1 crud ←── depends on 1.x, 2.2                           │
  3.2 generate ←── depends on 3.1                            │
  3.3 doctor/seed ←── independent                            │
                                                             │
EPIC 4 ──────────────────────────────────────────────────────┤
  4.1 prompts → 4.2 evaluation                               │
  4.3 pgvector                                               │
  4.4 agentic rag ←── depends on 4.3 + agents                │
                                                             │
EPIC 5 ──────────────────────────────────────────────────────┤
  5.1 files                                                  │
  5.2 notifications                                          │
  5.3 billing ←── depends on 2.1 idempotency                 │
                                                             │
EPIC 6 ──────────────────────────────────────────────────────┤
  6.1 ledger ←── depends on Epic 2                           │
  6.2 compliance ←── depends on 6.1                          │
                                                             │
EPIC 7 ──────────────────────────────────────────────────────┤
  7.1 docker → 7.2 CI/CD → 7.3 K8s                          │
                                                             │
EPIC 8 ──────────────────────────────────────────────────────┘
  8.1 docs, 8.2 API reference — last, after all features stable
```

---

## DEFINITION OF DONE FOR THE ENTIRE PLATFORM

A generated project is **production-ready** when ALL of these pass:

1. `uv sync --locked` installs cleanly on Python 3.12
2. Minimal profile boots with zero optional deps
3. Every enabled profile generates valid code without manual repair
4. Generated project passes full pytest suite green
5. Provider adapters swap via config without changing business logic
6. AI/agent features remain completely optional
7. SQL and Mongo implementations satisfy identical contracts
8. Failures are observable (structured logs, metrics, traces) and recoverable (retry/DLQ/outbox)
9. Modules enable/disable without manual import repair
10. Real application builds from template without modifying foundation
11. Cross-tenant access denied at DB level (RLS)
12. Idempotent operations safe to retry
13. All auth methods tested against production-like setup
14. Key rotation completes without downtime
15. Account suspension cascades to all active sessions/tokens/keys
16. Docker image <200MB for minimal profile
17. CI pipeline green including integration + security scans
18. K8s deployment scales under load with zero downtime rolling updates
