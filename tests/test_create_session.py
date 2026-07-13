"""Tests for session creation (issue #3, TRD §6.1).

Covers both layers:
    * ``SessionService.create_session_from_config`` -- the business
      logic that builds the ``LLMAgent``/``OllamaLLM``, calls
      ``run_supervised()``, and registers the session.
    * ``POST /api/sessions`` -- the thin route wrapping it, including
      the request/response shape and the ``422`` on invalid config.

``OllamaLLM`` builds an ``ollama.AsyncClient`` at construction time but
makes no network call there, and ``run_supervised()`` doesn't touch the
LLM at all (no memories configured => ``load_memories()`` is a no-op).
So constructing a real session doesn't require a reachable Ollama
daemon -- but we still patch ``AsyncClient`` the same way the upstream
framework's own tests do (see
``llm-agents-from-scratch/tests/llms/test_ollama.py``), both to mirror
that project's own test pattern and as a safety net against any future
network access creeping into ``OllamaLLM.__init__``.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from llm_agents_from_scratch.agent.llm_agent import LLMAgent
from llm_agents_from_scratch.llms.ollama import OllamaLLM

from agent_inspector.server import create_app
from agent_inspector.services import (
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_THINK,
    NEXT_NUMBER_TOOL_NAME,
    SessionConfigError,
    SessionService,
    next_number,
)

_OLLAMA_ASYNC_CLIENT = "llm_agents_from_scratch.llms.ollama.llm.AsyncClient"

_HAILSTONE_TASK = "Compute the full Hailstone sequence starting from 4."


def test_next_number_is_the_hailstone_step_function() -> None:
    """``next_number`` matches the TRD's running Hailstone example."""
    even_input, odd_input = 4, 1

    assert next_number(even_input) == even_input // 2
    assert next_number(odd_input) == 3 * odd_input + 1


class TestCreateSessionFromConfig:
    """``SessionService.create_session_from_config`` (service layer)."""

    @patch(_OLLAMA_ASYNC_CLIENT)
    async def test_builds_agent_with_next_number_tool(
        self,
        mock_async_client_class: MagicMock,
    ) -> None:
        """The agent always gets exactly the ``next_number`` tool."""
        mock_async_client_class.return_value = MagicMock()
        service = SessionService()

        session = await service.create_session_from_config(task=_HAILSTONE_TASK)

        assert isinstance(session.agent, LLMAgent)
        assert set(session.agent.tools_registry) == {NEXT_NUMBER_TOOL_NAME}

    @patch(_OLLAMA_ASYNC_CLIENT)
    async def test_uses_default_model_and_think_when_omitted(
        self,
        mock_async_client_class: MagicMock,
    ) -> None:
        """Omitting ``model``/``think`` falls back to framework defaults."""
        mock_async_client_class.return_value = MagicMock()
        service = SessionService()

        session = await service.create_session_from_config(task="do a thing")

        assert isinstance(session.agent.llm, OllamaLLM)
        assert session.agent.llm.model == DEFAULT_OLLAMA_MODEL
        assert session.agent.llm.think == DEFAULT_THINK

    @patch(_OLLAMA_ASYNC_CLIENT)
    async def test_uses_requested_model_and_think(
        self,
        mock_async_client_class: MagicMock,
    ) -> None:
        """An explicit ``model``/``think`` overrides the defaults."""
        mock_async_client_class.return_value = MagicMock()
        service = SessionService()

        session = await service.create_session_from_config(
            task="do a thing",
            model="llama3.2",
            think=True,
        )

        llm = session.agent.llm
        assert isinstance(llm, OllamaLLM)
        assert llm.model == "llama3.2"
        assert llm.think is True

    @patch(_OLLAMA_ASYNC_CLIENT)
    async def test_ignores_unknown_function_tool_names(
        self,
        mock_async_client_class: MagicMock,
    ) -> None:
        """Only ``next_number`` is ever registered, regardless of input."""
        mock_async_client_class.return_value = MagicMock()
        service = SessionService()

        session = await service.create_session_from_config(
            task="do a thing",
            function_tools=["some_other_tool", NEXT_NUMBER_TOOL_NAME],
        )

        assert set(session.agent.tools_registry) == {NEXT_NUMBER_TOOL_NAME}

    @patch(_OLLAMA_ASYNC_CLIENT)
    async def test_starts_supervised_handler_at_need_next(
        self,
        mock_async_client_class: MagicMock,
    ) -> None:
        """A freshly created session's handler is seeded from ``task``."""
        mock_async_client_class.return_value = MagicMock()
        service = SessionService()

        session = await service.create_session_from_config(task=_HAILSTONE_TASK)

        assert session.need == "next"
        assert session.id.startswith("sess_")
        assert session.handler.task.instruction == _HAILSTONE_TASK
        assert session.handler.task.id_

    @patch(_OLLAMA_ASYNC_CLIENT)
    async def test_registered_session_is_retrievable(
        self,
        mock_async_client_class: MagicMock,
    ) -> None:
        """The returned session is the one stored in the registry."""
        mock_async_client_class.return_value = MagicMock()
        service = SessionService()

        session = await service.create_session_from_config(task="do a thing")

        assert service.get_session(session.id) is session

    @pytest.mark.parametrize("blank_task", ["", "   ", "\n\t"])
    @patch(_OLLAMA_ASYNC_CLIENT)
    async def test_blank_task_raises_session_config_error(
        self,
        mock_async_client_class: MagicMock,
        blank_task: str,
    ) -> None:
        """A blank (or whitespace-only) task is rejected as bad config."""
        mock_async_client_class.return_value = MagicMock()
        service = SessionService()

        with pytest.raises(SessionConfigError):
            await service.create_session_from_config(task=blank_task)


