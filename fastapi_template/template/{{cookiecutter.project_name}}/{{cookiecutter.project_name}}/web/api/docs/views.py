"""API documentation surfaces: one React application with three views.

The React application in ``frontend/`` renders the article at ``/api/docs`` and
the branded Swagger and ReDoc views at ``/api/swagger`` and ``/api/redoc``.
This module serves the HTML shell that boots the compiled bundle from
``/static/studio/dist``.

NOTE FOR TEMPLATE MAINTAINERS
    Cookiecutter renders this file through Jinja2, so a doubled open brace
    anywhere in the source is parsed as the start of a Jinja expression and
    breaks project generation. Embedded CSS and JavaScript therefore live in
    plain string constants and use placeholder tokens with ``str.replace``,
    rather than f-strings or ``str.format`` which would require doubling every
    brace.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.openapi.docs import get_swagger_ui_oauth2_redirect_html
from fastapi.responses import HTMLResponse

router = APIRouter()

# <package>/web/api/docs/views.py -> <package>/static
_STATIC_DIR = Path(__file__).resolve().parents[3] / "static"
_DIST_DIR = _STATIC_DIR / "studio" / "dist"
_BUNDLE_JS = _DIST_DIR / "studio.js"
_BUNDLE_CSS = _DIST_DIR / "studio.css"

def _asset_version(path: Path) -> str:
    """Cache-busting token derived from the file's mtime.

    The bundle is emitted with stable filenames so this module can reference it
    without reading a build manifest; the query string handles invalidation.
    """
    try:
        return str(int(path.stat().st_mtime))
    except OSError:
        return "0"


def _head(*, title: str, subtitle: str, extra_css: tuple[str, ...] = ()) -> str:
    """Shared fallback ``<head>`` shown before the React bundle is built."""
    links = "\n  ".join(
        f'<link rel="stylesheet" href="{escape(href, quote=True)}"/>'
        for href in extra_css
    )

    return f"""  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{escape(title)} · {escape(subtitle)}</title>
  <link rel="icon" href="/static/branding/logo.png"/>
  <link rel="stylesheet" href="/static/studio/tokens.css"/>
  {links}"""


def _chrome(
    *,
    title: str,
    subtitle: str,
    active: str,
    openapi_url: str,
    extra_actions: str = "",
) -> str:
    safe_title = escape(title)
    safe_openapi_url = escape(openapi_url, quote=True)

    def tab(href: str, label: str, key: str) -> str:
        cls = "active" if active == key else ""
        current = ' aria-current="page"' if active == key else ""
        return (
            f'<a class="{cls}" href="{escape(href, quote=True)}"{current}>{label}</a>'
        )

    actions = ""
    if extra_actions.strip():
        actions = f'<div class="nk-actions">{extra_actions}</div>'

    return f"""
<header class="nk-bar">
  <div class="nk-bar-left">
    <a class="nk-brand" href="/api/docs" aria-label="API Studio home">
      <img src="/static/branding/logo.png" alt="" width="28" height="28"/>
      <div class="nk-brand-copy">
        <strong id="app-title">{safe_title}</strong>
        <span id="app-subtitle">{escape(subtitle)}</span>
      </div>
    </a>

    <nav class="nk-tabs" aria-label="Documentation views">
      {tab("/api/docs", "Studio", "studio")}
      {tab("/api/swagger", "Swagger", "swagger")}
      {tab("/api/redoc", "ReDoc", "redoc")}
    </nav>
  </div>

  <div class="nk-bar-right">
    <nav class="nk-links" aria-label="Resources">
      <a href="{safe_openapi_url}">OpenAPI</a>
      <a href="/api/health">Health</a>
    </nav>
    {actions}
  </div>
