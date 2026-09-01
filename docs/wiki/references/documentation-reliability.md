---
id: documentation-reliability
title: Documentation reliability
description: How to keep EVA template documentation aligned with generated behavior.
---

[← INDEX](../INDEX.md)

Documentation is part of the template contract. A page must describe what a
freshly generated project can do, which options enable it, and what remains
the consumer's responsibility.

## Update workflow

When changing a capability:

1. Update the implementation and its contract tests.
2. Update the profile, use-case catalog, or option validation if the capability
   is selectable.
3. Generate at least one affected profile and, when applicable, one affected
   use case.
4. Run `nk doctor`, `nk validate`, `nk check`, and the relevant integration
   tests.
5. Update the matching page under `docs/wiki/` and link the implementation,
   configuration, route, and test anchors.
6. Build the Docusaurus site with `npm run build`.

## What every service page should answer

- Which profile or option enables the service?
- Is it a route, library contract, adapter, worker, or deployment artifact?
- What are the configuration and dependency requirements?
- Which authentication, tenant, CSRF, or scope checks apply?
- Is the default implementation durable and multi-process safe?
- How is the service replaced or extended?
- Which tests provide evidence?
- Which behavior is explicitly out of scope?

## Truth labels

Use precise language:

- **Generated** — rendered by a profile or option.
- **Available** — present in the generated source tree.
- **Mounted** — included in application routing or lifecycle.
- **Configured** — wired to a selected provider or dependency.
- **Durable** — survives restart and coordinates across workers.
- **Verified** — covered by the relevant live or contract test.

Do not use “production-ready” for a module merely because it exists in the
template. In-memory stores, protocol implementations, stubs, and optional
provider adapters must be named as such.

## Scope boundaries

Publish stable usage and architecture under `docs/wiki/`. Keep planning
documents in `docs/plans/` and append-only session notes out of the public
site. Runtime API schemas belong to the generated application's OpenAPI
document; Docusaurus should explain how to use and verify them, not invent
schemas that can drift.

## Review checklist

- [ ] Links point to current source files and generated routes.
- [ ] Profile and option names match `fastapi_template/profiles.py`.
- [ ] Use-case names and profile mappings match the use-case catalog.
- [ ] `platform.yaml` records the requested use case and resolved profile.
- [ ] Security claims match the generated router and settings.
- [ ] Durability and provider boundaries are explicit.
- [ ] Commands work from a generated project root.
- [ ] Docusaurus build passes with no broken links.
- [ ] Generated profile CI remains green.

