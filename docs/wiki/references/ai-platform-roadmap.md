<!-- NK AI Platform Master Roadmap · updated 2026-09-01 · status: active -->

# NK AI Application Platform — Master Architecture

[← Wiki index](../INDEX.md) · [Phases P0–P30](ai-platform-phases.md) · [OSS reference map](ai-platform-oss-map.md)

**Status:** Active · **Target:** Portable AI application operating runtime  
**Principle:** Build shared primitives once; compose agents, skills, and workflows from plugins.

Generated apps remain normal FastAPI applications. OSS projects are **engines, adapters, or references** — never the public NK API.

```text
Application → NK Interface → Adapter → OSS Engine
```

**References:** `temp/oss/` · `platform/oss_manifest.yaml` · `./scripts/clone_ai_platform_refs.sh`

---

## 1. Vision

NK is a **developer-first AI application runtime**, not an LLM feature template. Generated apps include:

model routing · agent execution · durable workflows · tools · MCP · A2A · skills · RAG · GraphRAG · memory · browser · code agents · multimodal · sandboxing · approvals · evaluation · replay · red team · observability · cost controls · autonomous optimization

---

## 2. Target architecture

```text
                    FastAPI API (REST / SSE / WS)
                              │
                    NK Kernel (plugins + lifecycle)
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
   Model Gateway        Agent Runtime         Tool Gateway
         │                    │                    │
         └────────────────────┼────────────────────┘
                              ▼
                    Context Runtime
                    (RAG · memory · skills)
                              ▼
                    Session Runtime
                    (events · resume · fork · replay)
                              ▼
                    Agent Harness
                    (eval · chaos · regression)
                              ▼
              Security + Policy + OTel GenAI
                              ▼
              Autonomous Optimization (autoresearch)
```

**Routing ladder:** Simple Q&A → `LoopRuntime` · tool loop → Agent runtime · workflow → Graph runtime · multi-agent → Supervisor · long-running → Durable + checkpoint.

---

## 3. Eight core primitives

| # | Primitive | Responsibility |
|---|-----------|----------------|
| 1 | **Plugin Kernel** | Discovery, lifecycle, dependency graph, capabilities |
| 2 | **Model Gateway** | Capability routing, fallback, budgets, semantic cache |
| 3 | **Agent Runtime** | Loop / graph / supervisor / subagents / modes |
| 4 | **Tool Gateway** | Native + MCP + A2A; policy, approval, audit |
| 5 | **Context Runtime** | RAG, memory, skills, context builder |
| 6 | **Session Runtime** | Append-only events, resume, fork, replay |
| 7 | **Agent Harness** | Scenarios, trajectory eval, chaos, fixtures |
| 8 | **Observability/Security** | OTel GenAI, injection defense, sandbox |

Feature packs (`llm/features/*`) are **thin compositions** over these primitives.

---

## 4. Plugin kernel (DeepSeek Harness reference)

Inspired by [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) (*architecture reference only — dev preview, MIT*):

```text
nk/kernel/ — plugins, registry, lifecycle, events, capabilities
```

Every plugin declares: `name`, `type`, `provides`, `requires`, `permissions`, `configuration`, `health`.

Types: `model` · `agent` · `tool` · `skill` · `memory` · `retriever` · `vector_store` · `sandbox` · `evaluator` · `workflow` · `scheduler` · `protocol` · `storage` · `security`

**Rule:** Implement NK's stable plugin contract. Do not depend on DeepSeek Harness internal APIs.

---

## 5. Session runtime (events + replay)

Every run is an append-only event stream:

`RunStarted` · `ContextBuilt` · `ModelCalled` · `ToolCalled` · `MemoryRead/Write` · `ApprovalRequested` · `RunCompleted`

```bash
nk ai replay <id> | fork <id> | resume <id> | inspect <id>
```

Deterministic CI: record tool I/O → fixtures → harness replay.

---

## 6. Skill runtime (gstack reference)

