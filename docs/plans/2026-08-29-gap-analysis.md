# NK Backend Platform — Gap Analysis

<!-- title: Gap Analysis · updated: 2026-08-29 · status: ACTIVE -->
<!-- question: What is still missing to be “Next.js for FastAPI” in production? -->
<!-- method: code + docs + generator flags; not a generic FastAPI wishlist -->

This is an inventory of **what the repo already ships** versus **what its own north star still lacks**. Sources of truth compared:

- Product framing: `docs/plans/2026-08-24-nk-system-design.md` (Next.js-for-FastAPI)
- Capability matrix: `.sisyphus/plans/gold-master-plan.md` (C1–C20, P0–P9)
- Execution backlog: `.sisyphus/plans/production-deliverables.md`
- Generated template: `fastapi_template/template/{{cookiecutter.project_name}}/`
- Generator: `fastapi_template/profiles.py`, `conditional_files.toml`, `.github/workflows/test.yml`

---

## 0. Verdict

The repo is **past a cookiecutter demo** and **not yet a framework**. A generated `saas` / `agentic` app already has a large library of protocols, tests, and opt-in modules. What is missing is the **Next.js-shaped product layer**: automatic wiring, one CLI for the full loop, durable production backends, HTTP surfaces for identity/agents/ops, and deploy-from-config.

| Layer | Status |
|---|---|
| Generator + profiles + prune | **Shipped** |
| Kernel libraries (errors, CRUD factory, pagination, DI, flags) | **Shipped as libraries** |
| Identity / data / AI / agents / fintech **code** | **Mostly present, often unwired** |
| `nk` as `create-next-app` + `next dev/build/start/deploy` | **Partial** (`doctor/validate/check/dev/build/generate` only) |
| App-Router-style module discovery | **Missing** |
| Helm / GitOps / path-split / signed images | **Missing** |
| Notifications, billing, webhook delivery, GraphRAG, MCP server | **Missing** |

If you generate `--profile saas` today you get APIs, Docker, CI lint/tests, identity **libraries**, and an OpenAPI studio. You do **not** get: auto-mounted business modules, identity-owned `/auth/*`, CORS, `/build-info`, durable sessions/audit/DLQ, Helm, or `nk deploy`.

---

## 1. Already in the repo (do not rebuild)

Keep this list so “missing” is not a generic FastAPI checklist.

**Generator**

- Profiles: `minimal` · `saas` · `ai-saas` · `agentic` · `fintech` (`fastapi_template/profiles.py`)
- Feature prune: `conditional_files.toml`
- Profile matrix CI on the generator repo (generate → `nk doctor` → lint → pytest → prod image)
- `platform.yaml` seed (project/profile/providers/modules/observability)

**Always-on-ish kernel (generated app)**

- FastAPI factory, RFC9457 problem handlers, request-id, security headers
- `/api/health` (liveness) and `/api/ready` (registry; **no default DB/broker checks registered**)
- Structured logging, graceful drain, feature flags, DI, identifiers, pagination, query allow-list
- `CrudService` + `crud_router()` factory (`core/crud.py`)
- Multi-stage Dockerfile: frontend build, non-root `appuser`, `HEALTHCHECK` on `/api/health`

**Opt-in modules with real code + tests**

- Data: `Repository[T]` + SQLAlchemy / Beanie adapters, UoW, soft-delete, optimistic lock, RLS DDL helpers, outbox + `events.emit()`
- Identity **domain**: JWT, OIDC, OAuth2, LDAP, MFA, CSRF, sessions, API keys, key rotation, RBAC, account lifecycle, SCIM **models/service**
- Jobs: TaskIQ wiring, enqueue + circuit breaker + **in-memory** DLQ
- Files: `ObjectStore` + local + S3/MinIO-shaped adapter + HTTP router
- Webhooks: Standard Webhooks **signer/verifier** only
- AI: `ChatModel` / `EmbeddingProvider` factories → any-llm + fastembed; prompt registry; hybrid retriever (in-process keyword+dense); pgvector store module
- Agents: loop + LangGraph `create_react_agent`, tools, skills, budgets, 3-layer guardrails, HITL, local workspace, MCP **client bridge**, agentic RAG, eval harness
- Fintech: double-entry ledger + limits/KYC/AML **stub** + reporting
- Frontend: React **API Studio** (OpenAPI explorer), not a product UI
- Generated CI: ruff + mypy + compose pytest + `docker build --target prod`

---

