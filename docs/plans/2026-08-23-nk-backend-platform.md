# NK Backend Platform — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform this cookiecutter FastAPI generator into the NK Backend Platform: profiles, provider-swappable infrastructure, a universal data layer (Postgres+pgvector / Mongo), a RAG progression stack (traditional → agentic → GraphRAG+loop), and contract tests that make the abstractions real.

**Architecture:** Keep the generator (it IS the product — `fastapi_template` renders projects from menus). Evolve it in place: add profile presets to the menu pipeline, add platform modules as template dirs wired through `conditional_files.toml`, and introduce protocol interfaces in generated code so providers are swappable at runtime via settings — not just at generation time.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 async + asyncpg, pgvector (`pgvector.sqlalchemy.Vector`, HNSW), Beanie/Motor (Mongo), TaskIQ (queue facade), Redis/Kafka/NATS/RabbitMQ adapters, OpenTelemetry, LangGraph (agent runtime, kept behind our own protocol), LightRAG adapter (GraphRAG mode), pytest contract matrix.

---

## 0. Current-State Assessment (verified against this repo)

| Area | What exists today | File(s) |
|---|---|---|
| Generator | Menu models → `BuilderContext` → cookiecutter render; ~20 CLI flags | `fastapi_template/cli.py`, `input_model.py` |
| Feature pruning | `conditional_files.toml` maps feature→resources; `replaceable_files.toml` for overrides | `template/conditional_files.toml` |
| App factory | Jinja-conditioned `get_app()` | `template/.../web/application.py` |
| Lifecycle wiring | One giant conditional `lifespan_setup`: SA/ormar/psycopg/beanie/tortoise + redis/rmq/kafka/nats/taskiq + OTel + prometheus | `template/.../web/lifespan.py` |
| Data access | Per-ORM DAO classes, **same method names, no shared interface** | `db_sa/dao/dummy_dao.py`, `db_beanie/dao/dummy_dao.py` |
| Config | pydantic-settings v2, env-prefixed, per-feature fields | `settings.py` |
| Queues | TaskIQ broker selection: AioPika → Redis ListQueue → ZeroMQ; InMemory in pytest | `tkq.py` |
| Observability | Full OTLP traces/metrics/logs + per-infra instrumentors | `lifespan.py` |
| CI/test matrix | Parametrized db×orm generation tests = de-facto contract suite | `tests/test_generator.py` |

**The gap:** wiring is generation-time-only (Jinja conditionals). There is no runtime provider swap, no repository contract, no identity/RBAC, no AI layer, no events abstraction, no profiles.

## 1. Key Decisions (with rationale)

