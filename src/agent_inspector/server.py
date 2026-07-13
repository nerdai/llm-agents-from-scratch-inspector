"""FastAPI application assembly.

Builds the ``FastAPI`` app and ``include_router``s from ``routes.py``.
No business logic lives here. When built frontend assets are present
under ``web/``, they are mounted as a catch-all static file handler so
the backend and UI can be served from a single origin.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from agent_inspector.routes import router

WEB_DIR = Path(__file__).parent / "web"


def create_app(*, serve_static: bool = True) -> FastAPI:
    """Assemble the Agent Inspector FastAPI application.

    Args:
        serve_static (bool): Whether to mount the built frontend
            assets (if present under ``web/``) as a catch-all static
            file handler. When ``web/`` has no built assets (e.g. in a
            fresh dev checkout before ``npm run build`` has run), this
            is a no-op so the API still boots cleanly. Defaults to
            True.

    Returns:
        FastAPI: The assembled application.
    """
    app = FastAPI(title="Agent Inspector")
    app.include_router(router)

    # WEB_DIR always contains a tracked `.gitkeep` (even in a fresh,
    # unbuilt checkout), so check for `index.html` specifically rather
    # than "any file exists" -- otherwise this mounts StaticFiles with
    # nothing real to serve, and `/` 404s instead of the documented
    # no-op.
    has_built_assets = (WEB_DIR / "index.html").is_file()
    if serve_static and has_built_assets:
        app.mount(
            "/",
            StaticFiles(directory=WEB_DIR, html=True),
            name="web",
        )

    return app