## 2. Missing for “Next.js for FastAPI” (the product gap)

These are the items that make Next.js feel like a framework. Without them, NK is a rich template, not a paved road.

### 2.1 CLI parity (`nk` vs `next`)

| Next.js | Promised | Actual | Gap |
|---|---|---|---|
| `npx create-next-app` | `nk init my-app --profile …` | `python -m fastapi_template create` (generator package still named `fastapi_template`) | No first-class `nk` **generator** CLI; PyPI still points at upstream s3rius |
| `next dev` | `nk dev` | Implemented (compose or uvicorn) | OK |
| `next build` | `nk build` | Docker `--target prod` only | No SBOM, no provenance, no lockfile guaranteed at generate time |
| `next start` | `nk start` | **Missing** | No prod entry verb |
| — | `nk migrate` | **Missing** | Alembic exists; no CLI wrapper / PreSync story |
| — | `nk seed` | **Missing** | Production-deliverables TASK 3.3c |
| — | `nk deploy staging\|prod` | **Missing** | No Helm/Argo wrapper |
| — | `nk generate module` | Files only | Does **not** mount the router; `_service_factory` is `NotImplementedError` |
| — | `nk generate agent` / `integration` / `client` | **Missing** | Documented in system design §16.1 |
| — | `nk eval` | **Missing** | Eval harness code exists; no CLI |
| — | `nk jobs replay` | **Missing** | DLQ has no replay command |
| — | `nk scale-status` | **Missing** | S0–S6 ladder is docs-only |
| — | `nk doctor` in **generated** CI as a required gate | Doctor exists; baked-app workflow does not run `nk check` / doctor | Weak day-2 loop |

### 2.2 App Router equivalent — modules do not auto-wire

North star (`system-design` §0.3 / §0.8): put `business/modules/crm/leads/router.py` on disk → framework mounts `GET /api/v1/crm/leads`.

**Reality**

- `web/api/router.py` is a **hand-written Jinja list** of echo/dummy/redis/kafka/nats/users.
- `nk generate` writes `business/modules/...` and prints “import router in `web/api/router.py`”.
- No package discovery, no entry points, no `@resource` convention, no `/api/v1` version prefix.
- Generated `service_factory` raises `NotImplementedError` — scaffold is not runnable.

This is the largest DX miss. It is why the product still feels like copy-paste FastAPI.

### 2.3 `platform.yaml` is a stub, not `next.config`

Shipped file: project, profile, a few providers, module bools, observability flags.

**Missing target fields** (system-design §0.5)

- `framework.version`
- `scale.stage` (S0–S6) and Helm value selection
- `providers.cache` / `identity` / `llm` / `vector` / `workflow`
- `observability.sampling_ratio`
- `deploy.path_split_stream`
- Overlay / patch layers (dsh-style profile → home → `--patch`)
- Runtime bootstrap that **reads** this file as the single switch (lifespan still Jinja + settings)

`nk doctor` does not validate the target schema. `nk deploy` cannot map `scale.stage` → values because those files do not exist.

### 2.4 Batteries that are documented as “always on” but are not

From system-design §0.4 / §0.7:

| Promise | Reality |
|---|---|
| CORS allowlist | **No `CORSMiddleware`** in `web/application.py` (studio even hints CORS may fail) |
| Auth on every route except allowlist | `AuthMiddleware` is **commented out**; identity is opt-in fastapi-users routes |
| `/build-info` with `GIT_SHA` | **Missing** |
| Readiness after pool warmup | `/ready` registry exists; **nothing registers DB/Redis/broker** in lifespan |
| Idempotency on mutations | Only if `enable_idempotency` (fintech profile); not saas default |
| Outbox for domain events | Only when ORM is sqlalchemy/beanie; no first-class `emit` in CRUD hooks by default |
| Tenant filter applied in repository automatically | Tenancy service exists; `get_membership_registry()` **raises `NotImplementedError`**; startup does not call `configure_tenant_authorization` |
| Structured JSON logs + `trace_id` | Logging module exists; Loguru path is still a separate flag |

---

## 3. Missing HTTP surfaces (libraries without a product API)

These modules exist as Python packages and unit tests, but a generated app does not expose the routes the docs promise.

### 3.1 Identity-owned auth API

`web/api/users/views.py` still mounts **fastapi-users** and documents the missing identity HTTP surface:

- `/auth/register`, `/auth/login`, `/auth/logout`, `/auth/refresh`
- `/auth/password/*`, `/auth/mfa/*`, `/auth/oauth/*`
- `/auth/sessions/*`, `/auth/api-keys/*`

