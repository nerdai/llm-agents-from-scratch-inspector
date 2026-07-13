"""Tests for FastAPI app assembly (server.py), especially SPA-fallback routing.

Covers the ``/assets`` mount + catch-all route that replaced a single
``StaticFiles(html=True)`` mount at ``/`` -- the earlier version 404'd
on any client-side route without a matching file on disk (e.g. a hard
refresh on a future React Router path).
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_inspector import server

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404


@pytest.fixture
def built_web_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake built ``web/`` dir: index.html + assets/ + a top-level file.

    Monkeypatches ``server.WEB_DIR``/``server.ASSETS_DIR`` (looked up
    as module globals inside ``create_app()``, not bound at import
    time) so tests don't depend on a real ``npm run build`` having
    run.
    """
    web_dir = tmp_path / "web"
    assets_dir = web_dir / "assets"
    assets_dir.mkdir(parents=True)
    (web_dir / "index.html").write_text("<html><body>spa-shell</body></html>")
    (web_dir / "favicon.svg").write_text("<svg></svg>")
    (assets_dir / "index-abc123.js").write_text("console.log('hi')")

    monkeypatch.setattr(server, "WEB_DIR", web_dir)
    monkeypatch.setattr(server, "ASSETS_DIR", assets_dir)
    return web_dir


def test_health_route_still_works(built_web_dir: Path) -> None:
    """The API router still takes priority over the static-serving setup."""
    client = TestClient(server.create_app())

    response = client.get("/api/health")

    assert response.status_code == _HTTP_OK


def test_root_serves_index_html(built_web_dir: Path) -> None:
    """The root path serves the built SPA shell."""
    client = TestClient(server.create_app())

    response = client.get("/")

    assert response.status_code == _HTTP_OK
    assert "spa-shell" in response.text


def test_real_asset_is_served_from_assets_mount(built_web_dir: Path) -> None:
    """A real, content-hashed Vite bundle under assets/ is served directly."""
    client = TestClient(server.create_app())

    response = client.get("/assets/index-abc123.js")

    assert response.status_code == _HTTP_OK
    assert "console.log" in response.text


def test_top_level_static_file_is_served(built_web_dir: Path) -> None:
    """A real top-level file (e.g. favicon.svg) is served by the catch-all."""
    client = TestClient(server.create_app())

    response = client.get("/favicon.svg")

    assert response.status_code == _HTTP_OK


def test_unmatched_client_route_falls_back_to_index(
    built_web_dir: Path,
) -> None:
    """A client-side route with no matching file survives a hard refresh.

    This is the bug the /assets + catch-all design fixes: a single
    ``StaticFiles(html=True)`` mount at "/" would 404 here instead.
    """
    client = TestClient(server.create_app())

    response = client.get("/sessions/abc123")

    assert response.status_code == _HTTP_OK
    assert "spa-shell" in response.text


def test_unmatched_api_path_is_a_real_404(built_web_dir: Path) -> None:
    """A broken/unmatched /api/* path must not be swallowed by the fallback.

    Starlette falls through to the catch-all for any /api/* sub-path
    the API router doesn't recognize (it doesn't 404 on its own), so
    the catch-all has to explicitly refuse anything under /api rather
    than silently returning the SPA shell with a 200.
    """
    client = TestClient(server.create_app())

    response = client.get("/api/does-not-exist")

    assert response.status_code == _HTTP_NOT_FOUND


def test_path_traversal_falls_back_safely(built_web_dir: Path) -> None:
    """A traversal attempt can't escape web/; it must fall back, not leak.

    A literal ``../`` is squashed by the HTTP client before the ASGI
    app ever sees it (true of httpx here, and of curl/browsers too),
    so it wouldn't actually exercise the resolve()+is_relative_to()
    guard -- percent-encoding (%2e%2e) survives that normalization and
    is the real bypass vector the guard defends against.
    """
    secret = built_web_dir.parent / "secret.txt"
    secret.write_text("do not leak me")
    client = TestClient(server.create_app())

    response = client.get("/%2e%2e/secret.txt")

    assert response.status_code == _HTTP_OK
    assert "do not leak me" not in response.text
    assert "spa-shell" in response.text


def test_serve_static_false_is_api_only(built_web_dir: Path) -> None:
    """serve_static=False (e.g. --backend-only) skips all static serving."""
    client = TestClient(server.create_app(serve_static=False))

    assert client.get("/api/health").status_code == _HTTP_OK
    assert client.get("/").status_code == _HTTP_NOT_FOUND


def test_no_built_assets_is_a_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No index.html on disk (fresh checkout) -> app boots API-only."""
    web_dir = tmp_path / "web"
    web_dir.mkdir()
    (web_dir / ".gitkeep").write_text("")
    monkeypatch.setattr(server, "WEB_DIR", web_dir)
    monkeypatch.setattr(server, "ASSETS_DIR", web_dir / "assets")

    client = TestClient(server.create_app())

    assert client.get("/api/health").status_code == _HTTP_OK
    assert client.get("/").status_code == _HTTP_NOT_FOUND
