---
id: identity
title: Identity, authorization, and tenancy
description: Security model and configuration boundaries for generated services.
---

[← INDEX](../INDEX.md)

Identity is a platform capability, not a business module. When users are
enabled, generated routes follow a default-deny flow:

```text
trusted host → public health allowlist → authentication
→ permission and tenant checks → request limits → handler
→ durable policy → audit and observability
```

## HTTP surface

The public identity contract is assembled in
`{{cookiecutter.project_name}}/identity/http.py`:

- `/api/auth/*` — registration, login, reset, and verification routes;
- `/api/users/*` — user lifecycle routes;
- `/api/auth/sessions` — session operations;
- `/api/auth/api-keys` — API key operations.
- `/api/auth/csrf` — issue a token bound to the authenticated browser cookie.

The exact methods and schemas are always available in the generated
`/api/openapi.json`. Legacy routers may remain in the template for
compatibility but are not necessarily mounted.

## Authentication options

The identity package contains replaceable implementations for:

- JWT access and refresh tokens;
- browser cookie sessions and CSRF;
- scoped API keys and rotation;
- durable Redis/SQL session and cookie-token stores that persist only
  keyed digests of bearer credentials;
- MFA/TOTP, password reset, email verification, and throttling;
- local, LDAP, OAuth2, OIDC, and magic-link provider adapters;
- service accounts and security events.

Provider libraries and credentials are deployment choices. Enabling local
identity does not configure an external identity provider.

## Authorization and request trust

Headers are untrusted input. Authentication and tenant resolution place
validated values on `request.state`; downstream authorization must use those
trusted values rather than accepting an organization header by itself.

Use the dependency and policy modules as the implementation reference:

- `identity/deps.py` — current-user and request dependencies;
- `identity/permissions.py` — scopes and authorization;
- `identity/principal.py` — principal representation;
- `identity/tenant_context.py` and `platform/tenancy.py` — tenant context;
- `core/security.py` — shared security controls.

Cookie-authenticated browser mutations (opaque sessions and JWT cookies)
require the configured CSRF header. Bearer and scoped API-key authentication
are not cookie flows and do not use cookie CSRF.

## Tenancy and database isolation

Tenant membership resolves a `TenantContext`; PostgreSQL row-level security
can provide defense in depth through `data/rls.py` and the generated
database migrations. A production application must verify that the
application's tenant context variable and the database policy/migration use
the same name and transaction scope.

RLS does not replace application authorization. Test both membership checks and
database isolation with a real PostgreSQL deployment before treating tenancy
as production-certified.

The generated Compose topology initializes PostgreSQL with a separate
administrative role and runs the API as a `NOSUPERUSER NOBYPASSRLS` runtime
role. Keep those credentials separate; the API must never use the
initialization role.

## Production requirements

Production startup is fail-closed and requires, at minimum:

- an explicit host allowlist;
- non-development reload settings;
- a 32-byte user secret;
- an identity provider;
- a durable authentication/session store.

Use a secret manager or deployment environment for secrets. Do not use
development credentials, an ephemeral in-memory session store, or an
unauthenticated edge as production controls.

## Evidence

- HTTP composition:
  `fastapi_template/template/{{cookiecutter.project_name}}/{{cookiecutter.project_name}}/identity/http.py`
- Tenant context: generated `identity/tenant_context.py`,
  `platform/tenancy.py`, and `data/rls.py`
- Contract tests: generated `tests/test_identity_hardened.py`,
  `test_identity_production.py`, `test_tenant_context.py`, and
  `test_rls_isolation.py`