</header>
"""


# ---------------------------------------------------------------------------
# API Studio
# ---------------------------------------------------------------------------


def _studio_html(*, title: str, openapi_url: str, surface: str = "article") -> str:
    version = _asset_version(_BUNDLE_JS)
    surface_title = {
        "article": "Baeldung",
        "swagger": "Swagger UI",
        "redoc": "ReDoc",
    }.get(surface, "Documentation")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{escape(title)} · {surface_title}</title>
  <link rel="icon" href="/static/branding/logo.png"/>
  <link rel="stylesheet" href="/static/studio/dist/studio.css?v={version}"/>
</head>
<body data-openapi="{escape(openapi_url, quote=True)}" data-title="{escape(title)}" data-surface="{escape(surface, quote=True)}">
  <div id="root"></div>
  <script type="module" src="/static/studio/dist/studio.js?v={version}"></script>
</body>
</html>"""


def _react_docs_response(
    *, title: str, openapi_url: str, surface: str
) -> HTMLResponse:
    if not (_BUNDLE_JS.exists() and _BUNDLE_CSS.exists()):
        return HTMLResponse(
            _studio_build_required_html(title=title, openapi_url=openapi_url),
            status_code=503,
        )

    return HTMLResponse(
        _studio_html(title=title, openapi_url=openapi_url, surface=surface)
    )


# Plain string: braces must stay single so Jinja2 leaves this file alone.
_SETUP_CSS = """
    .setup { max-width: 640px; margin: 0 auto; padding: 48px 24px; }
    .setup h1 { font-size: 20px; margin: 0 0 8px; }
    .setup p { color: var(--text-secondary); line-height: 1.6; margin: 0 0 16px; }
    .setup pre {
      background: var(--bg-input); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 14px 16px; overflow-x: auto;
      font-family: var(--mono); font-size: 12.5px; color: var(--text);
    }
    .setup code { font-family: var(--mono); }
    .setup a { color: var(--accent); }
"""


def _studio_build_required_html(*, title: str, openapi_url: str) -> str:
    """Shown when ``frontend/`` has not been built yet.

    The template ships the documentation UI as source, so a freshly generated
    project has no bundle until the developer builds it.
    """
    return f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
{_head(title=title, subtitle="API Studio", extra_css=("/static/studio/shell.css",))}
  <style>{_SETUP_CSS}</style>
</head>
<body>
  <div class="nk-shell">
{_chrome(title=title, subtitle="API Studio", active="studio", openapi_url=openapi_url)}
    <main class="nk-stage">
      <div class="setup">
        <h1>React documentation needs a build</h1>
        <p>
          Swagger UI, ReDoc, and the article reader are one React application
          that ships as source. Build it once to enable all three views.
        </p>
        <pre><code>cd frontend
npm install
npm run build</code></pre>
        <p>
          Use <code>npm run dev</code> for hot reload while editing the
          documentation application.
        </p>
      </div>
    </main>
  </div>
</body>
</html>"""


@router.get("/docs", include_in_schema=False)
async def api_studio(request: Request) -> HTMLResponse:
    title = request.app.title
    openapi_url = request.app.openapi_url or "/api/openapi.json"

    return _react_docs_response(
        title=title, openapi_url=openapi_url, surface="article"
    )


# ---------------------------------------------------------------------------
# Swagger UI
# ---------------------------------------------------------------------------

@router.get("/swagger", include_in_schema=False)
async def swagger_ui_html(request: Request) -> HTMLResponse:
    title = request.app.title
    openapi_url = request.app.openapi_url or "/api/openapi.json"
    return _react_docs_response(
        title=title, openapi_url=openapi_url, surface="swagger"
    )


@router.get("/swagger-redirect", include_in_schema=False)
async def swagger_ui_redirect() -> HTMLResponse:
    return get_swagger_ui_oauth2_redirect_html()


# ---------------------------------------------------------------------------
# ReDoc
# ---------------------------------------------------------------------------

@router.get("/redoc", include_in_schema=False)
async def redoc_html(request: Request) -> HTMLResponse:
    title = request.app.title
    openapi_url = request.app.openapi_url or "/api/openapi.json"
    return _react_docs_response(
        title=title, openapi_url=openapi_url, surface="redoc"
    )