def _client() -> TestClient:
    """Build a ``TestClient`` for the API-only app (no static assets)."""
    return TestClient(create_app(serve_static=False))


class TestCreateSessionRoute:
    """``POST /api/sessions`` (route layer, TRD §6.1)."""

    @patch(_OLLAMA_ASYNC_CLIENT)
    def test_returns_expected_response_shape(
        self,
        mock_async_client_class: MagicMock,
    ) -> None:
        """A well-formed request gets back the TRD §6.1 response shape."""
        mock_async_client_class.return_value = MagicMock()
        client = _client()

        response = client.post(
            "/api/sessions",
            json={
                "task": (
                    "Compute the full Hailstone sequence starting from "
                    "4, step by step using next_number, until you reach 1."
                ),
                "model": "qwen3:14b",
                "think": False,
                "function_tools": [
                    {
                        "name": "next_number",
                        "signature": "next_number(x: int) -> int",
                        "source": "def next_number(x: int) -> int: ...",
                    },
                ],
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        body = response.json()
        assert body["session_id"].startswith("sess_")
        assert body["task"]["instruction"].startswith(
            "Compute the full Hailstone sequence",
        )
        assert isinstance(body["task"]["id_"], str)
        assert body["task"]["id_"]
        assert body["tools"] == ["next_number"]
        assert body["skills"] == []
        assert body["need"] == "next"

    @patch(_OLLAMA_ASYNC_CLIENT)
    def test_defaults_model_and_think_when_omitted(
        self,
        mock_async_client_class: MagicMock,
    ) -> None:
        """Omitting ``model``/``think`` in the request still succeeds."""
        mock_async_client_class.return_value = MagicMock()
        client = _client()

        response = client.post("/api/sessions", json={"task": "do a thing"})

        assert response.status_code == status.HTTP_201_CREATED

    @patch(_OLLAMA_ASYNC_CLIENT)
    def test_ignores_m2_m3_scoped_fields(
        self,
        mock_async_client_class: MagicMock,
    ) -> None:
        """M2/M3-scoped fields are accepted but not wired up yet.

        ``skills_scopes``/``explicit_only_skills``/``mcp_servers`` and
        any ``function_tools`` name other than ``next_number`` don't
        cause a validation error, and don't change what actually gets
        registered on the agent.
        """
        mock_async_client_class.return_value = MagicMock()
        client = _client()

        response = client.post(
            "/api/sessions",
            json={
                "task": "do a thing",
                "skills_scopes": ["USER", "PROJECT"],
                "explicit_only_skills": ["stop-at-one"],
                "mcp_servers": [
                    {
                        "name": "weather-mcp",
                        "transport": "stdio",
                        "command": "uvx weather-mcp",
                    },
                ],
                "function_tools": [
                    {
                        "name": "totally_different_tool",
                        "signature": "totally_different_tool() -> int",
                        "source": "...",
                    },
                ],
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["tools"] == ["next_number"]

    def test_blank_task_returns_422(self) -> None:
        """An empty ``task`` string fails Pydantic's ``min_length``."""
        client = _client()

        response = client.post("/api/sessions", json={"task": ""})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    def test_missing_task_returns_422(self) -> None:
        """A request body without ``task`` is rejected."""
        client = _client()

        response = client.post("/api/sessions", json={})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    def test_wrong_type_returns_422(self) -> None:
        """A wrongly-typed field (e.g. ``think`` as a string) is rejected."""
        client = _client()

        response = client.post(
            "/api/sessions",
            json={"task": "do a thing", "think": "not-a-bool"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
