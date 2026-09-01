# Project Knowledge — fastapi-template

Wiki: docs/wiki/INDEX.md

- **Session compact (2026-08-27)**: `~/AI Intelligence/daily/2026/08/2026-08-27-fastapi-template-context.md`
- One canonical `SessionStore` (`identity/session.py`); lifecycle = alias shim
- JWT policy: `identity/token_policy` (PyJWT); `jwt.py` = low-level HS/RS
- Trust: headers input; `request.state` after auth/tenant trusted; no X-Org-Id alone
- State: `create_state_stores` + inject redis_client; pool at `app.state.redis_pool`
- Messaging: one shared Kafka/NATS/Rabbit/Redis resource; DI resolve only
- Profiles: UserDict `BuilderContext`; expand fills None only; fintech ≠ AI stack
- **DX**: `validate_context` pre-bake; generated `nk` CLI (doctor/validate/check/dev/build/generate/export-openapi); wiki Getting Started
- **OpenAPI clients (2026-09-01)**: `uv run nk export-openapi` writes Postman-ready `docs/openapi.json` + `docs/postman-environment.json` (baseUrl, testEmail, accessToken, …); future routes included on re-export
- **E2E smoke (2026-09-01)**: `scripts/e2e_postman.sh` — Postman CLI + curl; dev ApiKey bootstrap in lifespan; cookie auth via fixed `InMemoryAccessTokenStore`; dev SCIM in-memory repo
- AI: fakes only in `tests/_fakes.py`; real adapters `ai/providers/` (any_llm, fastembed); graph uses `langgraph.prebuilt.create_react_agent`
- Current: architecture gap implementation spans typed manifests/config, CLI parity,
  identity and tenant authorization, durable Redis/SQL adapters, bounded agents,
  secure RAG ingestion/retrieval, MCP, Helm/GitOps, CI, and observability.
- Verification: five generated profiles pass the generation matrix; focused
  config/CLI tests (49), profile generation (14), Ruff, mypy, generated SaaS
  compilation, and Helm lint/template checks pass. Docker generator test passes
  (266 containerized tests on minimal profile). SaaS security suite: 67+ tests
  including RLS, CSRF, identity, settings, and headers.
- **Security (2026-09-01)**: fail-closed identity, tenant RLS, CSRF, idempotency,
  credential digests, Postgres admin/runtime roles, supply-chain pinning, and
  `SECURITY-ARCHITECTURE.md` at repo root.
- **AI platform roadmap (2026-09-01)**: Master doc replaces feature-pack-only plan — 8 primitives (Plugin Kernel, Model Gateway, Agent Runtime, Tool Gateway, Context, Session, Harness, OTel/Security); P0–P30 phases; OSS map includes DeepSeek Harness, gstack, Karpathy autoresearch; `temp/oss/` 26 clones; `production-ai-local` profile; wiki: `docs/wiki/references/ai-platform-{roadmap,phases,oss-map}.md`.
- **AI P0 dev plane (2026-09-01)**: Ollama in compose + `OLLAMA_API_BASE`; `llm/dev_seed.py` (dev RAG+memory seed); `uv run nk ai doctor`; `NK_OLLAMA_PORT` in `nk dev`.
- **AI P1 storage (2026-09-01)**: Redis `RedisMemoryStore` + auto memory backend; `QdrantVectorStore` + `store_factory` auto-select (pgvector dev / qdrant scale); `ollama-init` pull sidecar; Qdrant in compose when `enable_vector`.
- **AI P2 model gateway (2026-09-01)**: `capabilities.yaml` + `for_capability()`; budget guard + semantic/exact completion cache; `uv run nk ai routes`.
- **AI P3 agent runtime (2026-09-01)**: `LoopRuntime`/`GraphRuntime`/`SupervisorRuntime` + `AgentRuntimeFactory` routing ladder; cancellation token; `runtime_mode` on agent runs; `nk ai runtime modes`.
- **AI P4 tool gateway (2026-09-01)**: `ToolGateway` (policy + approval + audit); `tool_policy.yaml` + MCP bootstrap; `register_many`; loop/MCP dispatch through gateway; `uv run nk ai tools list`.
- **AI P13 session runtime (2026-09-01)**: append-only events (`RunStarted`…`RunCompleted`); `SessionRuntime` inspect/fork/replay/resume; loop recorder; API + `nk ai inspect|replay|fork|resume`.
- **AI P14 harness runner (2026-09-01)**: `ScenarioRunner` + trajectory capture; fixture record/replay; `tests/evals/scenarios.yaml`; `uv run nk ai harness run|record|replay|list`.
- **AI P15 eval adapters (2026-09-01)**: `agents/evaluation/adapters/` — native, harness, ragas, deepeval, promptfoo; `uv run nk ai eval list|run --adapter native`.
- **AI P18 security (2026-09-01)**: PII redaction, tool poisoning scan, RAG data boundary, security manifest + invariants; `uv run nk ai security audit`.
- **AI P19 OTel GenAI (2026-09-01)**: `observability/genai/` spans (chat/tool/agent), latency histograms, `InstrumentedChatModel`; `uv run nk ai metrics`.
- **AI P21 plugin kernel (2026-09-01)**: `kernel/plugins/` discovery, lifecycle, dependency graph, catalog; `uv run nk ai plugins list|health`.
- **AI P22 skill runtime (2026-09-01)**: `skill.yaml` manifests (tools/permissions/evaluation), `SkillRuntime`, gstack presets; `uv run nk skills manifest|presets|list --manifests`.
- **AI P26 experiment runtime (2026-09-01)**: `research/experiments/` hypothesis catalog, mutations, store, runtime; `uv run nk ai experiment hypotheses|leaderboard|run|rollback`.
- **ERP feature packs (2026-09-02)**: full API replica — AR/AP aging, payment-term row split, GL/stock ledger rows, 185 reports, controller validation; **43 ERP tests pass**.

- **Session 2026-08-31**: Generator now exposes global `nk init NAME` and `fastapi-template` scripts; Python floor aligns at 3.12.
- **Architecture completion (2026-08-31)**: Generated identity protects agent/MCP routes,
  cookie JWT mutations use CSRF, production membership uses SQL resolution, account
  status gates JWT/session/API-key auth, agent actions require an executor, and Helm
  defaults include ingress namespace, writable Prometheus temp storage, and opt-in
  PrometheusRule rendering.

- **Tests (2026-08-27)**: probe 954 passed / 5 skipped (brokers down); generator unit 18 passed; Docker generator matrix blocked.
