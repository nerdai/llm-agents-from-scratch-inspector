"""Ollama daemon status (see #18).

A thin server-side proxy to the local Ollama daemon so the browser
never talks to it directly -- the daemon has no CORS/auth story of its
own. Narrowed from the original TRD §12 scope (status + models list)
per ADR-002: the model is fixed by the user's own launch script, so
there's no client-side model picker left for a models-list endpoint to
feed (see #10, #18's rescope note). Just the reachability/version
check remains.
"""

import httpx

DEFAULT_OLLAMA_HOST = "http://localhost:11434"

_STATUS_TIMEOUT_SECONDS = 2.0


class OllamaService:
    """Reports whether the local Ollama daemon is reachable."""

    def __init__(
        self,
        host: str = DEFAULT_OLLAMA_HOST,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Configure which Ollama daemon to check.

        Args:
            host (str): Base URL of the Ollama daemon. Defaults to
                Ollama's own default, ``http://localhost:11434``.
            transport (httpx.AsyncBaseTransport | None): Optional
                transport override for the internal HTTP client (tests
                use this to inject an ``httpx.MockTransport`` instead
                of hitting a real daemon). Defaults to ``None``, which
                makes ``httpx`` use a real network transport.
        """
        self.host = host
        self._transport = transport

    async def get_status(self) -> tuple[bool, str | None]:
        """Check whether the daemon is reachable and, if so, its version.

        A single ``GET {host}/api/version`` call serves both purposes:
        a successful response means the daemon is up, and its body
        already carries the version string.

        Returns:
            tuple[bool, str | None]: ``(reachable, version)``.
            ``version`` is ``None`` whenever ``reachable`` is ``False``
            (connection refused, timeout, or a non-2xx response --
            e.g. the daemon starting up but not ready yet).
        """
        try:
            async with httpx.AsyncClient(
                timeout=_STATUS_TIMEOUT_SECONDS,
                transport=self._transport,
            ) as client:
                response = await client.get(f"{self.host}/api/version")
                response.raise_for_status()
        except httpx.HTTPError:
            return False, None
        return True, response.json().get("version")
