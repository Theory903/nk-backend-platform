---
name: platform-guide
description: Explains the generated NK platform layout and guides agents to the correct extension points.
---

# NK Platform Guide

Use this guide when asked about the project structure, where functionality belongs, or how to add new agent capabilities.

## Project Layout

- `platform.yaml` — active platform profile, providers, and module switches.
- `data/` — repository protocols and the configured storage adapter.
- `agents/` — agent runtimes, tool registry, skills, and agent-specific execution components.
- `core/` — shared infrastructure such as Problem+JSON errors, configuration, and identifiers.

## Adding Capabilities

Prefer registering new agent capabilities through:

`agents.tools.agent_tool`

This keeps capabilities available to both:

- loop runtimes
- graph runtimes

Avoid implementing runtime-specific tool registration unless there is a clear architectural reason.

## Extension Rule

When adding functionality:

1. Put shared infrastructure in `core/`.
2. Put persistence abstractions and adapters in `data/`.
3. Put agent capabilities and tools in `agents/`.
4. Use `platform.yaml` for provider/profile/module configuration.
5. Prefer existing extension points before introducing new runtime-specific abstractions.