Until this ships, JWT/session/key-rotation/MFA are **libraries**, not a drop-in auth product.

### 3.2 SCIM

Router + filter/patch/service exist. `api/scim.py` `get_scim_service()` **raises `NotImplementedError`**. Provisioning from Okta/Entra will 500 unless the consumer wires DI.

### 3.3 Agent Protocol / MCP server

- No `/api/v1/runs`, `/threads`, `/store` (C9 / agent-protocol).
- No `/mcp` Streamable HTTP resource server (gold G5).
- `agents/mcp_bridge.py` is a **client** adapter (caller supplies session + runner). Not an MCP server, not `MultiServerMCPClient`.

### 3.4 Ops plane (C10 / twitter-server)

Present: `/api/health`, `/api/ready`, optional `/api/metrics`.

Missing:

- `/build-info` (`GIT_SHA`, `BUILD_DATE`, profile)
- Auth’d `/ops/log-level`, `/ops/quitquitquit`, runtime toggles/tunables
- Self-registering admin index (`Route(alias, group)`)
- Owned metric names (`nk_http_requests_total`, queue lag, DLQ, LLM cost, guardrail trips)
- PrometheusRule / SLO burn alerts
- `deploy/otel/collector-config.yaml`

### 3.5 Fintech HTTP

Ledger service + `industry/fintech/api/ledger_router.py` exist. Confirm they are **not** included from `web/api/router.py` (same manual-mount problem). Maker-checker approve endpoint is scoped, not a first-class platform route.

---

## 4. Capability matrix (C1–C20) — missing or stubbed

Gold-master §4. Status is against **generated production path**, not unit tests.

| # | Capability | Status | Missing |
|---|---|---|---|
| C1 | LLM gateway | Partial | Chat/complete only. No responses/messages/moderation/batch/image/speech/transcription. Factory is any-llm or error — no routing YAML, no degrade/fallback. |
| C2 | Embeddings | Partial | Dense FastEmbed only. No sparse / late-interaction / image modes. |
| C3 | Hybrid retrieval | Partial | In-process keyword+vector fusion. No Postgres FTS + RRF, no cross-encoder rerank, no Qdrant adapter, no citation pipeline as HTTP. `enable_rag_traditional` prunes **zero files**. |
| C4 | Ranking scorer | **Missing** | No `Ranker`, no weighted signals, no dual-window usage grammar. |
| C5 | Agent runtime | Partial | `loop` + `graph` (LangGraph). No `pydantic` engine. Graph checkpointer not Postgres-default. |
| C6 | Tools + MCP | Partial | Registry + schema-gen exist. MCP is inbound bridge only. No curated execute/fetch/http tools as defaults. |
| C7 | Skills / plugins | Partial | SKILL.md loader exists. No 3-role seam, no waterfall `next()`, no open-webui pipe convention. |
| C8 | Memory | Partial | In-app memory module. No LangGraph Store + embed search, no session-log “model-visible ⟺ logged” invariant. |
| C9 | Sessions/runs HTTP | **Missing** | See §3.3. |
| C10 | Ops/admin | Partial | See §3.4. |
| C11 | Config kernel | Partial | `BaseConfig` exists. No patch layers, no `resolve(request): Spec`, `platform.yaml` too thin. |
| C12 | Identity & tenancy | Partial | Rich local/OIDC/LDAP **code**. HTTP still fastapi-users. Membership/RLS not bootstrapped. No schema-per-tenant / DB-per-tenant. SCIM unwired. |
| C13 | Audit + idempotency | Partial | Idempotency middleware + in-memory/Redis-shaped stores. Audit **sink ABC**; default is in-memory (lost on restart). |
| C14 | Sandbox / workspace | Partial | `LocalWorkspace` only. No docker / E2B / Modal / network-deny sandbox. |
| C15 | Workflows | Partial | In-process `WorkflowRunner` (retry + compensate + callback HITL). No LangGraph StateGraph defs, no Temporal/DBOS/Hatchet, no durable journal. |
| C16 | Knowledge ingestion | **Missing** | No load→chunk→embed→index pipeline for PDF/DOCX/URL. Chunker exists; no loaders (Docling/Tika/pypdf). |
| C17 | Multimodal | **Missing** | No image/STT/TTS/vision surface. |
| C18 | Eval + usage analytics | Partial | Prompt eval + usage module. No `nk eval` CLI, no token/cost dashboards, no dual-window aggregations. |
| C19 | Jobs + reliability | Partial | Enqueue + in-memory DLQ. No Redis/SQL DLQ, no replay CLI, no chaos “kill worker → DLQ” drill in CI. |
| C20 | Web research tools | **Missing** | No SearXNG/fetch_url/browse tools. |

