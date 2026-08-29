# Gold Master Plan — Single Source of Truth

<!-- title: Gold Master Plan · updated: 2026-08-24 · status: ACTIVE (supersedes gold-refined-plan.md + gold-real-harvest.md) -->
<!-- architecture SSoT: nk-system-design.md (Next.js-for-FastAPI framing · S0–S6 K8s scale · telemetry · CI/CD · phases stay HERE only) -->
<!-- evidence appendix: temp-full-feature-map.md (§N refs below point there) -->

> DRY rule: this file states every fact once. Per-repo exhaustive detail lives ONLY in `temp-full-feature-map.md` (referenced as §N). Similar capabilities are COMBINED into single hybrid/multi-mode entries — one owned interface, N modes behind it.

---

## 1. Locked Decisions (never reopen)

Cookiecutter factory stays · Python 3.12 primary (3.11 compatible) · agentic = first-class platform capability · FinTech = first industry pack · optional extras aggressively (minimal boots zero optionals) · provider abstractions = contracts first, adapters second · modular monolith default · we own contracts/orchestration/policies/DX, we integrate infra (DB/queue/IdP/workflow engine/cloud).

## 2. Gold Definition (all 10 must hold)

1. Installs cleanly (`uv sync --locked`). 2. `minimal` boots zero optional deps. 3. Every profile generates valid code. 4. Generated project passes full pytest. 5. Provider swap without touching business logic. 6. AI/agent features fully optional. 7. SQL and Mongo pass identical contracts. 8. Failures observable + recoverable. 9. Enable/disable modules without import repair. 10. Real app buildable without modifying foundation.

## 3. Module Contract (gate for everything)

`Interface → Implementation → Configuration → Health → Metrics → Tracing → Errors → Tests`
Owned = contracts, orchestration, policies, DX. Integrated = Postgres/Redis/S3/Kafka/Qdrant/Temporal/Ollama/etc.

## 4. Combined Capability Matrix (similar features merged)

Each row: ONE owned interface, modes behind a factory/config switch. `[MM]`=multi-mode, `[H]`=hybrid pipeline, `[C]`=combined surface.

