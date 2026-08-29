# API Studio

This React application powers the generated project's branded documentation
surfaces: `/api/docs`, `/api/swagger`, and `/api/redoc`.

Built with [Vite](https://vite.dev), React, TypeScript, Tailwind CSS v4 and
[shadcn/ui](https://ui.shadcn.com) components.

## Build

The source is compiled into
`../{{cookiecutter.project_name}}/static/studio/dist/`. The generated API
serves stable `studio.js` and `studio.css` files; Docker builds the bundle
automatically.

```bash
npm ci
npm run typecheck
npm run build
```

The build output is a generated artifact and is git-ignored.

## Development

```bash
# terminal 1 — the API
uv run nk dev

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

The API logo is supplied by
`../{{cookiecutter.project_name}}/static/branding/logo.png`. Replace that
asset to customize the generated project's branding across the favicon,
navigation bar, and documentation shell.

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
