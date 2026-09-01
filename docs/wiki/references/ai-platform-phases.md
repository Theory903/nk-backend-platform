<!-- AI Platform Phases · updated 2026-09-01 · status: active -->

# NK AI Platform — Phases P0–P30

[← Master roadmap](ai-platform-roadmap.md) · [OSS map](ai-platform-oss-map.md)

---

## Foundation (P0–P4)

| Phase | Deliverable | Zero-effort outcome |
|-------|-------------|---------------------|
| **P0** | Ollama, Postgres, pgvector, Redis, worker, scheduler, auto-seed, `nk dev`, `nk ai doctor` | One command, demo-ready |
| **P1** | Memory/vector/lexical auto-select; Qdrant adapter | Survives restart |
| **P2** | Capability-based model gateway, fallback, budgets, semantic cache | `capability: reasoning` not model names |
| **P3** | LoopRuntime, GraphRuntime, SupervisorRuntime, checkpoint, cancellation | Routing ladder |
| **P4** | Tool gateway, MCP SDK, A2A, policy, approval, audit | External tools from yaml |

## Context (P5–P7)

| Phase | Deliverable |
|-------|-------------|
| **P5** | RAG 2.0: hybrid fusion, reranking, context builder, citations |
| **P6** | GraphRAG: provenance, confidence, temporal facts, conflict resolution |
| **P7** | Memory 2.0: working/episodic/semantic, consolidation, Redis backend |

## Agent capabilities (P8–P12)

| Phase | Deliverable |
|-------|-------------|
| **P8** | Multi-agent supervisor + A2A delegation |
| **P9** | Multimodal: vision, audio, streaming |
| **P10** | Browser agent (browser-use + sandbox + domain policy) |
| **P11** | Code agent (smolagents + sandbox + git/test) |
| **P12** | Deep research: search, citations, source verification |

## Harness (P13–P17)

| Phase | Deliverable |
|-------|-------------|
| **P13** | Session runtime: append-only events, resume, fork, replay |
| **P14** | Harness runner, scenarios, trajectory capture |
| **P15** | Eval adapters: Ragas, DeepEval, Harness Evals, Promptfoo |
| **P16** | Deterministic tool replay fixtures for CI |
| **P17** | Chaos harness: failure injection + recovery verification |

## Security / ops (P18–P20)

| Phase | Deliverable |
|-------|-------------|
| **P18** | Security: injection, tool poisoning, PII, sandbox, approvals |
| **P19** | OTel GenAI spans, cost/latency metrics |
| **P20** | Scale: HPA, tenant isolation, rate limits, distributed queue |

## Architecture layer (P21–P25)

| Phase | Deliverable |
|-------|-------------|
| **P21** | Plugin kernel (DeepSeek Harness reference) |
| **P22** | Skill runtime + manifests |
| **P23** | gstack-compatible engineering skills |
| **P24** | Creator / NK Studio |
| **P25** | Runtime mode presets (minimal → autonomous) |

## Autonomous platform (P26–P30)

| Phase | Deliverable |
|-------|-------------|
| **P26** | Experiment runtime: hypotheses, mutations, leaderboard, rollback |
| **P27** | Autoresearch: prompt/RAG/agent/routing optimization (Karpathy ref) |
| **P28** | Agent-generated evaluations from production failures |
| **P29** | Agent fleet: scheduling, concurrency, shared knowledge |
| **P30** | Self-improving loop: telemetry → experiment → harness → canary → deploy |

---

## Critical path (do not implement sequentially)

```text
P0 → P1 → P2 → P3 → P4 → P13 → P14 → P15 → P18 → P19 → P21 → P22 → P26 → P30
```

Branches after P4: P5–P12 (capabilities), P16–P17 (replay/chaos), P23–P25 (skills/studio).

---

## Failure matrix (every phase gets tests)

LLM timeout · malformed JSON · context overflow · empty RAG · MCP disconnect · tool loop · agent loop · runaway tokens · worker crash · SSE disconnect · approval timeout · tenant leakage · eval nondeterminism → each maps to harness chaos scenario.

[← Master roadmap](ai-platform-roadmap.md)