**Flags with empty prune lists** (declared, no files):

- `enable_rag_traditional` → `resources = []`
- `enable_graphrag` → `resources = []` — **GraphRAG / LightRAG is entirely missing**
- `sentry_enabled` → `resources = []` (wired in application.py when flag set; no extra files)

---

## 5. Production-deliverables backlog still open

Checked against `.sisyphus/plans/production-deliverables.md` (checkboxes were never marked done). Code-level status:

| Task | Status |
|---|---|
| 1.1 JSON logging + trace_id | Present |
| 1.2 SIGTERM drain | Present |
| 1.3 Security headers | Present |
| 1.3 CORS allowlist | **Missing** |
| 1.4 Custom metrics | Present if Prometheus flag |
| 2.1 Idempotency middleware | Present (profile-gated) |
| 2.2 Cursor pagination | Present |
| 2.3 Soft-delete | Present |
| 2.4 Optimistic locking | Present |
| 2.5 RLS | DDL + helpers; **not applied as default migrations / FORCE in generated schema**; isolation tests exist |
| 2.6 Outbox `emit()` | Present |
| 2.7 Webhook **delivery** (retry + DLQ + registration API) | **Missing** (signer only) |
| 2.8 Redis stores | Present + contract tests |
| 2.9 Distributed locks | Present |
| 3.1 CrudService + crud_router | Present as library |
| 3.2 `nk generate` auto-wire + OpenAPI | **Incomplete** |
| 3.3 `nk seed` | **Missing** |
| 4.1 Prompt registry | Present |
| 4.2 Evaluation CLI | Code yes, CLI **no** |
| 4.3 pgvector real + EXPLAIN | Module + tests; hybrid FTS/RRF **weak** |
| 4.4 Agentic RAG | Present (library) |
| 5.1 Files S3/local | Present |
| 5.2 Notifications (email + in-app + prefs) | **Missing entire module** |
| 5.3 Billing / Stripe / entitlements | **Missing entire module** |
| 6.1 Ledger | Present |
| 6.2 Compliance | Present with **allow-all AML stub** |
| 7.1 Dockerfile | Present (non-root + healthcheck). Image-size gate not enforced. `uv.lock` often generated in CI, not at bake. |
| 7.2 CI: pip-audit, trivy, push SHA, deploy staging/prod | **Missing** in generated workflow |
| 7.3 Helm (HPA, PDB, ingress, worker, migrate Job) | **Missing** — `deploy/` is only `docker-compose.otlp.yml` |
| 8.1 Getting started / auth / K8s guides | Wiki is a 5-page stub; `ARCHITECTURE.md` is `(fill in)` |
| 8.2 AsyncAPI from event registry | **Missing** |

---

## 6. Deploy & scale (S0–S6) — almost all missing

`deploy/` contains **one** file: OTel compose overlay.

Missing artifacts the north star treats as the definition of “production-ready”:

- Helm chart `deploy/helm/nk-backend` + `values/staging.yaml` + `prod-s{1,2,3}.yaml`
- Separate **api / stream / worker** Deployments and path-split Ingress
- Alembic as a **PreSync Job** (not migrate-on-startup in prod)
- HPA, PDB, topologySpread, NetworkPolicy, PSS restricted, ExternalSecrets
- KEDA ScaledObject
- Argo CD Application / Flux
- Canary + SLO-burn rollback
- Cosign + Syft SBOM + Trivy CRITICAL gate
- Cell / org-directory / ingest-edge (S5–S6) — correctly later, but S1–S2 is also absent

`docker-compose.prod.yml` exists; Traefik + Docker secrets are called out as not bundled (`GOTCHAS.md`).

---

## 7. Durability holes (looks production-shaped, dies on restart)

Called out in `.project-intelligence/GOTCHAS.md` and still true:

| Concern | Default impl | Production need |
|---|---|---|
| Sessions / CSRF / some identity stores | In-memory | Redis or Postgres |
| Audit sink | In-memory | Append-only Postgres |
| Job DLQ | In-memory | Redis/SQL + replay |
| Tenant membership / resource ownership | In-memory; not configured at boot | Durable registry + RLS GUC on every UoW |
| Agent graph checkpoint | Memory if any | `AsyncPostgresSaver` |
| Webhook replay store | In-memory | Redis/SQL |
| Generated `uv.lock` | Often missing after generate | Commit lockfile in `create` |