| # | Capability (combined) | Owned Interface / Path | Modes Behind One Switch | Primary Source (§map) | Extra |
|---|---|---|---|---|---|
| C1 | **[MM] LLM Gateway** — chat+stream+tools+structured+reasoning+responses+messages+moderation+batch in one surface | `ai/gateway` `ChatModel` Protocol → `get_chat_model(provider)` | `any_llm.acompletion` real (60+ providers, ollama local default) · hosted keys optional | §2 any-llm (api.py full surface); alt: dify provider_manager §17 | `any-llm-sdk[ollama,...]` |
| C2 | **[MM] Embeddings** — dense+sparse+late-interaction+image under ONE provider | `EmbeddingProvider.embed(text, mode=)` | fastembed native 4-mode: `TextEmbedding`(bge-small 384d) / `SparseTextEmbedding`(BM25/SPLADE/MiniCOIL) / `LateInteractionTextEmbedding`(ColBERT) / `ImageEmbedding`(CLIP/SigLIP) · hosted fallback `any_llm.embedding` | §5+§12 fastembed; hosted alt §2 | `fastembed` |
| C3 | **[H] Retrieval Pipeline** — keyword+vector fused, reranked, cited | `HybridRetriever.search(query, top_k)` | pgvector(default)+Postgres FTS/BM25 → RRF fusion → rerank → citations; vector store switch `pgvector|qdrant`; rerank `fastembed-cross-encoder|any-llm-arerank|none` | §16 open-webui hybrid BM25+vector; §17 dify rag; §5 fastembed | `pgvector`, opt `qdrant-client` |
| C4 | **[H] Ranking Scorer** — weighted-sum over signals, negative weights, config-driven | `Ranker.score(candidate)->float` | signals: semantic sim, recency, authority, spam(neg) — TML grammar `<scope>.<engagement>.<feature>.<window>` dual-window (30min/50day) | §19 algorithm-ml MaskNet scoring-as-config | — |
| C5 | **[MM] Agent Runtime** — one `AgentRuntime.run(task)->AgentResult`, three engines | `agents/runtime` Protocol | `loop` (owned ReAct, zero-dep) · `pydantic` (typed Agent+capabilities) · `graph` (langgraph create_react_agent+checkpointer) — config `agents.runtime=` | §3 langgraph (fix broken import!), §4 pydantic-ai, §13 dsh agent-loop-seam idea | per-engine extras |
| C6 | **[C] Tool System** — registry + schema-gen + permissions + MCP transport in one | `ToolRegistry` + `agent_tool` decorator | upgrade schema-gen w/ any-llm `callable_to_tool` (Enum/Literal/Pydantic); MCP = just another provider via `MultiServerMCPClient`; curated set per open-swe (execute/fetch/http first) | §6 mcp-adapters, §2 tools.py, §9 open-swe curation, §16 builtin tools | `langchain-mcp-adapters`,`mcp` |
| C7 | **[C] Skills & Plugins Seam** — skills manifest + plugin 3-role seam + waterfall hooks, one architecture | `ServiceDefinition/Provider/Consumer` + `SkillManifest` loader | skills: deepagents SKILL.md loader · dsh skill registry/catalog pattern · open-webui Filters/Pipes `pipe(body)->dict` convention; interception via waterfall `next()` events | §8 deepagents, §13 dsh, §16 plugins | — |
| C8 | **[MM] Memory** — working/conversation/episodic/semantic via one store | `MemoryStore.put/get/search(namespace)` | langgraph Store(+embed search) namespaces = episodic/semantic · checkpointer = working/thread state · serde jsonplus/msgpack; session-log invariant model-visible⟺logged | §7 checkpoint/store, §10 store items API, §13 dsh session log | `langgraph-checkpoint-{memory,postgres}` |
| C9 | **[C] Sessions & Runs HTTP API** — serve agents via standard protocol, not custom endpoints | FastAPI router `/runs /threads /store` | agent-protocol OpenAPI ops (wait/stream/cancel/history/sse/ws) mounted; dsh acp/sdk JSON-RPC as alt shape | §10 agent-protocol, §13 sdk/acp | — |
| C10 | **[C] Ops/Admin Plane** — health/readiness/shutdown/runtime-control/dashboard in one self-registering router | `web/api/ops` Route(alias, group) auto-index | liveness vs readiness split · quitquitquit(auth'd) · log-level/toggles/tunables live-mutation (audit-logged) · BuildProperties GIT_SHA/BUILD_DATE · metrics query | §20 twitter-server 35 handlers staged; dashboards data from §16 analytics | — |
| C11 | **[C] Config Kernel** — typed strict config + patchable profiles in one | `core/config` `BaseConfig` + `platform.yaml` overlay | TML BaseConfig (extra=forbid, one_of, pretty_print yaml) + dsh patch-layer semantics (profile → home → --patch overlay on platform.yaml rows) + explicit `resolve(request): Spec` | §19 base_config.py, §13 profiles/patches, template platform.yaml existing | — |
| C12 | **[MM] Identity & Tenancy** — authn/authz/orgs/groups/keys under one provider switch | `identity/` `IdentityProvider` Protocol + RBAC tables | `local` (first) → OAuth/SSO → SCIM provisioning later; org→project→resource tenancy; group-scoped model/tool access | §16 open-webui RBAC+LDAP+SCIM routers/models, §18 dispatch org/project/team | — |
| C13 | **[C] Audit & Idempotency** — append-only trail + key replay protection as one compliance pair | `platform/{audit,idempotency}` | append-only event log (dsh session-log discipline) + Stripe-style Idempotency-Key middleware; incident/case audit trail = first domain consumer | §13 invariant, §18 dispatch report/incident records | fintech pack |
| C14 | **[MM] Sandbox & Execution** — filesystem+shell+code-run behind one workspace seam | `WorkspaceBackend` Protocol (fixes broken stub) | `local` (dev) · `docker` · remote sandboxes (E2B/Modal/Daytona pattern) — FS/subprocess share execution world so swap moves both | §8 deepagents backends, §9 open-swe sandbox-per-task, §13 e2b+sandbox(bwrap/Landlock/Seatbelt) | opt |
| C15 | **[C] Workflows** — durable graph workflows + human tasks in one runtime | `workflows/` `WorkflowRuntime` | `local` = langgraph StateGraph+checkpointer now → Temporal adapter later; approval gates via interrupts; FIRST domain workflow = dispatch incident state machine (signal→incident→task(HITL)→document→report) | §3 StateGraph, §4 TemporalDurability pattern, §17 canvas node types, §18 incident flow | `workflow-temporal` later |
| C16 | **[C] Knowledge Ingestion** — load→chunk→embed→index→cite as one pipeline | `IngestionPipeline.process(source)` | loaders: pypdf/docx/pptx + Docling/Tika options · chunking: langchain text-splitters · embed: C2 · index: C3 · citations attached to chunks | §14 splitters, §17 indexing_runner, §16 loaders/Tika/Docling list | opt heavy parsers |
| C17 | **[MM] Multimodal AI Surface** — image gen/edit, STT/TTS, vision, moderation via one gateway passthrough | same C1 gateway, capability-flagged | any-llm SUPPORTS_* flags route: image_generation/speech/transcription/moderation · local engines optional (ComfyUI/A1111/Whisper pattern) | §2 flags+endpoints, §16 engine lists, §5 image embeddings | per-capability extras |
| C18 | **[C] Evaluation & Usage Analytics** — traces, cost, quality in one observability stack | `operations/telemetry` + `platform/usage` | OTel vendor-neutral (traces/metrics/logs) · token/cost per user/model with C4 dual-window aggregation · eval harness (typed datasets, regression) | §20 stats/tracing, §17 otel distro+Langfuse/Phoenix mentions, §16 ELO/arena dashboards, §11 pydantic-evals | `opentelemetry-*` |
| C19 | **[C] Jobs & Reliability** — enqueue+retry+DLQ+rate-limit+breaker+outbox unified | `jobs.enqueue()` Protocol | taskiq/ARQ default · outbox relay already in template · circuit breaker + rate limit wrappers shared by every integration (contract requirement) | template outbox existing; llmchat §28 contract | existing deps |
| C20 | **[C] Web Research Tools** — search+browse+fetch as agent tools | tools registered in C6 | SearXNG/self-host default + provider APIs optional · fetch_url→markdown · browse pattern | §16 20+ providers, §9 fetch_url, §17 web tools | opt |

## 5. Fake→Real Kill List (P0 executes this)

| Kill | Replace With | Source |
|---|---|---|
| `FakeChatModel` prod path | `AnyLLMChatModel(acompletion, ollama local default)` | §2 |
| `FakeEmbeddingProvider` (hash 32-dim lie) | `FastEmbedProvider` bge-small-en-v1.5 real 384d ONNX | §5 |
| `graph.py` broken `langchain.agents.create_agent` | `langgraph.prebuilt.create_react_agent` + `InMemorySaver` | §3 |
| `workspace.py` `Protocol := object` stub | `WorkspaceBackend` real local/docker impls | §14 C14 |
| `mcp_bridge.py` stub | `MultiServerMCPClient.load_tools` | §6 |
| ad-hoc settings fields | `BaseConfig` strict kernel + platform.yaml patches | §19/§13 |
| no readiness/shutdown endpoints | ops plane C10 | §20 |

Tests stay deterministic WITHOUT fakes-in-prod: unit tests use scripted replies only inside `tests/_fakes.py` (test-private); CI green path = ollama container + fastembed CPU. `importorskip("langchain.agents")` removed once real import lands.

## 6. Phases (green-gated: generated-project pytest green before next)

**P0 Stabilize (hard gate)** — kill-list above + `BaseConfig` adopt + health/ready split + real deps behind Jinja guards (`enable_llm/vector/rag/agents` flags already exist). Verify: factory smoke tests + generated agentic `uv run pytest -q` green on ollama+fastembed, minimal green with none.
**P1 Core** — C11 config kernel, structured JSON logging+trace_id, build_info, RFC9457 done.
**P2 Platform** — C12 identity(local+RBAC), C13 audit+idempotency, files/notifications, data contracts both adapters.
**P3 Reliability** — C19 jobs/retries/DLQ/rate-limit/breaker/outbox; chaos test kill-worker-retry-DLQ.
**P4 AI Gateway** — C1 full surface + routing yaml + usage/cost capture hooks feeding C18.
**P5 Agents** — C5 multi-runtime + C6 tools/MCP + C7 skills/seam + C8 memory + budgets(tokens/time/cost beyond steps) + 3-layer guardrails + HITL(interrupts).
**P6 Knowledge** — C2+C3+C4+C16+C20: hybrid retrieval, rerank, citations, ingestion, research tools; contract tests per store mode.
**P7 Workflows** — C15 local runtime + interrupt approvals; Temporal adapter only when a real use-case lands.
**P8 Industry Packs** — fintech first (ledger double-entry append-only + C13 + C15 incident-style case flow §18) → saas/crm/erp/commerce.
**P9 DX** — `nk init/module/provider/doctor/generate`; mount C9 protocol server; deploy profiles; docs wiki.

Every phase PR ships: factory smoke test update + generated-project suite green + grep-guard (e.g. minimal has zero `langchain/fastembed/any_llm` imports).

## 7. Repo Index (all 16 TEMP clones — complete coverage)

| Repo | Map § | Role in Gold | Status in old plans (was gap) |
|---|---|---|---|
| any-llm | §2 | C1/C17/C2-hosted primary gateway | had Y |
| langgraph (+checkpoint deep-dive) | §3,§7 | C5-graph, C8 memory/checkpoint | had Y |
| pydantic-ai (+docs exhaustive) | §4,§11 | C5-pydantic engine, durable-exec pattern | had Y |
| fastembed (+models exhaustive) | §5,§12 | C2 all four embedding modes, C3 rerank | had Y |
| langchain-mcp-adapters | §6 | C6 MCP transport | had Y |
| deepagents | §8 | C7 skills, C14 backends | had Y |
| open-swe | §9 | C6 curation, C14 sandboxes | had Y |
| agent-protocol | §10 | C9 sessions/runs/store API | had Y |
| **deepseek-harness (dsh)** | §13 | C7 seam/waterfall, C11 patch layers, C8 log invariant, C13 discipline, C14 sandbox backends | **was MISSING elsewhere** |
| langchain | §14 | reference interfaces, C16 splitters | ref only |
| openwiki | §15 | C16 connector patterns reference | ref only |
| **open-webui** | §16 | C3 hybrid RAG, C12 RBAC/LDAP/SCIM, C20 search providers, multimodal engines, C18 analytics | **was MISSING elsewhere** |
| **dify** | §17 | C1 alt, C3 rag/indexing, C15 workflow nodes, C18 LLMOps/otel | refined-only stub |
| **dispatch** | §18 | C13 audit pattern, C15 first domain workflow, C12 tenancy | had Y (harvest) |
| **the-algorithm-ml** | §19 | C4 ranker, C11 BaseConfig, C4 windowed usage | **was MISSING elsewhere** |
| **twitter-server** | §20 | C10 entire ops plane | **was MISSING elsewhere** |

## 8. Risks

Template drift → smoke test per phase is merge gate · prune breaks imports → grep-guards in CI · heavy-dep leak → minimal lockfile assertion · fake regression → fakes allowed ONLY in `tests/_fakes.py` · fintech overreach → ledger append-only from day one, no reversible migrations.

## 9. Single Checklist

P0 kill-list (§5) → P1..P9 each gated by §6 verify line → gold definition (§2) audited before calling anything gold.
