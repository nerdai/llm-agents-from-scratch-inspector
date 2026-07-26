"""Tests for the discovered agent's static properties (see #86).

Covers both layers:
    * ``services.session.get_agent_info`` -- reads ``model``/``tools``
      straight off the discovered ``LLMAgentBuilder`` (no ``.build()``
      call, no session) plus the ``SessionService``-held
      ``default_task``.
    * ``GET /api/agent-info`` -- the thin route wrapping it, reachable
      without any session (same shape as ``GET /api/templates``).

Unlike ``skills`` (session-only, since they depend on per-session
``skills_scopes``/``explicit_only_skills``), ``model``/``tools``/
``default_task`` are all fixed by the discovered builder itself --
these tests exercise that they're readable *before* any session is
created.
"""

from __future__ import annotations

from typing import Any, Sequence

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from llm_agents_from_scratch import LLMAgentBuilder
from llm_agents_from_scratch.base.llm import BaseLLM, StructuredOutputType
from llm_agents_from_scratch.base.tool import Tool
from llm_agents_from_scratch.data_structures import (
    ChatMessage,
    ChatRole,
    CompleteResult,
    Task,
    ToolCallResult,
)
from llm_agents_from_scratch.llms import OllamaLLM
from llm_agents_from_scratch.tools.simple_function import SimpleFunctionTool

from agent_inspector.deps import get_session_service
from agent_inspector.errors.session import AgentBuilderNotConfiguredError
from agent_inspector.server import create_app
from agent_inspector.services.session import SessionService, get_agent_info


class _MockBaseLLM(BaseLLM):
    """Network-free ``BaseLLM`` stand-in, same pattern as
    ``test_create_session.py``'s -- with a real ``model`` attribute
    (``getattr(llm, "model", None)`` is best-effort; most concrete
    implementations, e.g. ``OllamaLLM``, do have one)."""

    model: str = "mock-model-7b"

    async def complete(self, prompt: str, **kwargs: Any) -> CompleteResult:
        """Unused here; provided to satisfy BaseLLM."""
        return CompleteResult(response="mock complete", prompt=prompt)

    async def structured_output(
        self,
        prompt: str,
        mdl: type[StructuredOutputType],
        **kwargs: Any,
    ) -> StructuredOutputType:
        """Unused here; provided to satisfy BaseLLM."""
        raise NotImplementedError

    async def chat(
        self,
        input: str,
        chat_history: Sequence[ChatMessage] | None = None,
        tools: Sequence[Tool] | None = None,
        **kwargs: Any,
    ) -> tuple[ChatMessage, ChatMessage]:
        """Unused here; provided to satisfy BaseLLM."""
        return (
            ChatMessage(role=ChatRole.USER, content=input),
            ChatMessage(role=ChatRole.ASSISTANT, content="mock chat response"),
        )

    async def continue_chat_with_tool_results(
        self,
        tool_call_results: Sequence[ToolCallResult],
        chat_history: Sequence[ChatMessage],
        tools: Sequence[Tool] | None = None,
        **kwargs: Any,
    ) -> tuple[list[ChatMessage], ChatMessage]:
        """Unused here; provided to satisfy BaseLLM."""
        return ([], ChatMessage(role=ChatRole.ASSISTANT, content="mock tool"))


def next_number(x: int) -> int:
    """A trivial test tool, mirroring demo.py's own."""
    if x % 2 == 0:
        return x // 2
    return 3 * x + 1


@pytest.fixture
def agent_builder() -> LLMAgentBuilder:
    """A fixture ``LLMAgentBuilder`` with a model and one tool."""
    return LLMAgentBuilder(llm=_MockBaseLLM()).with_tool(
        SimpleFunctionTool(func=next_number),
    )


class TestGetAgentInfoService:
    """``services.session.get_agent_info`` (service layer)."""

    def test_raises_when_no_builder_configured(self) -> None:
        """No discovered builder raises AgentBuilderNotConfiguredError."""
        service = SessionService()

        with pytest.raises(AgentBuilderNotConfiguredError):
            get_agent_info(service)

    def test_returns_model_and_tools(
        self,
        agent_builder: LLMAgentBuilder,
    ) -> None:
        """model/tools reflect the builder's llm/tools directly."""
        service = SessionService(agent_builder=agent_builder)

        info = get_agent_info(service)

        assert info.model == "mock-model-7b"
        assert info.tools == ["next_number"]

    def test_model_is_none_when_llm_has_no_model_attribute(self) -> None:
        """A `model`-less LLM degrades to `None`, not an error."""

        class _NoModelLLM(_MockBaseLLM):
            model = None  # type: ignore[assignment]

        service = SessionService(
            agent_builder=LLMAgentBuilder(llm=_NoModelLLM()),
        )

        info = get_agent_info(service)

        assert info.model is None

    def test_default_task_is_none_when_not_configured(
        self,
        agent_builder: LLMAgentBuilder,
    ) -> None:
        """No `default_task` on the service reports `None`."""
        service = SessionService(agent_builder=agent_builder)

        info = get_agent_info(service)

        assert info.default_task is None

    def test_default_task_is_returned_when_configured(
        self,
        agent_builder: LLMAgentBuilder,
    ) -> None:
        """A configured `default_task` is passed through as-is."""
        task = Task(instruction="do the default thing")
        service = SessionService(
            agent_builder=agent_builder,
            default_task=task,
        )

        info = get_agent_info(service)

        assert info.default_task is task