A container restart on `saas` can drop sessions, audit, DLQ, and tenant maps.

---

## 8. Security & tenancy gaps

- **CORS** not installed (browser studio / SPA will fail cross-origin).
- **Auth middleware** not installed; routes are public unless each router adds `Depends`.
- **RLS**: generator helpers exist; generated Alembic user/dummy migrations do not FORCE RLS on tenant tables by default.
- **Schema-per-tenant / DB-per-tenant**: documented, not implemented.
- **Cross-tenant CI on real Postgres** is the bar in the north star; many tests stay in-memory.
- **Password reset email send** is explicitly “not implemented” in `identity/password_lifecycle.py`.
- **AML** is `allow-all` stub (`industry/fintech/compliance/aml.py`).
- Supply chain: no signed images, no SBOM, no CRITICAL CVE gate on generated apps.

---

## 9. Industry packs & white-label

| Pack | Status |
|---|---|
| Fintech ledger + limits/KYC/AML hook | Code present; HTTP/mount/AML vendor missing |
| CRM / ERP / commerce / data-platform | **Missing** |
| White-label branding/domain slots | **Missing** |
| `nk-core` extracted wheel (P8) | **Not extracted** — everything still lives in the cookiecutter tree |

---

## 10. Generator / repo productization

The **product is still the old package**:

- Root `pyproject.toml`: `name = "fastapi_template"`, authors Pavel Kirilin, URLs → `s3rius/FastAPI-template`
- README still documents `pip install fastapi_template` / `ghcr.io/s3rius/fastapi_template`
- No published `nk` console script on the **generator**
- Root Python `>=3.9` vs generated target 3.12
- Cookiecutter 1.x (`<2`)
- `.project-intelligence/ARCHITECTURE.md` empty
- Wiki does not document settings, auth setup, or Kubernetes
- `enable_graphrag` / `enable_rag_traditional` are menu flags that do not add files

---

## 11. Recommended implementation order

Do not start with S6 cells or GraphRAG. Close the framework loop first.

### P0 — Make the paved road real (highest leverage)

1. **Module auto-discovery** — mount `business/modules/**/router.py` under `/api/v1/{domain}`; `nk generate` wires DI with an in-memory or SA repository so the scaffold runs.
2. **Identity HTTP** — replace fastapi-users routes with identity-owned `/auth/*` (login/refresh/logout/sessions/api-keys).
3. **Boot wiring** — register readiness checks (DB, Redis, broker); `configure_tenant_authorization`; CORS from settings; `/api/build-info`.
4. **CLI** — `nk start`, `nk migrate`, `nk seed`; generator alias `nk init`.
5. **Durable defaults for `saas+`** — Postgres/Redis stores for session, audit, DLQ, idempotency (already protocolized).

### P1 — Production deploy

6. Helm chart + worker + migrate Job + values for S1/S2.
7. Generated CI: lockfile at generate time, `nk check`, trivy, optional GHCR push.
8. Path-split stream Deployment when `enable_agents`.

### P2 — Platform product modules

9. Notifications (SMTP + in-app).
10. Webhook **delivery** (retry, DLQ, endpoint CRUD) on top of existing signer.
11. Billing protocol + Stripe adapter + entitlement gate.
12. SCIM `get_scim_service` DI.

### P3 — AI completeness (only after P0)

13. Ingestion pipeline + Postgres FTS hybrid + rerank.
14. MCP **server** (`/mcp`) + Agent Protocol `/runs|/threads`.
15. GraphRAG adapter **or** drop the `enable_graphrag` flag until it has files.
16. Sandbox backend + durable checkpointer.

---

## 12. What “done” means (unchanged, still unmet)

A generated `agentic` app at **S2** is production-ready when the north-star checklist in `2026-08-24-nk-system-design.md` §19 is true. **None of those boxes are checked in code** (no Helm path-split, no PrometheusRules, no signed images, no Argo, no chaos-proven outbox/DLQ).

Gold definition (10 rules) is also unmet for: lockfile-on-generate, provider swap without touching business code (Jinja still dominates), and “real app without modifying foundation” (generate module does not run).

---

*Audited 2026-08-29 against `feat/nk-backend-platform`. This file is the backlog map; it does not implement the gaps.*
