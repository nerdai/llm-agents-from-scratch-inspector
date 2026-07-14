"""Tests for ``OllamaService`` (see #18)."""

from __future__ import annotations

import httpx
import pytest

from agent_inspector.services.ollama import OllamaService


def _service(handler: httpx.MockTransport | None = None) -> OllamaService:
    """Build an ``OllamaService`` against a mocked HTTP transport."""
    return OllamaService(transport=handler)


class TestGetStatus:
    """``OllamaService.get_status()`` (see #18)."""

    async def test_reachable_daemon_returns_version(self) -> None:
        """A ``200`` from ``/api/version`` -> ``(True, <version>)``."""

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/version"
            return httpx.Response(200, json={"version": "0.5.1"})

        service = OllamaService(transport=httpx.MockTransport(handler))

        reachable, version = await service.get_status()

        assert reachable is True
        assert version == "0.5.1"

    @pytest.mark.parametrize(
        "raise_error",
        [
            httpx.ConnectError("connection refused"),
            httpx.TimeoutException("timed out"),
        ],
    )
    async def test_unreachable_daemon_returns_false(
        self,
        raise_error: httpx.HTTPError,
    ) -> None:
        """A connection failure -> ``(False, None)``, not a raised error."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise raise_error

        service = OllamaService(transport=httpx.MockTransport(handler))

        reachable, version = await service.get_status()

        assert reachable is False
        assert version is None

    async def test_non_2xx_response_returns_false(self) -> None:
        """A non-2xx response (daemon up but not ready) -> unreachable."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        service = OllamaService(transport=httpx.MockTransport(handler))

        reachable, version = await service.get_status()

        assert reachable is False
        assert version is None

    async def test_non_json_body_returns_reachable_with_no_version(
        self,
    ) -> None:
        """A ``200`` with a non-JSON body -> still reachable, no version."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"not json")

        service = OllamaService(transport=httpx.MockTransport(handler))

        reachable, version = await service.get_status()

        assert reachable is True
        assert version is None

    async def test_json_array_body_returns_reachable_with_no_version(
        self,
    ) -> None:
        """Valid JSON that isn't an object -> reachable, no version."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=["not", "a", "dict"])

        service = OllamaService(transport=httpx.MockTransport(handler))

        reachable, version = await service.get_status()

        assert reachable is True
        assert version is None

    async def test_non_string_version_returns_reachable_with_no_version(
        self,
    ) -> None:
        """A non-string ``version`` value is treated as absent, not raised."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"version": 123})

        service = OllamaService(transport=httpx.MockTransport(handler))

        reachable, version = await service.get_status()

        assert reachable is True
        assert version is None

    async def test_uses_configured_host(self) -> None:
        """The configured ``host`` is what actually gets requested."""
        seen_urls = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_urls.append(str(request.url))
            return httpx.Response(200, json={"version": "0.5.1"})

        service = OllamaService(
            host="http://example.internal:11434",
            transport=httpx.MockTransport(handler),
        )

        await service.get_status()

        assert seen_urls == ["http://example.internal:11434/api/version"]