class TestOllamaHostDetection:
    """``ollama_host``/``is_local_ollama`` (see #90).

    Constructing an ``OllamaLLM`` never makes a network call --
    ``ollama.AsyncClient.__init__`` just builds an ``httpx.AsyncClient``
    -- so these exercise real instances, not fakes, without needing a
    live daemon (local or cloud).
    """

    def test_non_ollama_llm_reports_none(
        self,
        agent_builder: LLMAgentBuilder,
    ) -> None:
        """A non-`OllamaLLM` reports both `None`, not an error."""
        service = SessionService(agent_builder=agent_builder)

        info = get_agent_info(service)

        assert info.ollama_host is None
        assert info.is_local_ollama is None

    def test_local_ollama_llm_is_detected(self) -> None:
        """`OllamaLLM()` with no `host` resolves to the local default."""
        service = SessionService(
            agent_builder=LLMAgentBuilder(llm=OllamaLLM(model="qwen3:14b")),
        )

        info = get_agent_info(service)

        assert info.ollama_host == "http://127.0.0.1:11434"
        assert info.is_local_ollama is True

    def test_cloud_ollama_llm_is_detected(self) -> None:
        """`OllamaLLM(host="https://ollama.com")` is reported as non-local."""
        service = SessionService(
            agent_builder=LLMAgentBuilder(
                llm=OllamaLLM(
                    host="https://ollama.com",
                    model="qwen3.5:397b-cloud",
                ),
            ),
        )

        info = get_agent_info(service)

        assert info.ollama_host == "https://ollama.com"
        assert info.is_local_ollama is False


def _client(session_service: SessionService) -> TestClient:
    """Build a ``TestClient`` wired to ``session_service`` via dep override."""
    app = create_app(serve_static=False)
    app.dependency_overrides[get_session_service] = lambda: session_service
    return TestClient(app)


class TestGetAgentInfoRoute:
    """``GET /api/agent-info`` (route layer)."""

    def test_returns_500_when_no_builder_configured(self) -> None:
        """No discovered builder maps to a 500, not an opaque crash."""
        client = _client(SessionService())

        response = client.get("/api/agent-info")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_returns_expected_shape_without_default_task(
        self,
        agent_builder: LLMAgentBuilder,
    ) -> None:
        """model/tools come through; default_task is null when unset."""
        client = _client(SessionService(agent_builder=agent_builder))

        response = client.get("/api/agent-info")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["model"] == "mock-model-7b"
        assert body["tools"] == ["next_number"]
        assert body["default_task"] is None

    def test_returns_default_task_when_configured(
        self,
        agent_builder: LLMAgentBuilder,
    ) -> None:
        """A configured default_task serializes with id_/instruction."""
        task = Task(instruction="do the default thing")
        client = _client(
            SessionService(agent_builder=agent_builder, default_task=task),
        )

        response = client.get("/api/agent-info")

        body = response.json()
        assert body["default_task"]["instruction"] == "do the default thing"
        assert body["default_task"]["id_"] == task.id_

    def test_needs_no_session(self, agent_builder: LLMAgentBuilder) -> None:
        """Reachable with zero sessions ever created, same as /templates."""
        client = _client(SessionService(agent_builder=agent_builder))

        response = client.get("/api/agent-info")

        assert response.status_code == status.HTTP_200_OK

    def test_reports_cloud_ollama_host(self) -> None:
        """A cloud-configured OllamaLLM serializes ollama_host and is_local."""
        client = _client(
            SessionService(
                agent_builder=LLMAgentBuilder(
                    llm=OllamaLLM(
                        host="https://ollama.com",
                        model="qwen3.5:397b-cloud",
                    ),
                ),
            ),
        )

        response = client.get("/api/agent-info")

        body = response.json()
        assert body["ollama_host"] == "https://ollama.com"
        assert body["is_local_ollama"] is False

    def test_reports_none_for_non_ollama_llm(
        self,
        agent_builder: LLMAgentBuilder,
    ) -> None:
        """A non-OllamaLLM serializes both fields as null."""
        client = _client(SessionService(agent_builder=agent_builder))

        response = client.get("/api/agent-info")

        body = response.json()
        assert body["ollama_host"] is None
        assert body["is_local_ollama"] is None
