"""Tests for ``GET /api/ollama/status`` (TRD §12, issue #18)."""

from __future__ import annotations

import httpx
from fastapi import status
from fastapi.testclient import TestClient

from agent_inspector.deps import get_ollama_service
from agent_inspector.server import create_app
from agent_inspector.services.ollama import OllamaService


def _client(ollama_service: OllamaService) -> TestClient:
    """Build a ``TestClient`` wired to ``ollama_service`` via dep override."""
    app = create_app(serve_static=False)
    app.dependency_overrides[get_ollama_service] = lambda: ollama_service
    return TestClient(app)


class TestGetOllamaStatus:
    """``GET /api/ollama/status`` (TRD §12)."""

    def test_reachable_daemon_returns_version(self) -> None:
        """A live daemon -> ``200`` with ``reachable: true`` + version."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"version": "0.5.1"})

        client = _client(
            OllamaService(transport=httpx.MockTransport(handler)),
        )

        response = client.get("/api/ollama/status")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"reachable": True, "version": "0.5.1"}

    def test_unreachable_daemon_returns_200_with_reachable_false(
        self,
    ) -> None:
        """An unreachable daemon is a normal ``200``, not an error status --
        the UI's offline hint is driven by ``reachable: false``."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = _client(
            OllamaService(transport=httpx.MockTransport(handler)),
        )

        response = client.get("/api/ollama/status")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"reachable": False, "version": None}
