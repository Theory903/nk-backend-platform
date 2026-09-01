# Project Knowledge — fastapi-template

Wiki: docs/wiki/INDEX.md

- **Session compact (2026-08-27)**: `~/AI Intelligence/daily/2026/08/2026-08-27-fastapi-template-context.md`
- One canonical `SessionStore` (`identity/session.py`); lifecycle = alias shim
- JWT policy: `identity/token_policy` (PyJWT); `jwt.py` = low-level HS/RS
- Trust: headers input; `request.state` after auth/tenant trusted; no X-Org-Id alone
- State: `create_state_stores` + inject redis_client; pool at `app.state.redis_pool`
- Messaging: one shared Kafka/NATS/Rabbit/Redis resource; DI resolve only
- Profiles: UserDict `BuilderContext`; expand fills None only; fintech ≠ AI stack
- **DX**: `validate_context` pre-bake; generated `nk` CLI (doctor/validate/check/dev/build/generate); wiki Getting Started
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

- **Session 2026-08-31**: Generator now exposes global `nk init NAME` and `fastapi-template` scripts; Python floor aligns at 3.12.
- **Architecture completion (2026-08-31)**: Generated identity protects agent/MCP routes,
  cookie JWT mutations use CSRF, production membership uses SQL resolution, account
  status gates JWT/session/API-key auth, agent actions require an executor, and Helm
  defaults include ingress namespace, writable Prometheus temp storage, and opt-in
  PrometheusRule rendering.

- **Tests (2026-08-27)**: probe 954 passed / 5 skipped (brokers down); generator unit 18 passed; Docker generator matrix blocked.
