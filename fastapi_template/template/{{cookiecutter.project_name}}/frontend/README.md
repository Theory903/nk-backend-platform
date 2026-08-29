# React API documentation

The React documentation application served at `/api/docs`, `/api/swagger`, and
`/api/redoc`.

Built with [Vite](https://vite.dev), React, TypeScript, Tailwind CSS v4 and
[shadcn/ui](https://ui.shadcn.com) components.

## Setup

The React docs ship as source. Build once before running the API directly; the
Dockerfile builds the bundle automatically for container images.

```bash
cd frontend
npm install
npm run build
```

The bundle is emitted to `../{{cookiecutter.project_name}}/static/studio/dist/`
with stable filenames (`studio.js`, `studio.css`) and is served by FastAPI on
all three documentation routes.
It is a build artifact and is git-ignored.

## Development

```bash
# terminal 1 — the API
uv run python -m {{cookiecutter.project_name}}

# terminal 2 — the Studio with hot reload
cd frontend && npm run dev
```

`npm run dev` serves on <http://localhost:5173> and proxies `/api` and
`/static` to the FastAPI app. Override the target with `API_ORIGIN`:

```bash
API_ORIGIN=http://127.0.0.1:9000 npm run dev
```

Run `npm run typecheck` to check types without emitting.

## Adding components

The project is configured for the shadcn CLI:

```bash
npx shadcn@latest add dialog
```

Components land in `src/components/ui/`. The `@/` alias maps to `src/`.

## Theming

The React app owns the documentation palette:

| File | Used by |
| --- | --- |
| `src/index.css` | the article, Swagger, and ReDoc React views |
| `../{{cookiecutter.project_name}}/static/studio/tokens.css` | legacy fallback |

The app uses a Baeldung-inspired editorial palette. The second file is only
used by the pre-build fallback and legacy static assets.

## Layout

```
src/
  App.tsx                 article, Swagger, and ReDoc views
  hooks/use-studio.ts     all Studio state: schema, request, response, history
  lib/openapi.ts          OpenAPI 3 parsing, $ref resolution, URL building
  lib/curl.ts             cURL export
  lib/format.ts           status, size and duration formatting
  lib/rows.ts             editable key/value row model
  lib/storage.ts          guarded localStorage helpers
  components/             Studio features
  components/ui/          shadcn primitives
```
