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
- Next: wire state stores from pool; jti/kid; SQL membership + SET LOCAL; identity `/auth/*`; publish `nk init` alias

- **Tests (2026-08-27)**: probe 954 passed / 5 skipped (brokers down); generator unit 18 passed; Docker generator matrix blocked.
