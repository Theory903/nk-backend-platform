---
id: api-reference
title: API reference and route map
description: Conceptual route map and runtime OpenAPI workflow for generated services.
---

[← INDEX](../INDEX.md)

Docusaurus documents the stable concepts and workflows. The generated
application remains the authority for exact schemas, security requirements,
and enabled routes through its OpenAPI document.

## Runtime references

Start a generated service:

```bash
uv run nk dev
```

Then use:

- `/api/openapi.json` — machine-readable contract;
- `/api/docs` — API Studio with editorial documentation;
- `/api/swagger` — interactive Swagger UI;
- `/api/redoc` — reference-oriented ReDoc;
- `/api/health` — dependency-free liveness;
- `/api/ready` — startup and dependency readiness;
- `/api/metrics` — Prometheus metrics when enabled.

The API Studio source is in
`{{cookiecutter.project_name}}/web/api/docs/` and the route composition is in
`{{cookiecutter.project_name}}/web/application.py` and
`{{cookiecutter.project_name}}/web/api/router.py`.

## Stable route families

The exact route set is profile- and option-dependent:

| Route family | Enabled by | Notes |
| --- | --- | --- |
| `/api/echo/` | REST routers | Minimal example endpoint |
| `/api/v1/<domain>/<module>/` | Database + module | Generated business routers |
| `/api/auth/*`, `/api/users/*` | Users | Identity and user lifecycle |
| `/api/auth/sessions`, `/api/auth/api-keys` | Users | Platform identity extensions |
| `/api/v1/answers` | Traditional RAG | Authorization-first answers |
| `/api/v1/runs`, `/api/v1/threads/*` | Agents | Bounded agent protocol |
| `/api/mcp`, `/mcp` | Agents | MCP integration surface |
| `/api/files*` | Users/files | File metadata and storage boundary |
| `/scim/v2/Users` | SCIM integration | Requires consumer repository wiring |
| `/graphql` | GraphQL option | Optional GraphQL surface |

Business, file, broker, cache, GraphQL, SCIM, and metrics routes require the
generated security configuration when identity is enabled. Do not infer that
a route is public from its path alone.

## Generate an application-specific reference

For a deployable service, export OpenAPI from the generated application
rather than copying this route table. No HTTP server is required — the CLI
loads `get_app()` and writes the schema. Any future route registered on the
app is included automatically on the next export:

```bash
uv run nk export-openapi
```

This writes `docs/openapi.json` (Postman-ready: server variables, login/register
examples, fixed OAuth2 token URL) and `docs/postman-environment.json`
(`baseUrl`, `testEmail`, `testPassword`, `accessToken`, …).

**Postman:** import the environment first, then the OpenAPI file, select **NK
Local Dev**, run Register → JWT Login, set `accessToken`.

Alternatively, while the API is running:

```bash
curl --fail http://127.0.0.1:8000/api/openapi.json \
  --output docs/openapi.json
```

Review the output after every profile or route change. The output is
application-specific and may contain generated business modules, so it should
not be committed to the template's generic documentation unless it is a
stable example fixture.

## Authentication behavior

Use the generated OpenAPI security schemes and identity configuration to
determine whether a request uses bearer JWT, cookie session, API key, or
another adapter. Browser cookie mutations require the CSRF header. Bearer and
scoped API-key requests do not use cookie CSRF.

## Contract anchors

- Composition: `web/application.py`
- Routing and protection: `web/api/router.py`
- API Studio: `web/api/docs/views.py`
- Identity HTTP: `identity/http.py`
- Knowledge API: `web/api/knowledge.py`
- Agent protocol: `web/api/agent_protocol.py`
- Operational views: `web/api/monitoring/views.py`
- Route tests: generated `tests/` files matching the capability