[gstack](https://github.com/garrytan/gstack) (*MIT, reference only*) → NK-native skills under `skills/`:

```text
/office-hours · /plan-eng · /review · /qa · /ship · /retro · /security-review
```

Skill manifest (machine-readable):

```yaml
name: plan-eng-review
tools: [filesystem.read, git.diff]
permissions: { network: false, filesystem: read }
evaluation: { harness: engineering-review }
```

Preset: `skills.preset: gstack-compatible` — NK-native equivalents, not vendor copy.

---

## 7. Autonomous research (Karpathy autoresearch)

[karpathy/autoresearch](https://github.com/karpathy/autoresearch) → `nk/research/`:

```text
Hypothesis → Change → Run → Evaluate → keep | revert → next
```

Optimizes: prompts · RAG config · chunking · agent graphs · model routing · cost/latency — **never modifies production directly**.

Karpathy repos (`nanochat`, `nanoGPT`, `llm.c`, …) are **reference/minimalism** guides — every subsystem has production + minimal paths.

---

## 8. Runtime modes

| Mode | Composition |
|------|-------------|
| `minimal` | Model + basic tools (benchmark) |
| `standard` | + tools, skills, memory, RAG |
| `research` | + search, browser, citations |
| `code` | + editor, shell, git, sandbox |
| `browser` | + browser-use adapter |
| `benchmark` | Deterministic tools + harness |
| `autonomous` | + scheduler, durable state, optimization |
| `creator` | NK Studio — build agent/skill/workflow manifests |

---

## 9. Context + RAG 2.0

Retrieval fusion: dense + lexical + sparse + metadata + graph → rerank → context builder → LLM.

Backends auto-resolve: `dev/small → pgvector` · `scale → Qdrant` · optional Haystack adapter.

GraphRAG facts carry: `source`, `confidence`, `valid_from/to`, conflict resolution.

Memory 2.0: working → episodic → semantic; consolidation; conflict resolution; Redis in prod.

---

## 10. Tool gateway + MCP + A2A

```text
MCP  = agent → tool/resource
A2A  = agent → agent
HTTP = application → API
```

MCP is **not** a security boundary. All tools pass: schema validation · permissions · budgets · risk · approval · audit · sandbox.

---

## 11. Harness (first-class product surface)

```bash
nk ai harness run | record | replay | chaos | redteam | benchmark
```

Eval adapters: Ragas · DeepEval · Harness Evals · Promptfoo CLI · NK-native.

Dimensions: correctness · groundedness · trajectory · tool correctness · safety · latency · cost.

---

## 12. Security invariants (automated tests)

- Retrieved content = **data**, never auto-executed as instructions
- Tools cannot exceed declared permissions
- Critical tools require approval; failed approval ≠ implicit grant
- Tenants isolated; secrets filtered from context/logs
- Budgets enforced; agents cannot raise their own limits
- Production writes require idempotency keys

---

## 13. Profiles

| Profile | Stack |
|---------|-------|
| `production-ai-local` | FastAPI + Postgres + pgvector + Redis + Ollama + worker + harness — **no API keys** |
| `production-ai` | Above + optional external providers + SearXNG + security |
| `production-ai-scale` | + Qdrant + NATS + HPA + distributed tracing |

---

## 14. Feature packs (compositions)

| Pack | Composed from |
|------|---------------|
| Agentic RAG | Agent + RAG + Harness |
| Deep Research | Agent + Search + RAG + Browser + Harness |
| GraphRAG | RAG + Graph + Fusion |
| Multi-Agent | Supervisor + A2A |
| MCP Assistant | Agent + Tool Gateway + MCP |
| Browser / Code Agent | Agent + Sandbox + adapter |
| Memory Agent | Memory + consolidation |
| Always-On | Durable workflow + scheduler |
| Engineering Agent | Skills (gstack-style) + Code + Harness |
| Autonomous Research | Harness + Experiment runtime |

Target **18–20 packs** — all thin facades.

---

## 15. AI-native SDLC (gstack-inspired)

```text
Idea → Office Hours → Product/Eng/Design Review → Implementation
  → Code Review → QA → Security → Benchmark → Canary → Deploy → Observe → Retro → Learn
```

NK = **AI application runtime** + **AI software factory runtime**.

---

## 16. Critical path

```text
P0 Dev plane → P1 Storage → P2 Model Gateway → P3 Agent Runtime → P4 Tool Gateway
  → P13 Sessions → P14 Harness → P15 Eval → P18 Security → P19 OTel
  → P21 Plugin Kernel → P22 Skills → P26 Experiments → P30 Self-improving
```

Full phase list: [ai-platform-phases.md](ai-platform-phases.md)

---

## 17. Implementation batches

| Batch | Scope |
|-------|-------|
| A | P0 dev plane + `nk ai doctor` |
| B | P1 storage abstraction |
| C | P2 model gateway (capabilities) |
| D | P3 agent runtime refactor |
| E | P4 tool gateway + MCP + A2A |
| F | P5–P7 RAG/memory/graph |
| G | P8–P12 agent capabilities |
| H | P13–P17 sessions/harness/chaos |
| I | P18–P20 security/otel/scale |
| J | P21–P25 plugin/skills/modes |
| K | P26–P28 autoresearch |
| L | P29–P30 fleet/self-improvement |

---

## 18. What NK owns vs OSS provides

**NK owns:** interfaces · plugin contracts · session model · tool policy · harness · security · budgets · CLI · generated structure

**OSS provides:** execution engines · protocols · storage · evaluators · reference patterns

**Strategic rule:** NK is the operating layer that makes OSS projects composable — not a copy of every OSS project.

---

## 19. Definition of done

```bash
fastapi-template --profile production-ai-local myapp && cd myapp
uv sync --extra ai-platform --extra ai-eval
uv run nk dev && uv run nk ai doctor    # all green
uv run nk ai harness run                # seeded demo passes
```

No manual worker · no manual ingest · no MCP wiring · no API keys (local profile).

---

## 20. OSS ecosystem map

| Layer | References |
|-------|------------|
| Architecture | DeepSeek Harness (plugin/session) |
| Skills | gstack |
| Research | Karpathy autoresearch + nanochat |
| Agent runtime | LangGraph, smolagents, OpenHands |
| RAG | Haystack, Qdrant, pgvector, Ragas |
| Protocols | MCP SDK, A2A SDK |
| Browser | Browser Use |
| Eval | Harness Evals, DeepEval, Promptfoo |
| Models | LiteLLM, Ollama |
| Observability | OTel GenAI conventions |

Full manifest with licenses and integration modes: [ai-platform-oss-map.md](ai-platform-oss-map.md)

[← Wiki index](../INDEX.md)
