"""Typer CLI for Agent Inspector.

Registered as the ``agent-inspector`` console script (see
``[project.scripts]`` in ``pyproject.toml``).
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import webbrowser
from pathlib import Path
from typing import Optional

import typer
import uvicorn

from agent_inspector.server import create_app

app = typer.Typer(
    name="agent-inspector",
    help=(
        "Manually drive an LLMAgent's SupervisedTaskHandler one call "
        "at a time, over HTTP, via a browser UI."
    ),
    add_completion=False,
    # A no-op callback keeps `launch` addressable as an explicit
    # subcommand (`agent-inspector launch ...`) instead of Typer
    # collapsing the single command into the root command.
    no_args_is_help=True,
)


@app.callback()
def _callback() -> None:
    """Agent Inspector command-line interface."""


DEFAULT_PORT = 8000
DEFAULT_VITE_PORT = 5173
_BROWSER_OPEN_DELAY_SECONDS = 1.0

# frontend/ lives at the repo root, three levels up from this file
# (src/agent_inspector/cli.py -> src/agent_inspector -> src -> <root>).
_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


def _open_browser_later(url: str) -> None:
    """Open ``url`` in the default browser after a short delay.

    The delay gives uvicorn (and, in dev mode, the Vite dev server)
    time to start accepting connections before the browser tab loads.

    Args:
        url (str): The URL to open.
    """
    timer = threading.Timer(_BROWSER_OPEN_DELAY_SECONDS, webbrowser.open, [url])
    timer.daemon = True
    timer.start()


@app.command()
def launch(
    port: int = typer.Option(
        DEFAULT_PORT,
        "--port",
        help="Port to serve the backend API on.",
    ),
    no_open: bool = typer.Option(
        False,
        "--no-open",
        help="Do not automatically open a browser tab.",
    ),
    backend_only: bool = typer.Option(
        False,
        "--backend-only",
        help=(
            "Only start the FastAPI backend; skip serving the bundled "
            "UI and opening a browser."
        ),
    ),
    dev: bool = typer.Option(
        False,
        "--dev",
        help=(
            "Development mode: run the backend without serving the "
            "bundled web/ assets, and instead start the Vite dev "
            "server (frontend/), which proxies /api requests back to "
            "this backend so the UI and API are reachable from a "
            "single origin (the Vite dev server's URL)."
        ),
    ),
) -> None:
    """Boot the Agent Inspector backend and (by default) its UI.

    Args:
        port (int): Port to serve the backend API on. Defaults to
            8000.
        no_open (bool): Skip opening a browser tab automatically.
            Defaults to False.
        backend_only (bool): Skip serving static assets and opening a
            browser; only run the API. Defaults to False.
        dev (bool): Run the Vite dev server alongside the backend
            instead of serving the bundled ``web/`` assets. Defaults
            to False.
    """
    serve_static = not backend_only and not dev
    fastapi_app = create_app(serve_static=serve_static)

    vite_process: Optional[subprocess.Popen[bytes]] = None
    browser_url = f"http://127.0.0.1:{port}"

    if dev and not backend_only:
        npm = shutil.which("npm")
        if npm is not None and _FRONTEND_DIR.is_dir():
            typer.echo(
                f"Starting Vite dev server in {_FRONTEND_DIR} "
                f"(proxying /api to http://127.0.0.1:{port})...",
            )
            vite_process = subprocess.Popen(
                [npm, "run", "dev"],
                cwd=_FRONTEND_DIR,
            )
            browser_url = f"http://127.0.0.1:{DEFAULT_VITE_PORT}"
        else:
            typer.echo(
                "--dev requested but npm and/or frontend/ was not "
                "found; serving the API only. Run `npm run dev` in "
                "frontend/ manually (it proxies /api to the backend).",
            )

    if not backend_only and not no_open:
        _open_browser_later(browser_url)

    try:
        uvicorn.run(fastapi_app, host="127.0.0.1", port=port)
    finally:
        if vite_process is not None:
            vite_process.terminate()


def main() -> None:
    """CLI entry point registered as the ``agent-inspector`` script."""
    app()


if __name__ == "__main__":
    main()