1. **Universal REPOSITORY CONTRACT, not universal ORM.** Postgres and Mongo have irreconcilable transaction/query semantics. We define one `Repository[T]` protocol (get/list/filter/create/update/delete/count/upsert) that both a SQLAlchemy adapter and a Beanie adapter implement, enforced by one parametrized test suite (`RepositoryContractTest`). pgvector lives *inside* the Postgres adapter as a `VectorRepository` sub-protocol (cosine_distance, hybrid FTS+RRF search). This gives real leverage without fake parity.
2. **Runtime provider selection via settings**, generation-time pruning only decides what's *possible*. Generated apps read `providers:` config and instantiate adapters in lifespan. Swapping Redis→in-memory cache or Rabbit→Kafka becomes a config change, not a regeneration.
3. **Queue facade stays TaskIQ-shaped initially** — it's already wired for RMQ/Redis/ZMQ/InMemory and has OTel instrumentation. Add native Kafka/NATS JetStream adapters behind our own `QueueProvider` protocol rather than replacing TaskIQ.
4. **RAG progression = three modes of ONE `RetrievalProvider`:**
   - `mode=traditional`: embed → pgvector HNSW → top-k (+ hybrid BM25/RRF rerank).
   - `mode=agentic`: same retrieval exposed as a **tool** to the agent runtime; loop = plan→retrieve→grade→re-retrieve (CRAG-style) implemented in our AgentRuntime.
   - `mode=graph`: LightRAG adapter (KG+vector dual-level, incremental updates — production-proven vs MS GraphRAG's heavier indexing); router selects mode by query intent. Entities/relations persist in Postgres first (no Neo4j dependency on day one).
5. **AgentRuntime owns its own protocol.** LangGraph underneath, never leaked into business code. Budgets, guardrails, checkpoints, HITL gates are first-class protocol members.
6. **Modular monolith.** No microservices. Domain modules are packages inside the generated app with explicit boundaries (public API via `module.exports`-style registries).
7. **In-place evolution of this repo.** It's already published as a generator package; profiles/modules extend it. Extract `nk-core` as an installable library only after contracts stabilize (Phase 8).

## 2. Target Layout

```
FastAPI-template/
├── fastapi_template/                  # generator (evolves into `nk` CLI)
│   ├── cli.py                         # + profile_menu, module_menu
│   ├── input_model.py                 # + Profile presets, Module registry
│   ├── profiles.py                    # NEW: minimal/saas/ai-saas/agentic/fintech presets
│   └── template/
│       ├── conditional_files.toml     # + every new feature→resource rule
│       └── {{cookiecutter.project_name}}/
│           └── {{cookiecutter.project_name}}/
│               ├── core/              # NEW: errors, identifiers, time, events, DI container
│               ├── data/              # REFACTORED db_*: protocols + postgres/ mongo/ adapters
│               │   ├── protocols.py   # Repository[T], UnitOfWork, VectorRepository
│               │   ├── postgres/      # SA impl + pgvector
│               │   └── mongo/         # Beanie impl
│               ├── messaging/         # NEW: QueueProvider + taskiq/kafka/nats/rmq adapters
│               ├── ai/                # NEW: LLMProvider, EmbeddingProvider, RetrievalProvider
│               │   ├── retrieval/     # traditional | agentic-loop | graph(LightRAG)
│               │   └── llm/           # openai | anthropic | ollama | compatible
│               ├── agents/            # NEW: AgentRuntime (LangGraph-backed), tools, budgets, HITL
│               └── web/lifespan.py    # rewritten: provider registry bootstrap
└── tests/                             # generator matrix + NEW contract suites
```

## 3. Phased Roadmap

| Phase | Delivers | Depends on |
|---|---|---|
| P0 | Repo hygiene: ruff/pyright strict, CI green baseline, plan reviewed | — |
| P1 | **Profiles**: `profiles.py` presets → menu pipeline + CLI flag; generated `platform.yaml` manifest | P0 |
| P2 | **Core kernel**: core/errors (RFC7807), identifiers, time, events protocol, DI container; lifespan rewrite to registry-based bootstrap | P1 |
| P3 | **Universal data layer**: `data/protocols.py`, postgres adapter (SA+asyncpg+pgvector), mongo adapter (Beanie), UoW, contract test suite running both adapters | P2 |
| P4 | **Messaging**: QueueProvider protocol + taskiq/kafka/nats/rmq adapters, domain event bus, idempotency keys, DLQ | P2 |
| P5 | **AI layer**: LLMProvider (openai/anthropic/ollama), EmbeddingProvider, RetrievalProvider(traditional: pgvector+hybrid RRF), usage/cost tracking | P3,P4 |
| P6 | **Agentic RAG + agents**: AgentRuntime (LangGraph), retrieval-as-tool, CRAG loop, budgets/guardrails/checkpoints/HITL | P5 |
| P7 | **GraphRAG**: LightRAG adapter behind RetrievalProvider(mode=graph), intent router across modes | P5 |
| P8 | **Platform modules**: identity (JWT/OAuth2 + RBAC tables), audit, files(S3/local), webhooks, notifications; extract `nk-core` wheel | P3,P4 |
| P9 | **Industry packs + white-label**: fintech pack (double-entry ledger, maker-checker), CRM/ERP starter modules, tenant isolation modes | P8 |

## 4. Detailed Tasks — Phase 0 & Phase 1 (executable now)

### Task 1: Baseline quality gate
**Files:** Modify `pyproject.toml`; Create `.github/workflows/platform-ci.yml`
1. Add `[tool.ruff]` (line-length 100, select E,F,I,B,S) and `[tool.mypy]` (strict-ish: disallow_untyped_defs) sections to root `pyproject.toml`.
2. Run: `uv run ruff check fastapi_template && uv run mypy fastapi_template/input_model.py`
   Expected: clean or fix trivial issues.
3. Commit: `chore: add ruff+mypy config for platform work`

### Task 2: Profile registry (failing test first)
**Files:** Create `fastapi_template/profiles.py`; Test in `fastapi_template/tests/test_profiles.py`

Step 1 — failing test:
```python
def test_ai_saas_profile_expands():
    ctx = expand_profile("ai-saas", BuilderContext())
    assert ctx.enable_redis and ctx.enable_taskiq and ctx.otlp_enabled
    assert ctx.enable_kafka is None or ctx.enable_kafka is False  # not forced
```
Step 2 — run: `uv run pytest fastapi_template/tests/test_profiles.py -v` → FAIL (module missing)
Step 3 — implement:
```python
PROFILES: dict[str, dict[str, Any]] = {
    "minimal": {"enable_routers": True},
    "saas": {"enable_redis": True, "enable_taskiq": True, "otlp_enabled": True,
             "add_users": True, "orm": "sqlalchemy", "db": "postgresql",
             "enable_migrations": True},
    "ai-saas": {**PROFILES["saas"], "enable_llm": True, "enable_rag_traditional": True,
                "enable_vector": True},
    "agentic": {**PROFILES["ai-saas"], "enable_agents": True, "enable_graphrag": True},
    "fintech": {**PROFILES["saas"], "enable_audit": True, "enable_idempotency": True},
}
def expand_profile(name, ctx): ...
```
Step 4 — tests pass. Step 5 — commit `feat: profile presets`.

### Task 3: Wire profile into CLI + menus
**Files:** Modify `cli.py:656` (`run_command`), `cli.py:344` (features_menu entries get `is_hidden` guards for new codes)
1. Add `--profile [minimal|saas|ai-saas|agentic|fintech]` Option; apply expansion BEFORE menu loop so menus only ask about unset values (existing `need_ask` logic already supports this — verified).
2. New feature MenuEntries: `enable_llm`, `enable_vector`, `enable_rag_traditional`, `enable_agents`, `enable_graphrag`, `enable_audit`, `enable_idempotency` — each hidden unless its prerequisite profile bits exist.
3. Verify: `uv run python -m fastapi_template --help` shows new flags; generate a scratch project with `--quiet --profile agentic -n scratch` and confirm dirs exist.
4. Commit: `feat: wire profiles into generator CLI`

### Task 4: platform.yaml manifest in generated project
**Files:** Create template file `template/{{cookiecutter.project_name}}/platform.yaml.jinja`; register in `cookiecutter.json` context if needed
```yaml
project: {{ '{{cookiecutter.project_name}}' }}
profile: {{ '{{cookiecutter.profile}}' }}
providers:
  database: {{ '{{cookiecutter.db_info.name}}' }}
  orm: {{ '{{cookiecutter.orm}}' }}
  queue: {% raw %}{{ queue_provider | default("taskiq") }}{% endraw %}
modules:
  rag_traditional: {{ '{{cookiecutter.enable_rag_traditional}}' }}
  agents: {{ '{{cookiecutter.enable_agents}}' }}
  graphrag: {{ '{{cookiecutter.enable_graphrag}}' }}
```
Generated app loads this in `core/config.py` → single source of truth for runtime bootstrap. Commit.

### Task 5–12 (P2 onward, specified when P0/P1 land)
Kernel errors/DI → data protocols + adapters + contract tests → messaging → AI/traditional RAG → agent runtime → GraphRAG. Each gets the same TDD granularity; specs drafted per phase gate review.

## 5. Contract Test Suite Design (the thing that makes it real)

```
tests/contracts/
├── conftest.py          # fixture factories: postgres_url, mongo_url (docker compose)
├── test_repository.py   # @pytest.mark.parametrize("adapter", ["postgres","mongo"])
│                        #   CRUD, filter, pagination, count — SAME asserts both backends
├── test_uow.py          # commit/rollback semantics (Mongo uses 4.x multi-doc txns on replica set)
├── test_vector.py       # postgres-only: insert embeddings, cosine top-k, hybrid RRF ordering
├── test_queue.py        # publish/consume/retry/DLQ across taskiq-rmq / taskiq-redis / kafka / nats / inmemory
└── test_retrieval.py    # traditional vs graph mode return-shape parity; agentic loop terminates within budget
```
Rule inherited from existing `test_generator.py` matrix style: every provider added ⇒ must pass its contract file or it doesn't ship.

## 6. Risks / Open Questions

1. **Mongo transactions** need a replica set in dev docker-compose — adds startup weight to contract tests. Mitigation: mark `test_uow[mongo]` slow-marker.
2. **LightRAG license/activity**: MIT, active — but pin exact version and vendor prompts; escape hatch = nano-graphrag (hackable) or MS GraphRAG later.
3. **LangGraph coupling**: acceptable as implementation detail since AgentRuntime protocol isolates it; revisit if PydanticAI matures faster.
4. **Scope honesty**: P9 industry packs (ERP/CRM/fintech domains) are product decisions, not infra — plan locks infra (P0–P8); packs start after identity/audit exist.

---

## 7. Gap Analysis Additions — Web Research 2026-08-23

Exhaustive sweep of current production systems (Stripe-class patterns, durable-execution engines, MCP spec, vector extensions, standards bodies). Six gaps found in §1–§5 above; each maps to a phase amendment:

### G1. Transactional Outbox (amends P4 Messaging)
The dual-write problem (DB commit succeeds, broker publish fails ⇒ lost event) has no answer in the original events design. Standard fix, now table-stakes (82% of event-driven teams per 2025 CNCF survey):
- `core/events/outbox.py`: outbox table (`id, aggregate_id, event_type, payload JSONB, trace_id, created_at, published_at`) written **in the same transaction** as business writes.
- Relay: async poller using `SELECT ... FOR UPDATE SKIP LOCKED LIMIT n` (multi-instance safe); CDC/Debezium documented as scale-up path.
- Consumer idempotency via Redis SETNX dedup; backlog metric `unsent_count` exported to OTel/Prometheus with alert threshold; TTL cleanup job.
- Contract test `test_outbox.py`: crash-relay-restart ⇒ at-least-once, no loss.

### G2. Row-Level Security Tenancy (amends P8 Identity/Multi-tenancy)
The vision listed three isolation models but named no enforcement. 2026 consensus default: shared schema + RLS at the database, not app-layer `WHERE` discipline:
- Every tenant-scoped table: `tenant_id UUID NOT NULL`, `ENABLE`+`FORCE ROW LEVEL SECURITY`, policies with both `USING` and `WITH CHECK` on `current_setting('app.tenant_id')`.
- Session context via transaction-local GUCs: `SELECT set_config('app.tenant_id', :tid, true)` inside the request's DB session — auto-reset on commit, safe with pooled connections.
- App never connects as superuser; dedicated non-superuser role.
- Negative CI contract tests mandatory: cross-tenant read ⇒ 0 rows/404, cross-tenant write ⇒ rejected. Evaluate `fastapi-rls` (PyPI) before hand-rolling DDL generation.
- Schema-per-tenant / DB-per-tenant remain opt-in profiles for enterprise/residency tiers.

### G3. pgvectorscale as Optional Vector Scaling Layer (amends P5 AI)
Plan specified vanilla pgvector HNSW. Timescale's pgvectorscale (Rust/PGRX, PostgreSQL license, v0.9 Nov 2025) complements it: StreamingDiskANN (disk-resident index — graceful when embeddings exceed RAM), Statistical Binary Quantization, label-based filtered search. Benchmarks: 28x lower p95 / 16x throughput vs Pinecone s1 @99% recall.
- Keep pgvector HNSW as the default; expose `vector_index: hnsw | diskann` in `platform.yaml`.
- Adoption rule: benchmark first on real corpus; switch index type only when measured recall/latency demands it. No new service — still just Postgres.

### G4. Durable Execution Ladder — DBOS Default, not Temporal-First (amends P6 Agents)
Original plan assumed Temporal underneath workflows. The 2026 landscape changes the cost calculus:
- **DBOS** (in-process Python library): step results committed to *your* Postgres in the same transaction as your writes; replay-on-restart; zero new infra. Ideal default for a modular monolith.
- **Hatchet**: Postgres-native queue + durable tasks + built-in rate limiting/multi-tenancy/OTel; drop-in Temporal replacement at moderate scale (10k tasks/s).
- **Temporal**: enterprise tier (cluster ops, polyglot, signals/HITL).
- Key correction: **LangGraph checkpointing is NOT durable execution** — checkpoints ≠ journaled side-effect replay. AgentRuntime therefore defines a `DurableBackend` protocol (validated by Pydantic AI supporting Temporal/DBOS/Prefect/Restate behind one interface). Profile mapping: `agentic` profile ⇒ DBOS default; `enterprise` profile ⇒ Temporal adapter.
- HITL approvals = durable timer + signal/resume primitive from the backend protocol.

### G5. MCP as First-Class API Surface (amends P6/P8)
MCP (Linux Foundation) hit v2 spec **2026-07-28**: stateless Streamable HTTP single-endpoint transport (SSE deprecated), OAuth 2.1 Resource Server model. Platform must expose an `/mcp` endpoint alongside REST/GraphQL:
- Auth: RFC 9728 Protected Resource Metadata discovery + RFC 8707 audience-bound tokens; reject tokens issued for other resources; NEVER pass inbound token upstream (confused-deputy).
- Client registration: CIMD (Client ID Metadata Documents) replaces Dynamic Client Registration.
- Tenant isolation NOT in spec ⇒ enforce from token claims ourselves; rate limiting + per-team cost attribution are our responsibility.
- Tool inputs are untrusted AI-generated data ⇒ strict Pydantic validation per tool (primary prompt-injection defense); state handles minted explicitly (no implicit sessions).
- Implementation: official `mcp` Python SDK v2 (stable) wrapped behind our ToolRegistry so business tools register once, exposed via both REST and MCP.

### G6. Standards Adoption (amends P4/P8)
- **Standard Webhooks** (adopted by OpenAI/Anthropic/Supabase/Twilio/Svix): outbound webhooks sign with HMAC per spec headers (`webhook-id`, `webhook-timestamp`, `webhook-signature`); use `standardwebhooks` PyPI lib. What JWT did for auth, this does for webhooks — consumers verify once.
- **CloudEvents 1.0** envelope for the internal event bus + outbox payloads (`specversion/type/source/id/time`): unambiguous log filtering, native interop if events ever route through Kafka/EventGrid/Knative.
- **AsyncAPI** document generated from event registry (what OpenAPI is to REST).
- **Stripe-style `Idempotency-Key` HTTP middleware** promoted to a core kernel primitive (not just queue-level): key → stored response replay window, per-endpoint opt-in.

### Amendment Summary Table

| Gap | Phase | New artifacts |
|---|---|---|
| G1 Outbox | P4 | `core/events/outbox.py`, relay worker, `test_outbox.py` |
| G2 RLS | P8 | RLS policy DDL generator, GUC session dep, negative CI suite |
| G3 pgvectorscale | P5 | `vector_index` config, benchmark harness task |
| G4 Durable ladder | P6 | `DurableBackend` protocol, DBOS adapter (default), Hatchet/Temporal adapters |
| G5 MCP | P6+P8 | `/mcp` Streamable HTTP endpoint, OAuth RS wiring, ToolRegistry→MCP bridge |
| G6 Standards | P4+P8 | standardwebhooks signer, CloudEvents envelope, Idempotency-Key middleware, AsyncAPI gen |
