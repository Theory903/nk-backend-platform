<!-- Architecture · updated 2026-08-31 · status: active -->

# Architecture

[← INDEX](INDEX.md)

NK is a **framework on top of FastAPI**: cookiecutter factory + profiles + contracts + `nk` CLI.

- Profiles expand into BuilderContext (`fastapi_template/profiles.py`)
- Feature deps validated before bake (`fastapi_template/validation.py`)
- Template prune via `conditional_files.toml`
- Generated apps expose `nk` (`doctor` / `validate` / `check` / `dev` / `build` / `generate`)
- Trust model: headers = input; `request.state` after auth/tenant = trust
- AI fakes live only in `tests/_fakes.py`; real adapters under `ai/providers/`

North-star design: `docs/plans/2026-08-24-nk-system-design.md`  
Capability phases: `.sisyphus/plans/gold-master-plan.md`

## Security control plane

Generated applications use a default-deny request flow:

```text
edge / trusted host
  -> public health allowlist
  -> authentication
  -> permission + tenant checks
  -> request limits and validation
  -> business or infrastructure handler
  -> durable store / database policy
  -> audit and observability
```

For profiles with identity enabled, business, file, broker, cache, GraphQL,
SCIM, and metrics routes require authentication. Health and readiness remain
public for orchestrator probes. Browser session mutations require the
CSRF header; bearer and scoped API-key requests do not use cookie CSRF.

Production startup is fail-closed: it requires an explicit host allowlist,
non-development reload settings, a 32-byte user secret, an identity provider,
and a durable authentication-store backend. OIDC/SAML providers, mTLS/PKI,
cloud IAM, secret managers, and edge WAFs remain deployment integrations and
must be configured outside the generated application.

The full security architecture reference lives at
[`SECURITY-ARCHITECTURE.md`](../../SECURITY-ARCHITECTURE.md).
