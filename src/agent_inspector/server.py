"""FastAPI application assembly.

Builds the ``FastAPI`` app, ``include_router``s from ``routes.py``,
and registers the shared ``SessionServiceError`` -> HTTP-response
handler (``routes/error_handlers.py``, see #26) that every route
relies on instead of its own per-endpoint try/except. No business
logic lives here. When built frontend assets are present
under ``web/``, ``/assets`` (Vite's content-hashed JS/CSS bundles) is
mounted directly, and a catch-all route serves any other real file
under ``web/`` (e.g. ``favicon.svg``) or falls back to ``index.html``
for anything else -- so client-side routes survive a hard refresh,
which a single ``StaticFiles(html=True)`` mount at ``/`` cannot do (a
``Mount`` owns its whole path prefix; a 404 raised inside it never
falls through to a route registered after it).

Also owns the app's ``lifespan``: starting/stopping the session-
eviction background sweep (#25) against the process-wide
``SessionService`` singleton (``deps.get_session_service()``) for the
life of the app. The sweep loop itself is business logic and lives in
``services/session.py`` (``SessionService.run_eviction_sweep``); this
module only starts/cancels that task at the right time, per the repo's
FastAPI layering standard (routes/server stay thin, business logic
lives in ``services/``).
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agent_inspector.deps import get_session_service
from agent_inspector.routes import router
from agent_inspector.routes.error_handlers import register_exception_handlers
from agent_inspector.services.session import DEFAULT_SESSION_TTL_SECONDS

WEB_DIR = Path(__file__).parent / "web"
ASSETS_DIR = WEB_DIR / "assets"


def create_app(
    *,
    serve_static: bool = True,
    session_ttl_seconds: float = DEFAULT_SESSION_TTL_SECONDS,
    session_sweep_interval_seconds: float | None = None,
) -> FastAPI:
    """Assemble the Agent Inspector FastAPI application.

    Args:
        serve_static (bool): Whether to serve the built frontend
            assets (if present under ``web/``). When ``web/`` has no
            built assets (e.g. in a fresh dev checkout before ``npm
            run build`` has run), this is a no-op so the API still
            boots cleanly. Defaults to True.
        session_ttl_seconds (float): Idle TTL (#25) after which a
            session with no mutating call is evicted -- closing its
            MCP providers and freeing its ``LLMAgent``/handler.
            Forwarded to the eviction-sweep task started in this app's
            ``lifespan``. Defaults to
            ``services.session.DEFAULT_SESSION_TTL_SECONDS``.
        session_sweep_interval_seconds (float | None): How often the
            eviction sweep checks for idle sessions. Forwarded verbatim
            to ``SessionService.run_eviction_sweep`` -- ``None`` (the
            default) derives a sane interval from
            ``session_ttl_seconds`` rather than requiring a separate
            knob; see that method's docstring.

    Returns:
        FastAPI: The assembled application.
    """

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Run the session-eviction sweep (#25) for the app's lifetime.

        Started against ``deps.get_session_service()``'s process-wide
        singleton -- the same instance every route's ``SessionServiceDep``
        resolves to -- so no separate DI wiring is needed. Cancelled and
        awaited on shutdown so the sweep doesn't outlive the app (e.g. in
        tests that build multiple apps in the same process).
        """
        session_service = get_session_service()
        sweep_task = asyncio.create_task(
            session_service.run_eviction_sweep(
                ttl_seconds=session_ttl_seconds,
                interval_seconds=session_sweep_interval_seconds,
            ),
        )
        try:
            yield
        finally:
            sweep_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sweep_task

    app = FastAPI(title="Agent Inspector", lifespan=lifespan)
    app.include_router(router)
    register_exception_handlers(app)

    # WEB_DIR always contains a tracked `.gitkeep` (even in a fresh,
    # unbuilt checkout), so check for `index.html` specifically rather
    # than "any file exists" -- otherwise this serves a UI with
    # nothing real behind it.
    has_built_assets = (WEB_DIR / "index.html").is_file()
    if serve_static and has_built_assets and ASSETS_DIR.is_dir():
        # Vite content-hashes every filename under assets/, so it's
        # safe to serve directly (and, later, cache aggressively).
        app.mount(
            "/assets",
            StaticFiles(directory=ASSETS_DIR),
            name="web-assets",
        )

        web_dir_resolved = WEB_DIR.resolve()

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_spa(full_path: str) -> FileResponse:
            """Serve a real ``web/`` file if one exists, else the SPA shell.

            A plain route (registered after the API router and the
            ``/assets`` mount), not a ``Mount`` -- so it only ever
            handles paths neither of those already claimed, and it
            can fall back to ``index.html`` instead of just 404ing.
            That fallback is what lets a client-side route (e.g. a
            future React Router path with no file on disk) survive a
            hard refresh: the browser gets the SPA shell again and the
            client-side router takes over from there.

            Args:
                full_path (str): The requested path, with the leading
                    slash stripped by FastAPI's path converter.

            Returns:
                FileResponse: The matching file under ``web/`` if one
                    exists (e.g. ``favicon.svg``), otherwise
                    ``web/index.html``. Resolves and checks the
                    candidate is actually inside ``web/`` first, so a
                    path like ``../../etc/passwd`` can't escape it.

            Raises:
                HTTPException: 404 for any ``api/...`` path. Routes
                    registered earlier (the API router) already get
                    first refusal at real ``/api/*`` requests, but
                    Starlette falls through to this catch-all for any
                    of *its* unmatched sub-paths (e.g. a typo'd
                    endpoint) rather than 404ing on its own -- without
                    this check, a broken API URL would silently come
                    back as the SPA shell with a ``200`` instead of a
                    real 404.
            """
            if full_path == "api" or full_path.startswith("api/"):
                raise HTTPException(status_code=404)

            candidate = (WEB_DIR / full_path).resolve()
            if (
                full_path
                and candidate.is_file()
                and candidate.is_relative_to(web_dir_resolved)
            ):
                return FileResponse(candidate)
            return FileResponse(WEB_DIR / "index.html")

    return app
